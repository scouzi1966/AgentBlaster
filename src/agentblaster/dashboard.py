from __future__ import annotations

import hashlib
import hmac
import html
import json
from importlib.util import find_spec
from http.cookies import SimpleCookie
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse
from zipfile import BadZipFile, ZipFile

from pydantic import ValidationError

from agentblaster.audit import AuditLogger
from agentblaster.campaign import campaign_plan_preview
from agentblaster.capabilities import check_suite_compatibility, format_capability_report
from agentblaster.cleanup import CLEANUP_PLAN_SCHEMA_VERSION, RETENTION_CLEANUP_SCHEMA_VERSION
from agentblaster.config import ProviderStore
from agentblaster.engine_advisory import ENGINE_ADVISORY_SCHEMA_VERSION
from agentblaster.engine_onboarding import build_local_engine_onboarding
from agentblaster.engine_targets import engine_target_catalog
from agentblaster.errors import ConfigError, PolicyError, SecretError
from agentblaster.evidence_index import EVIDENCE_INDEX_SCHEMA_VERSION
from agentblaster.harness import HARNESS_REVIEW_SCHEMA_VERSION
from agentblaster.implementation_status import IMPLEMENTATION_STATUS_SCHEMA_VERSION
from agentblaster.matrix_gate import MATRIX_GATE_SCHEMA_VERSION
from agentblaster.matrix_pressure import MATRIX_PRESSURE_SCHEMA_VERSION
from agentblaster.matrix_saturation import MATRIX_SATURATION_SCHEMA_VERSION
from agentblaster.metric_coverage import METRIC_COVERAGE_SCHEMA_VERSION
from agentblaster.model_catalog import list_model_targets
from agentblaster.models import ApiContract, ModelMetadata, ProviderConfig, RawTraceMode, SecretRef
from agentblaster.policy import SecurityPolicy, enforce_provider_policy, load_policy
from agentblaster.planning import build_run_plan
from agentblaster.protocol_repair import PROTOCOL_REPAIR_POSTURE_SCHEMA_VERSION
from agentblaster.provider_audit import PROVIDER_AUDIT_SCHEMA_VERSION, audit_providers
from agentblaster.publication_brief import PUBLICATION_BRIEF_SCHEMA_VERSION
from agentblaster.quality import SDLC_VALIDATION_MANIFEST_SCHEMA_VERSION, SELFTEST_REPORT_SCHEMA_VERSION
from agentblaster.readiness import READINESS_SCHEMA_VERSION
from agentblaster.redaction import redact_value
from agentblaster.reports import generate_reports, load_manifest, load_results, summarize_run
from agentblaster.runner import BenchmarkRunner, RUN_EVENTS_FILENAME
from agentblaster.security_posture import SECURITY_POSTURE_SCHEMA_VERSION
from agentblaster.secrets import SecretResolver, dotenv_ref_name
from agentblaster.suite_audit import SUITE_AUDIT_SCHEMA_VERSION
from agentblaster.suite_calibration import CALIBRATION_REPORT_SCHEMA_VERSION
from agentblaster.suites import BUILTIN_SUITES, get_builtin_suite
from agentblaster.telemetry import telemetry_mapping_catalog
from agentblaster.workflow_readiness import WORKFLOW_READINESS_SCHEMA_VERSION
from agentblaster.workflow_surfaces import workflow_surface_catalog


LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
DASHBOARD_AUTH_COOKIE = "agentblaster_dashboard"
REPORT_ARTIFACTS = {
    "report.html": "text/html; charset=utf-8",
    "report.md": "text/markdown; charset=utf-8",
    "report.pdf": "application/pdf",
    "summary.json": "application/json; charset=utf-8",
    "publication.json": "application/json; charset=utf-8",
    "report-card.svg": "image/svg+xml; charset=utf-8",
    "report-card.png": "image/png",
    "metrics/prometheus-summary.json": "application/json; charset=utf-8",
}
REVIEW_ARTIFACT_DIRS = (
    "reports",
    "evidence",
    "publication-bundles",
    "release-bundles",
    "campaign-preflight",
    "test-reports",
)
REVIEW_ARTIFACT_SUFFIXES = {".json", ".zip"}
REVIEW_ARTIFACT_MAX_JSON_BYTES = 1_000_000
REVIEW_ARTIFACT_BLOCKED_NAMES = {"results.jsonl"}
PUBLICATION_BUNDLE_MANIFEST = "publication-bundle-manifest.json"
PUBLICATION_BUNDLE_MANIFEST_SCHEMA_VERSION = "agentblaster.publication-bundle.v1"
MATRIX_PUBLICATION_BUNDLE_MANIFEST = "matrix-publication-bundle-manifest.json"
MATRIX_PUBLICATION_BUNDLE_MANIFEST_SCHEMA_VERSION = "agentblaster.matrix-publication-bundle.v1"
MEDIA_KIT_SCHEMA_VERSION = "agentblaster.media-kit.v1"
MATRIX_SCORECARD_SCHEMA_VERSION = "agentblaster-matrix-scorecard-v1"
CAMPAIGN_PREFLIGHT_BENCHMARK_READINESS_INDEX_SCHEMA_VERSION = "agentblaster.campaign-preflight-benchmark-readiness-index.v1"
CAMPAIGN_PREFLIGHT_SCHEMA_VERSION = "agentblaster.campaign-preflight-bundle.v1"
NORMALIZED_TELEMETRY_SCHEMA_VERSION = "agentblaster.normalized-telemetry.v1"


def assert_dashboard_bind_allowed(
    host: str,
    *,
    allow_non_loopback: bool = False,
    auth_configured: bool = False,
) -> None:
    """Require explicit opt-in before binding the dashboard beyond loopback."""
    if _is_loopback_host(host):
        return
    if allow_non_loopback and auth_configured:
        return
    if allow_non_loopback:
        raise ConfigError("non-loopback dashboard binding requires token authentication")
    raise ConfigError(
        "dashboard binds to loopback by default; pass --allow-non-loopback only on trusted networks"
    )


def list_dashboard_runs(runs_dir: Path) -> list[dict[str, Any]]:
    """Return compact, redacted summaries for valid run directories."""
    if not runs_dir.exists():
        return []

    runs: list[dict[str, Any]] = []
    for run_dir in sorted((path for path in runs_dir.iterdir() if path.is_dir()), reverse=True):
        try:
            manifest = load_manifest(run_dir)
            results = load_results(run_dir)
            summary = summarize_run(run_dir)
        except ConfigError:
            continue
        runs.append(
            {
                "run_id": manifest.run_id,
                "suite": manifest.suite,
                "provider": manifest.provider,
                "contract": manifest.contract.value,
                "model": manifest.model,
                "model_metadata": manifest.model_metadata.model_dump(mode="json"),
                "provider_metadata": manifest.provider_metadata.model_dump(mode="json"),
                "created_at": manifest.created_at,
                "raw_trace_mode": manifest.raw_trace_mode.value,
                "retention_policy": manifest.retention_policy.model_dump(mode="json"),
                "concurrency": manifest.concurrency,
                "suite_sha256": manifest.suite_sha256,
                "suite_snapshot_path": manifest.suite_snapshot_path,
                "suite_provenance": manifest.suite_provenance.model_dump(mode="json"),
                "metrics_artifacts": manifest.metrics_artifacts,
                "total_cases": summary.total_cases,
                "passed": summary.passed,
                "failed": summary.failed,
                "ok": summary.failed == 0,
                "duration_ms": summary.duration_ms,
                "requests_per_second": summary.requests_per_second,
                "total_cost_usd": _sum_metric([result.total_cost_usd for result in results]),
                "avg_queue_ms": _average_metric([result.queue_ms for result in results]),
                "avg_rate_limit_wait_ms": _average_metric([result.rate_limit_wait_ms for result in results]),
                "avg_latency_ms": _average_metric([result.latency_ms for result in results]),
                "avg_ttft_ms": _average_metric([result.ttft_ms for result in results]),
                "avg_decode_tokens_per_second": _average_metric(
                    [result.tokens_per_second_decode for result in results]
                ),
                "artifacts": _run_artifacts(manifest.run_id, run_dir),
            }
        )
    return runs


def dashboard_run_payload(runs_dir: Path, run_id: str) -> dict[str, Any]:
    if not runs_dir.exists():
        raise ConfigError(f"runs directory does not exist: {runs_dir}")
    for run_dir in sorted(path for path in runs_dir.iterdir() if path.is_dir()):
        try:
            manifest = load_manifest(run_dir)
        except ConfigError:
            continue
        if manifest.run_id != run_id:
            continue
        results = load_results(run_dir)
        summary = summarize_run(run_dir)
        return {
            "manifest": manifest.model_dump(mode="json"),
            "summary": summary.model_dump(mode="json"),
            "results": [result.model_dump(mode="json") for result in results],
        }
    raise ConfigError(f"unknown run: {run_id}")


def dashboard_run_events(runs_dir: Path, run_id: str) -> dict[str, Any]:
    run_dir = dashboard_run_dir(runs_dir, run_id)
    events_path = run_dir / RUN_EVENTS_FILENAME
    if not events_path.exists():
        return {
            "schema_version": "agentblaster.dashboard-run-events.v1",
            "run_id": run_id,
            "events_path": RUN_EVENTS_FILENAME,
            "event_count": 0,
            "events": [],
            "missing_artifact": True,
            "security_notes": [
                "Lifecycle events are operational metadata only; raw prompts, response text, raw provider payloads, headers, and secrets are not exposed.",
            ],
        }
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(events_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            events.append({"line": line_number, "event": "malformed_event", "ok": False})
            continue
        if isinstance(event, dict):
            events.append(redact_value(event))
    return {
        "schema_version": "agentblaster.dashboard-run-events.v1",
        "run_id": run_id,
        "events_path": RUN_EVENTS_FILENAME,
        "event_count": len(events),
        "events": events,
        "missing_artifact": False,
        "security_notes": [
            "Lifecycle events are operational metadata only; raw prompts, response text, raw provider payloads, headers, and secrets are not exposed.",
            "Event payloads are defensively redacted again before dashboard API output.",
        ],
    }


def generate_dashboard_reports(runs_dir: Path, run_id: str, formats: list[str]) -> dict[str, Any]:
    run_dir = dashboard_run_dir(runs_dir, run_id)
    requested_formats = [item.strip() for item in formats if item.strip()]
    if not requested_formats:
        requested_formats = ["html", "md", "json", "publication", "card", "pdf"]
    generated = generate_reports(run_dir, requested_formats)
    manifest = load_manifest(run_dir)
    return {
        "run_id": manifest.run_id,
        "generated": [
            {
                "name": path.relative_to(run_dir).as_posix(),
                "label": _artifact_label(path.relative_to(run_dir).as_posix()),
                "href": f"/runs/{quote(manifest.run_id, safe='')}/artifacts/{quote(path.relative_to(run_dir).as_posix(), safe='')}",
            }
            for path in generated
            if path.relative_to(run_dir).as_posix() in REPORT_ARTIFACTS
        ],
    }


def dashboard_providers(store: ProviderStore | None = None) -> list[dict[str, Any]]:
    providers = (store or ProviderStore()).list()
    return [
        {
            "name": provider.name,
            "contract": provider.contract.value,
            "base_url": str(provider.base_url).rstrip("/"),
            "default_model": provider.default_model,
            "remote": provider.remote,
            "api_key_ref": provider.api_key_ref.redacted_display() if provider.api_key_ref else None,
            "api_key_ref_path_redacted": provider.api_key_ref.display_path_redacted() if provider.api_key_ref else False,
            "native_adapter": provider.native_adapter,
            "capabilities": provider.capabilities,
            "rate_limits": provider.rate_limits,
            "metrics_url": str(provider.metrics_url).rstrip("/") if provider.metrics_url else None,
            "tls_verify": provider.tls_verify,
            "ca_bundle": str(provider.ca_bundle) if provider.ca_bundle else None,
            "model_metadata": provider.model_metadata.model_dump(mode="json"),
        }
        for provider in providers
    ]


def configure_dashboard_provider_profile(
    payload: dict[str, Any],
    *,
    audit_log: Path | None = None,
    policy: SecurityPolicy | None = None,
) -> dict[str, Any]:
    name = str(payload.get("name") or payload.get("provider") or "").strip()
    if not name:
        raise ConfigError("provider setup requires name")
    contract_value = str(payload.get("contract") or ApiContract.OPENAI.value).strip()
    try:
        contract = ApiContract(contract_value)
    except ValueError as exc:
        allowed = ", ".join(contract.value for contract in ApiContract)
        raise ConfigError(f"provider contract must be one of: {allowed}") from exc
    base_url = str(payload.get("base_url") or "").strip()
    if not base_url:
        raise ConfigError("provider setup requires base_url")

    default_model = str(payload.get("default_model") or "").strip() or None
    native_adapter = str(payload.get("native_adapter") or "").strip() or None
    metrics_url = str(payload.get("metrics_url") or "").strip() or None
    ca_bundle = str(payload.get("ca_bundle") or "").strip() or None
    api_key_env = str(payload.get("api_key_env") or payload.get("env_var") or "").strip()
    api_key_ref = None
    if api_key_env:
        if not _valid_env_var_name(api_key_env):
            raise ConfigError("provider setup requires a valid API-key environment variable name")
        api_key_ref = SecretRef(kind="env", name=api_key_env)

    store = ProviderStore()
    existing_names = {provider.name for provider in store.list()}
    provider = ProviderConfig(
        name=name,
        contract=contract,
        base_url=base_url,
        api_key_ref=api_key_ref,
        default_model=default_model,
        native_adapter=native_adapter,
        metrics_url=metrics_url,
        tls_verify=_payload_bool(payload, "tls_verify", default=True),
        ca_bundle=Path(ca_bundle) if ca_bundle else None,
        remote=_payload_bool(payload, "remote", default=False),
    )
    store.upsert(provider)
    event = "provider_updated" if provider.name in existing_names else "provider_created"
    result = {
        "name": provider.name,
        "contract": provider.contract.value,
        "base_url": str(provider.base_url).rstrip("/"),
        "default_model": provider.default_model,
        "remote": provider.remote,
        "api_key_ref": provider.api_key_ref.redacted_display() if provider.api_key_ref else None,
        "api_key_ref_path_redacted": provider.api_key_ref.display_path_redacted() if provider.api_key_ref else False,
        "native_adapter": provider.native_adapter,
        "metrics_url": str(provider.metrics_url).rstrip("/") if provider.metrics_url else None,
        "tls_verify": provider.tls_verify,
        "ca_bundle": str(provider.ca_bundle) if provider.ca_bundle else None,
    }
    policy_review = _dashboard_provider_policy_review(provider, policy)
    if policy_review is not None:
        result["policy_review"] = policy_review
    AuditLogger(audit_log).emit(
        event,
        source="dashboard",
        provider=provider.name,
        contract=provider.contract.value,
        base_url=str(provider.base_url).rstrip("/"),
        remote=provider.remote,
        api_key_ref=provider.api_key_ref.redacted_display() if provider.api_key_ref else None,
        api_key_ref_path_redacted=provider.api_key_ref.display_path_redacted() if provider.api_key_ref else False,
        tls_verify=provider.tls_verify,
        ca_bundle=str(provider.ca_bundle) if provider.ca_bundle else None,
        native_adapter=provider.native_adapter,
        policy_ok=policy_review["ok"] if policy_review else None,
        policy_finding_count=policy_review["finding_count"] if policy_review else None,
    )
    return result


def configure_dashboard_provider_auth(
    provider_name: str,
    payload: dict[str, Any],
    *,
    audit_log: Path | None = None,
    policy: SecurityPolicy | None = None,
) -> dict[str, Any]:
    provider_name = provider_name.strip()
    if not provider_name:
        raise ConfigError("provider auth setup requires provider")

    method = str(payload.get("method") or payload.get("auth_method") or payload.get("kind") or "").strip().lower()
    if method == "environment":
        method = "env"
    if method in {"keychain", "apple-keychain"}:
        method = "keyring"

    store = ProviderStore()
    provider = store.get(provider_name)
    resolver = SecretResolver()
    api_key_to_store: str | None = None

    if method == "env":
        env_var = str(payload.get("env_var") or payload.get("env") or payload.get("api_key_env") or "").strip()
        if not _valid_env_var_name(env_var):
            raise ConfigError("env auth setup requires a valid environment variable name")
        if str(payload.get("api_key") or payload.get("secret") or "").strip():
            raise ConfigError("env auth setup must not include raw API-key material; use keyring auth for API-key entry")
        ref = SecretRef(kind="env", name=env_var)
        stored_secret = False
        secret_backend = "env"
    elif method == "keyring":
        api_key = str(payload.get("api_key") or payload.get("secret") or "").strip()
        if not api_key:
            raise ConfigError("keyring auth setup requires api_key")
        ref = SecretRef(kind="keyring", name=f"{provider.name}:api_key")
        api_key_to_store = api_key
        stored_secret = True
        secret_backend = "keyring"
    elif method == "dotenv":
        if not bool(payload.get("allow_plaintext_secret_file")):
            raise ConfigError("dotenv auth setup requires allow_plaintext_secret_file")
        api_key = str(payload.get("api_key") or payload.get("secret") or "").strip()
        dotenv_file = str(payload.get("dotenv_file") or payload.get("api_key_dotenv_file") or "").strip()
        dotenv_var = str(payload.get("dotenv_var") or payload.get("env_var") or "").strip()
        if not api_key:
            raise ConfigError("dotenv auth setup requires api_key")
        if not dotenv_file:
            raise ConfigError("dotenv auth setup requires dotenv_file")
        if not _valid_env_var_name(dotenv_var):
            raise ConfigError("dotenv auth setup requires a valid dotenv_var")
        ref = SecretRef(kind="dotenv", name=dotenv_ref_name(dotenv_var, Path(dotenv_file)))
        api_key_to_store = api_key
        stored_secret = True
        secret_backend = "dotenv"
    else:
        raise ConfigError("provider auth setup method must be env, keyring, or dotenv")

    updated_provider = provider.model_copy(update={"api_key_ref": ref})
    policy_review = _dashboard_provider_policy_review(updated_provider, policy)
    if stored_secret and policy_review is not None and not policy_review["ok"]:
        AuditLogger(audit_log).emit(
            "provider_auth_ref_rejected",
            provider=provider.name,
            ref_kind=ref.kind,
            secret_backend=secret_backend,
            stored_secret=False,
            resolves=False,
            plaintext_secret_warning=secret_backend == "dotenv",
            source="dashboard",
            policy_ok=False,
            policy_finding_count=policy_review["finding_count"],
        )
        raise ConfigError("provider auth secret storage blocked by policy")
    if api_key_to_store is not None:
        try:
            resolver.set(ref, api_key_to_store)
        except SecretError as exc:
            if secret_backend == "keyring":
                raise ConfigError("keyring secret storage is unavailable; use env auth or install agentblaster[secrets]") from exc
            raise ConfigError("dotenv secret storage is unavailable; use env auth or keyring auth") from exc
    store.upsert(updated_provider)
    resolves = resolver.resolve(ref) is not None
    result = {
        "provider": provider.name,
        "api_key_ref": ref.redacted_display(),
        "api_key_ref_path_redacted": ref.display_path_redacted(),
        "secret_backend": secret_backend,
        "stored_secret": stored_secret,
        "resolves": resolves,
    }
    if secret_backend == "dotenv":
        result["plaintext_secret_warning"] = True
    if policy_review is not None:
        result["policy_review"] = policy_review
    AuditLogger(audit_log).emit(
        "provider_auth_ref_changed",
        provider=provider.name,
        api_key_ref=ref.redacted_display(),
        api_key_ref_path_redacted=ref.display_path_redacted(),
        ref_kind=ref.kind,
        secret_backend=secret_backend,
        stored_secret=stored_secret,
        resolves=resolves,
        plaintext_secret_warning=secret_backend == "dotenv",
        source="dashboard",
        policy_ok=policy_review["ok"] if policy_review else None,
        policy_finding_count=policy_review["finding_count"] if policy_review else None,
    )
    return result


def clear_dashboard_provider_auth(
    provider_name: str,
    *,
    delete_secret: bool = False,
    audit_log: Path | None = None,
    policy: SecurityPolicy | None = None,
) -> dict[str, Any]:
    provider_name = provider_name.strip()
    if not provider_name:
        raise ConfigError("provider auth clear requires provider")

    store = ProviderStore()
    provider = store.get(provider_name)
    ref = provider.api_key_ref
    deleted_secret = False

    if ref is not None and delete_secret:
        if ref.kind not in {"keyring", "dotenv"}:
            raise ConfigError(
                "only keyring or dotenv secrets can be deleted by AgentBlaster; unset env secrets in your shell or CI"
            )
        try:
            SecretResolver().delete(ref)
        except SecretError as exc:
            raise ConfigError("secret deletion is unavailable; clear the auth reference without deleting the secret") from exc
        deleted_secret = True

    updated_provider = provider.model_copy(update={"api_key_ref": None})
    store.upsert(updated_provider)
    result = {
        "provider": provider.name,
        "api_key_ref": None,
        "previous_api_key_ref": ref.redacted_display() if ref else None,
        "previous_api_key_ref_path_redacted": ref.display_path_redacted() if ref else False,
        "secret_backend": ref.kind if ref else None,
        "cleared": ref is not None,
        "deleted_secret": deleted_secret,
    }
    policy_review = _dashboard_provider_policy_review(updated_provider, policy)
    if policy_review is not None:
        result["policy_review"] = policy_review
    AuditLogger(audit_log).emit(
        "provider_auth_ref_cleared",
        provider=provider.name,
        previous_api_key_ref=ref.redacted_display() if ref else None,
        previous_api_key_ref_path_redacted=ref.display_path_redacted() if ref else False,
        ref_kind=ref.kind if ref else None,
        deleted_keyring_secret=deleted_secret and ref is not None and ref.kind == "keyring",
        deleted_dotenv_secret=deleted_secret and ref is not None and ref.kind == "dotenv",
        source="dashboard",
        policy_ok=policy_review["ok"] if policy_review else None,
        policy_finding_count=policy_review["finding_count"] if policy_review else None,
    )
    return result


def _dashboard_provider_policy_review(provider: ProviderConfig, policy: SecurityPolicy | None) -> dict[str, Any] | None:
    if policy is None:
        return None
    try:
        enforce_provider_policy(
            provider,
            policy,
            raw_trace_mode=RawTraceMode.REDACTED,
            concurrency=1,
            suite=None,
        )
    except PolicyError as exc:
        return {
            "policy_configured": True,
            "ok": False,
            "status": "blocked",
            "finding_count": 1,
            "findings": [
                {
                    "severity": "error",
                    "code": "policy_violation",
                    "message": str(redact_value(str(exc))),
                }
            ],
            "contacts_provider": False,
            "resolves_secrets": False,
        }
    return {
        "policy_configured": True,
        "ok": True,
        "status": "pass",
        "finding_count": 0,
        "findings": [],
        "contacts_provider": False,
        "resolves_secrets": False,
    }


def dashboard_suites() -> list[dict[str, Any]]:
    return [
        {
            "name": suite.name,
            "description": suite.description,
            "provenance": suite.provenance.model_dump(mode="json"),
            "case_count": len(suite.cases),
            "cases": [
                {
                    "id": case.id,
                    "title": case.title,
                    "tags": case.tags,
                    "risk_level": case.risk_level,
                    "provenance": case.provenance,
                }
                for case in suite.cases
            ],
        }
        for suite in BUILTIN_SUITES.values()
    ]


def dashboard_model_targets() -> dict[str, Any]:
    return {
        "schema_version": "agentblaster.dashboard-model-targets.v1",
        "model_targets": [target.model_dump(mode="json") for target in list_model_targets()],
    }


def dashboard_engine_targets() -> dict[str, Any]:
    return engine_target_catalog()


def dashboard_local_engine_onboarding() -> dict[str, Any]:
    return build_local_engine_onboarding()


def dashboard_workflow_surfaces() -> dict[str, Any]:
    return workflow_surface_catalog()


def dashboard_telemetry_mappings() -> dict[str, Any]:
    return telemetry_mapping_catalog()


def dashboard_review_artifacts(project_root: Path | None = None) -> dict[str, Any]:
    """Return redaction-safe metadata for static review and release artifacts."""

    root = (project_root or Path.cwd()).resolve()
    artifacts: list[dict[str, Any]] = []
    skipped = 0
    for directory in REVIEW_ARTIFACT_DIRS:
        base = root / directory
        if not base.exists() or not base.is_dir():
            continue
        for path in sorted(item for item in base.rglob("*") if item.is_file()):
            if _is_blocked_review_artifact(path):
                skipped += 1
                continue
            if path.suffix.lower() not in REVIEW_ARTIFACT_SUFFIXES:
                skipped += 1
                continue
            try:
                artifacts.append(_review_artifact_entry(path, root=root, category=directory))
            except ConfigError:
                skipped += 1
    return {
        "schema_version": "agentblaster.dashboard-review-artifacts.v1",
        "project_root": "<redacted>",
        "project_root_redacted": True,
        "artifact_count": len(artifacts),
        "skipped_items": skipped,
        "artifacts": artifacts,
        "security_notes": [
            "Review artifact index scans only known static artifact directories.",
            "The project root is redacted from the index response.",
            "It excludes raw run paths and raw result logs and returns metadata rather than raw artifact contents.",
            "Only manifest.json inside release qualification zip bundles, publication-bundle-manifest.json inside run publication bundles, and matrix-publication-bundle-manifest.json inside matrix publication bundles are inspected; other zip artifacts are classified by filename and not opened.",
        ],
    }


def dashboard_review_artifact_payload(project_root: Path | None, artifact_path: str) -> dict[str, Any]:
    """Return one small redacted JSON review artifact payload."""

    root = (project_root or Path.cwd()).resolve()
    path = _safe_review_artifact_path(root, artifact_path)
    if path.suffix.lower() != ".json":
        raise ConfigError("dashboard review artifact details are available only for JSON artifacts")
    if path.stat().st_size > REVIEW_ARTIFACT_MAX_JSON_BYTES:
        raise ConfigError("review artifact is too large for dashboard detail view")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"invalid JSON review artifact: {exc}") from exc
    if not isinstance(payload, dict):
        raise ConfigError("review artifact JSON root must be an object")
    artifact = _review_artifact_entry(path, root=root, category=path.relative_to(root).parts[0])
    artifact.pop("root_keys", None)
    artifact.pop("top_level_keys", None)
    return {
        "schema_version": "agentblaster.dashboard-review-artifact-detail.v1",
        "artifact": artifact,
        "payload": _review_artifact_detail_payload(payload),
        "security_notes": [
            "Detail view is restricted to small JSON artifacts in known review directories.",
            "Raw paths, raw result logs, zip bundles, oversized JSON, and path traversal are blocked.",
            "Payload is defensively redacted before dashboard output, including local filesystem paths.",
            "Campaign preflight, publication brief, SDLC manifest, and provider audit details return compact review summaries only.",
        ],
    }


def _review_artifact_detail_payload(payload: dict[str, Any]) -> dict[str, Any]:
    schema = payload.get("schema_version") or payload.get("schema")
    if schema == CAMPAIGN_PREFLIGHT_SCHEMA_VERSION:
        summary = _campaign_preflight_json_review_summary(payload) or {}
        return {
            "schema_version": CAMPAIGN_PREFLIGHT_SCHEMA_VERSION,
            "redacted_for_dashboard_detail": True,
            "campaign_preflight_summaries": [summary] if summary else [],
            "security": {
                "contains_local_paths": False,
                "contains_raw_secrets": False,
                "contains_raw_provider_payloads": False,
                "contains_raw_traces": False,
                "external_publication_safe": True,
            },
        }
    if schema == NORMALIZED_TELEMETRY_SCHEMA_VERSION:
        summary = _normalized_telemetry_json_review_summary(payload) or {}
        return {
            "schema_version": NORMALIZED_TELEMETRY_SCHEMA_VERSION,
            "redacted_for_dashboard_detail": True,
            "normalized_telemetry_summaries": [summary] if summary else [],
            "security": {
                "contains_raw_provider_payloads": False,
                "contains_raw_secrets": False,
                "includes_raw_usage": False,
                "includes_raw_stats": False,
            },
        }
    if schema == PUBLICATION_BRIEF_SCHEMA_VERSION:
        summary = _publication_brief_json_review_summary(payload) or {}
        return {
            "schema_version": PUBLICATION_BRIEF_SCHEMA_VERSION,
            "redacted_for_dashboard_detail": True,
            "publication_brief_summaries": [summary] if summary else [],
            "security": {
                "contains_raw_provider_payloads": bool(summary.get("contains_raw_provider_payloads")),
                "contains_secrets": bool(summary.get("contains_secrets")),
                "includes_proof_point_text": False,
                "includes_disclosure_text": False,
                "includes_source_artifact_payloads": False,
            },
        }
    if schema == SDLC_VALIDATION_MANIFEST_SCHEMA_VERSION:
        summary = _sdlc_validation_manifest_json_review_summary(payload) or {}
        return {
            "schema_version": SDLC_VALIDATION_MANIFEST_SCHEMA_VERSION,
            "redacted_for_dashboard_detail": True,
            "sdlc_validation_manifest_summaries": [summary] if summary else [],
            "security": {
                "contacts_providers": bool(summary.get("contacts_providers")),
                "contains_raw_provider_payloads": bool(summary.get("contains_raw_provider_payloads")),
                "contains_secrets": bool(summary.get("contains_secrets")),
                "includes_command_output": False,
                "includes_raw_test_logs": False,
                "includes_local_paths": False,
            },
        }
    if schema == PROVIDER_AUDIT_SCHEMA_VERSION:
        summary = _provider_audit_json_review_summary(payload) or {}
        return {
            "schema_version": PROVIDER_AUDIT_SCHEMA_VERSION,
            "redacted_for_dashboard_detail": True,
            "provider_audit_summaries": [summary] if summary else [],
            "security": {
                "contacts_providers": False,
                "resolves_secrets": False,
                "reads_keyring_values": False,
                "contains_raw_provider_payloads": False,
                "contains_secrets": False,
                "includes_secret_reference_names": False,
                "includes_finding_messages": False,
            },
        }
    return _redact_detail_local_paths(redact_value(payload))


def _redact_detail_local_paths(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _redact_detail_local_paths(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_detail_local_paths(item) for item in value]
    if isinstance(value, str) and _looks_like_detail_local_path(value):
        return "<redacted-path>"
    return value


def _looks_like_detail_local_path(value: str) -> bool:
    normalized = value.strip().replace("\\", "/")
    if normalized.startswith(("/", "~/")):
        return True
    return len(normalized) >= 3 and normalized[1] == ":" and normalized[2] == "/"


def dashboard_setup_status(policy: SecurityPolicy | None = None) -> dict[str, Any]:
    providers = ProviderStore().list()
    active_policy = policy or load_policy(None)
    provider_audit = audit_providers(providers, active_policy).model_dump(mode="json")
    return {
        "schema_version": "agentblaster.dashboard-setup-status.v1",
        "summary": {
            "providers": provider_audit["total_providers"],
            "remote_providers": provider_audit["remote_providers"],
            "policy_ok": provider_audit["policy_ok"],
            "errors": provider_audit["errors"],
            "warnings": provider_audit["warnings"],
            "missing_api_key_refs": sum(
                1 for provider in provider_audit["providers"] if provider["remote"] and not provider["api_key_ref_configured"]
            ),
            "insecure_tls_providers": sum(1 for provider in provider_audit["providers"] if not provider["tls_verify"]),
        },
        "policy_controls": provider_audit["policy_controls"],
        "secret_backend_posture": provider_audit["secret_backend_posture"],
        "auth_setup": _dashboard_auth_setup_status(active_policy, policy_configured=policy is not None),
        "providers": provider_audit["providers"],
        "security_notes": [
            "Setup status is static and does not contact endpoints, resolve API keys, read environment variables, or inspect keyring values.",
            "Secret references are summarized by backend kind only; raw secret names and values are excluded.",
            "Auth setup posture records backend capability and policy allowance only; it does not test, read, or return secret values.",
            "Remote execution remains blocked by launch policy unless the operator explicitly allows remote providers.",
        ],
    }


def _dashboard_auth_setup_status(policy: SecurityPolicy, *, policy_configured: bool) -> dict[str, Any]:
    methods = [
        _dashboard_auth_method(
            method="env",
            label="Environment variable reference",
            available=True,
            policy=policy,
            stores_secret=False,
            accepts_raw_api_key=False,
            writable_backend=False,
            plaintext_fallback=False,
            enterprise_recommended=True,
            note="Stores only env:VAR in provider config; set the secret in shell, CI, or enterprise secret manager.",
        ),
        _dashboard_auth_method(
            method="keyring",
            label="OS keyring / Apple Keychain",
            available=find_spec("keyring") is not None,
            policy=policy,
            stores_secret=True,
            accepts_raw_api_key=True,
            writable_backend=True,
            plaintext_fallback=False,
            enterprise_recommended=True,
            note=(
                "Accepts raw API-key entry only to write through Python keyring; on macOS this normally maps to Apple Keychain, "
                "while Linux and Windows depend on the configured OS backend."
            ),
        ),
        _dashboard_auth_method(
            method="dotenv",
            label="Plaintext dotenv fallback",
            available=True,
            policy=policy,
            stores_secret=True,
            accepts_raw_api_key=True,
            writable_backend=True,
            plaintext_fallback=True,
            enterprise_recommended=False,
            note="Requires explicit plaintext acknowledgment and should be restricted to approved local development.",
        ),
    ]
    usable = [method for method in methods if method["available"] and method["policy_allowed"]]
    recommended = next((method["method"] for method in usable if method["method"] == "keyring"), None)
    if recommended is None:
        recommended = next((method["method"] for method in usable if method["method"] == "env"), None)
    if recommended is None:
        recommended = next((method["method"] for method in usable), None)
    return {
        "policy_configured": policy_configured,
        "recommended_method": recommended,
        "raw_api_key_entry_methods": [
            method["method"]
            for method in usable
            if method["accepts_raw_api_key"] and not method["plaintext_fallback"]
        ],
        "plaintext_fallback_methods": [method["method"] for method in usable if method["plaintext_fallback"]],
        "methods": methods,
        "security": {
            "provider_config_stores_secret_values": False,
            "setup_status_reads_secret_values": False,
            "raw_api_keys_echoed": False,
            "env_secrets_deleted_by_agentblaster": False,
            "keyring_optional": True,
        },
    }


def _dashboard_auth_method(
    *,
    method: str,
    label: str,
    available: bool,
    policy: SecurityPolicy,
    stores_secret: bool,
    accepts_raw_api_key: bool,
    writable_backend: bool,
    plaintext_fallback: bool,
    enterprise_recommended: bool,
    note: str,
) -> dict[str, Any]:
    policy_allowed = policy.allowed_secret_ref_kinds is None or method in policy.allowed_secret_ref_kinds
    return {
        "method": method,
        "label": label,
        "available": available,
        "policy_allowed": policy_allowed,
        "blocked_by_policy": not policy_allowed,
        "stores_secret": stores_secret,
        "accepts_raw_api_key": accepts_raw_api_key,
        "writable_backend": writable_backend,
        "plaintext_fallback": plaintext_fallback,
        "enterprise_recommended": enterprise_recommended,
        "requires_plaintext_ack": plaintext_fallback,
        "note": note,
    }


def dashboard_catalog_index() -> dict[str, Any]:
    return {
        "schema_version": "agentblaster.dashboard-catalog-index.v1",
        "catalogs": [
            {"id": "providers", "href": "/api/providers", "description": "Redacted configured provider profiles."},
            {"id": "setup-status", "href": "/api/setup-status", "description": "Redacted provider setup, policy, auth, and TLS readiness."},
            {"id": "suites", "href": "/api/suites", "description": "Built-in benchmark suite metadata."},
            {"id": "models", "href": "/api/models", "description": "Canonical model targets for comparable matrices."},
            {"id": "engine-targets", "href": "/api/engine-targets", "description": "Standardized engine target planning metadata."},
            {"id": "local-engine-onboarding", "href": "/api/local-engine-onboarding", "description": "Static local-engine preset, launch, target, workflow, and telemetry setup checklist."},
            {"id": "workflow-surfaces", "href": "/api/workflow-surfaces", "description": "Tool, MCP, skill, LCP, and harness-engineering surfaces."},
            {"id": "telemetry-mappings", "href": "/api/telemetry-mappings", "description": "Raw-to-normalized telemetry mapping catalog."},
            {"id": "review-artifacts", "href": "/api/review-artifacts", "description": "Redaction-safe index of evidence, gate, audit, advisory, and release artifacts."},
            {"id": "campaign-preview", "href": "/api/campaign-preview", "description": "No-write canonical campaign plan preview."},
            {"id": "run-plan", "href": "/api/run-plan", "description": "No-dispatch benchmark launch preview with policy enforcement."},
            {"id": "run-launch", "href": "/api/runs", "description": "Policy-gated benchmark launch endpoint that dispatches provider requests."},
            {"id": "runs", "href": "/api/runs", "description": "Completed run summaries."},
            {"id": "run-events", "href": "/api/runs/<run-id>/events", "description": "Redacted per-run lifecycle timeline events."},
        ],
    }


def dashboard_catalog_payload(
    catalog_id: str,
    *,
    project_root: Path,
    policy: SecurityPolicy | None = None,
    query: dict[str, list[str]] | None = None,
) -> tuple[dict[str, Any], str]:
    if catalog_id == "providers":
        return {"providers": dashboard_providers()}, "/api/providers"
    if catalog_id == "setup-status":
        return dashboard_setup_status(policy=policy), "/api/setup-status"
    if catalog_id == "suites":
        return {"suites": dashboard_suites()}, "/api/suites"
    if catalog_id == "models":
        return dashboard_model_targets(), "/api/models"
    if catalog_id == "engine-targets":
        return dashboard_engine_targets(), "/api/engine-targets"
    if catalog_id == "local-engine-onboarding":
        return dashboard_local_engine_onboarding(), "/api/local-engine-onboarding"
    if catalog_id == "workflow-surfaces":
        return dashboard_workflow_surfaces(), "/api/workflow-surfaces"
    if catalog_id == "telemetry-mappings":
        return dashboard_telemetry_mappings(), "/api/telemetry-mappings"
    if catalog_id == "review-artifacts":
        return dashboard_review_artifacts(project_root), "/api/review-artifacts"
    if catalog_id == "campaign-preview":
        return dashboard_campaign_preview(query), "/api/campaign-preview"
    if catalog_id == "run-plan":
        return {
            "schema_version": "agentblaster.dashboard-run-plan-endpoint.v1",
            "method": "POST",
            "description": "Submit provider, suite, model, raw_traces, concurrency, allow_remote, and optional capability_preflight to build a no-dispatch run plan.",
            "safety": {
                "dispatches_requests": False,
                "contacts_provider": False,
                "resolves_secrets": False,
                "writes_run_artifacts": False,
                "policy_enforced": True,
            },
            "ui": {"form": "/", "submit": "Preview plan"},
        }, "/api/run-plan"
    if catalog_id == "run-launch":
        return {
            "schema_version": "agentblaster.dashboard-run-launch-endpoint.v1",
            "method": "POST",
            "description": "Policy-gated benchmark launch endpoint that dispatches provider requests and writes run artifacts.",
            "safety": {
                "dispatches_requests": True,
                "contacts_provider": True,
                "resolves_secrets": True,
                "writes_run_artifacts": True,
                "policy_enforced": True,
            },
            "ui": {"form": "/", "submit": "Launch"},
        }, "/api/runs"
    if catalog_id == "runs":
        return {"runs": list_dashboard_runs(project_root / "runs")}, "/api/runs"
    raise ConfigError(f"unknown catalog: {catalog_id}")


def render_dashboard_catalog_html(
    catalog_id: str,
    *,
    project_root: Path,
    policy: SecurityPolicy | None = None,
    query: dict[str, list[str]] | None = None,
) -> str:
    index = dashboard_catalog_index()
    catalog = next((item for item in index["catalogs"] if item["id"] == catalog_id), None)
    if catalog is None:
        raise ConfigError(f"unknown catalog: {catalog_id}")
    payload, api_href = dashboard_catalog_payload(catalog_id, project_root=project_root, policy=policy, query=query)
    title = catalog_id.replace("-", " ").title()
    description = str(catalog.get("description") or "")
    summary = _catalog_summary_cards(payload)
    sections = _catalog_detail_sections(payload)
    raw_json = html.escape(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentBlaster Catalog - {html.escape(title)}</title>
  <style>
    :root {{
      --ink: #111915;
      --muted: #637066;
      --paper: #fffdf4;
      --card: rgba(255, 255, 255, 0.72);
      --line: #d8cdb8;
      --accent: #a45c2a;
      --accent-dark: #70411f;
      --shadow: 0 24px 70px rgba(47, 35, 18, 0.16);
    }}
    body {{ background: radial-gradient(circle at top left, #f7ecd2, #f7f4e9 45%, #ece1cc); color: var(--ink); font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; }}
    main {{ margin: 0 auto; max-width: 1180px; padding: 42px 26px 70px; }}
    a {{ color: var(--accent-dark); font-weight: 800; }}
    .crumb {{ margin-bottom: 22px; }}
    .hero, .panel {{ background: var(--paper); border: 1px solid var(--line); border-radius: 28px; box-shadow: var(--shadow); padding: 28px; }}
    .hero {{ margin-bottom: 26px; }}
    .kicker {{ color: var(--accent); font-size: 12px; font-weight: 900; letter-spacing: 0.15em; text-transform: uppercase; }}
    h1 {{ font-family: Georgia, serif; font-size: clamp(42px, 6vw, 78px); line-height: 0.94; margin: 10px 0 16px; }}
    h2 {{ font-size: 26px; margin: 0 0 14px; }}
    .description {{ color: var(--muted); font-size: 20px; line-height: 1.5; max-width: 800px; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 12px; margin-top: 22px; }}
    .button {{ background: var(--ink); border-radius: 999px; color: white; display: inline-block; padding: 10px 16px; text-decoration: none; }}
    .button.secondary {{ background: transparent; border: 1px solid var(--line); color: var(--ink); }}
    .summary-grid {{ display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); margin: 24px 0; }}
    .summary-card {{ background: var(--card); border: 1px solid var(--line); border-radius: 18px; padding: 16px; }}
    .summary-card strong {{ display: block; font-size: 24px; margin-top: 6px; }}
    .summary-card span {{ color: var(--muted); font-size: 13px; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 11px 10px; text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; }}
    code, pre {{ background: rgba(17,25,21,0.06); border-radius: 14px; }}
    code {{ padding: 2px 6px; }}
    pre {{ max-height: 560px; overflow: auto; padding: 18px; white-space: pre-wrap; }}
    details {{ margin-top: 22px; }}
    summary {{ cursor: pointer; font-weight: 900; }}
    .panel + .panel {{ margin-top: 22px; }}
    @media (max-width: 760px) {{ main {{ padding: 24px 14px; }} .panel {{ overflow-x: auto; }} }}
  </style>
</head>
<body>
  <main>
    <div class="crumb"><a href="/">Back to dashboard</a></div>
    <section class="hero" data-testid="catalog-detail-page">
      <div class="kicker">Planning catalog</div>
      <h1>{html.escape(title)}</h1>
      <p class="description">{html.escape(description)}</p>
      <div class="actions">
        <a class="button" href="{html.escape(api_href)}">Open JSON API</a>
        <a class="button secondary" href="/">Use dashboard controls</a>
      </div>
    </section>
    <section class="panel">
      <h2>Summary</h2>
      <div class="summary-grid">{summary}</div>
    </section>
    {sections}
    <section class="panel">
      <details>
        <summary>Show raw JSON payload</summary>
        <pre data-testid="catalog-json-preview">{raw_json}</pre>
      </details>
    </section>
  </main>
</body>
</html>
"""


def _catalog_summary_cards(payload: dict[str, Any]) -> str:
    cards: list[tuple[str, str]] = []
    schema = payload.get("schema_version") or payload.get("schema") or payload.get("report_type")
    if schema:
        cards.append(("Schema", str(schema)))
    for key, value in payload.items():
        if isinstance(value, list):
            cards.append((key.replace("_", " ").title(), str(len(value))))
        elif isinstance(value, dict):
            cards.append((key.replace("_", " ").title(), str(len(value))))
        elif isinstance(value, (bool, int, float, str)) and len(cards) < 6:
            cards.append((key.replace("_", " ").title(), str(value)))
    if not cards:
        cards.append(("Payload", "available"))
    return "\n".join(
        f'<div class="summary-card"><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong></div>'
        for label, value in cards[:8]
    )


def _catalog_detail_sections(payload: dict[str, Any]) -> str:
    sections: list[str] = []
    scalar_rows = [
        (key, value)
        for key, value in payload.items()
        if not isinstance(value, (dict, list))
    ]
    if scalar_rows:
        sections.append(_catalog_key_value_section("Overview", scalar_rows))
    for key, value in payload.items():
        if isinstance(value, list):
            sections.append(_catalog_list_section(key, value))
        elif isinstance(value, dict):
            nested_scalar_rows = [
                (nested_key, nested_value)
                for nested_key, nested_value in value.items()
                if not isinstance(nested_value, (dict, list))
            ]
            if nested_scalar_rows:
                sections.append(_catalog_key_value_section(key.replace("_", " ").title(), nested_scalar_rows))
    return "\n".join(sections)


def _catalog_key_value_section(title: str, rows: list[tuple[str, Any]]) -> str:
    body = "\n".join(
        f"<tr><th>{html.escape(str(key).replace('_', ' ').title())}</th><td>{_catalog_cell(value)}</td></tr>"
        for key, value in rows[:24]
    )
    return f"""
    <section class="panel">
      <h2>{html.escape(title)}</h2>
      <table><tbody>{body}</tbody></table>
    </section>
    """


def _catalog_list_section(title: str, rows: list[Any]) -> str:
    if not rows:
        return f"""
    <section class="panel">
      <h2>{html.escape(title.replace('_', ' ').title())}</h2>
      <p class="description">No entries.</p>
    </section>
    """
    dict_rows = [row for row in rows if isinstance(row, dict)]
    if not dict_rows:
        body = "\n".join(f"<tr><td>{_catalog_cell(row)}</td></tr>" for row in rows[:40])
        return f"""
    <section class="panel">
      <h2>{html.escape(title.replace('_', ' ').title())}</h2>
      <table><tbody>{body}</tbody></table>
    </section>
    """
    columns = _catalog_columns(dict_rows)
    header = "".join(f"<th>{html.escape(column.replace('_', ' ').title())}</th>" for column in columns)
    body = "\n".join(
        "<tr>" + "".join(f"<td>{_catalog_cell(row.get(column))}</td>" for column in columns) + "</tr>"
        for row in dict_rows[:40]
    )
    return f"""
    <section class="panel">
      <h2>{html.escape(title.replace('_', ' ').title())}</h2>
      <table>
        <thead><tr>{header}</tr></thead>
        <tbody>{body}</tbody>
      </table>
    </section>
    """


def _catalog_columns(rows: list[dict[str, Any]]) -> list[str]:
    preferred = [
        "id",
        "name",
        "title",
        "provider",
        "contract",
        "suite",
        "model",
        "status",
        "schema_version",
        "description",
        "href",
    ]
    keys: list[str] = []
    for key in preferred:
        if any(key in row for row in rows):
            keys.append(key)
    for row in rows:
        for key, value in row.items():
            if key not in keys and not isinstance(value, (dict, list)):
                keys.append(key)
            if len(keys) >= 7:
                return keys
    return keys[:7] or sorted(str(key) for key in rows[0].keys())[:7]


def _catalog_cell(value: Any) -> str:
    if value is None:
        return '<span class="meta">none</span>'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return html.escape(str(value))
    if isinstance(value, str):
        text = value if len(value) <= 220 else value[:217] + "..."
        return html.escape(text)
    compact = json.dumps(value, sort_keys=True, default=str)
    if len(compact) > 220:
        compact = compact[:217] + "..."
    return f"<code>{html.escape(compact)}</code>"


def dashboard_campaign_preview(query: dict[str, list[str]] | None = None) -> dict[str, Any]:
    query = query or {}
    providers = _query_csv(query, "providers")
    targets = _query_csv(query, "targets")
    suites = _query_csv(query, "suites")
    output_dir = Path(_query_value(query, "output_dir") or "campaigns/qwen-gemma-local")
    policy_value = _query_value(query, "policy")
    name = _query_value(query, "name")
    concurrency_value = _query_value(query, "concurrency")
    try:
        concurrency = int(concurrency_value) if concurrency_value else 1
        return campaign_plan_preview(
            output_dir=output_dir,
            providers=providers,
            targets=targets,
            suites=suites,
            concurrency=concurrency,
            policy=Path(policy_value) if policy_value else None,
            name=name,
        )
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc


def dashboard_run_plan(
    payload: dict[str, Any],
    *,
    audit_log: Path | None = None,
    policy: SecurityPolicy | None = None,
) -> dict[str, Any]:
    provider_name = str(payload.get("engine") or payload.get("provider") or "").strip()
    if not provider_name:
        raise ConfigError("run preview requires provider or engine")
    suite_name = str(payload.get("suite") or "smoke").strip()
    model = str(payload.get("model") or "").strip()
    try:
        concurrency = int(payload.get("concurrency") or 1)
    except (TypeError, ValueError) as exc:
        raise ConfigError("run preview concurrency must be an integer") from exc
    if concurrency < 1:
        raise ConfigError("run preview concurrency must be at least 1")
    try:
        raw_trace_mode = (
            RawTraceMode.OFF
            if _truthy(payload.get("no_raw_traces"))
            else RawTraceMode(str(payload.get("raw_traces") or RawTraceMode.REDACTED.value))
        )
    except ValueError as exc:
        allowed = ", ".join(mode.value for mode in RawTraceMode)
        raise ConfigError(f"raw trace mode must be one of: {allowed}") from exc
    allow_remote = _truthy(payload.get("allow_remote"))
    capability_preflight = _payload_bool(payload, "capability_preflight", default=True)
    strict_unknown_capabilities = _truthy(payload.get("strict_unknown_capabilities"))

    provider = ProviderStore().get(provider_name)
    suite = get_builtin_suite(suite_name)
    active_policy = _dashboard_request_policy(policy, allow_remote=allow_remote)
    try:
        enforce_provider_policy(
            provider,
            active_policy,
            raw_trace_mode=raw_trace_mode,
            concurrency=concurrency,
            suite=suite,
        )
    except PolicyError as exc:
        raise ConfigError(str(exc)) from exc
    capability_report = (
        check_suite_compatibility(provider, suite, strict_unknown=strict_unknown_capabilities)
        if capability_preflight
        else None
    )
    if capability_report is not None and not capability_report.compatible:
        raise ConfigError(format_capability_report(capability_report))
    resolved_model = model or provider.default_model
    if not resolved_model:
        raise ConfigError("model is required when provider has no default_model")
    plan = build_run_plan(
        provider=provider,
        suite=suite,
        model=resolved_model,
        raw_trace_mode=raw_trace_mode,
        concurrency=concurrency,
        capability_report=capability_report,
    )
    AuditLogger(audit_log).emit(
        "run_plan_previewed",
        source="dashboard",
        provider=provider.name,
        suite=suite.name,
        model=resolved_model,
        remote=provider.remote,
        allow_remote=allow_remote,
        raw_trace_mode=raw_trace_mode.value,
        concurrency=concurrency,
        total_cases=plan.total_cases,
        dispatches_requests=False,
        writes_run_artifacts=False,
    )
    return {
        "schema_version": "agentblaster.dashboard-run-plan.v1",
        "safety": {
            "preview_only": True,
            "dispatches_requests": False,
            "contacts_provider": False,
            "resolves_secrets": False,
            "writes_run_artifacts": False,
            "policy_enforced": True,
            "capability_preflight": capability_preflight,
            "strict_unknown_capabilities": strict_unknown_capabilities,
            "capability_compatible": capability_report.compatible if capability_report is not None else None,
            "capability_missing": [finding.key for finding in capability_report.missing] if capability_report else [],
            "capability_unknown": [finding.key for finding in capability_report.unknown] if capability_report else [],
        },
        "plan": plan.model_dump(mode="json"),
    }


def launch_dashboard_run(
    runs_dir: Path,
    payload: dict[str, Any],
    *,
    audit_log: Path | None = None,
    policy: SecurityPolicy | None = None,
) -> dict[str, Any]:
    provider_name = str(payload.get("engine") or payload.get("provider") or "").strip()
    if not provider_name:
        raise ConfigError("run launch requires provider or engine")
    suite_name = str(payload.get("suite") or "smoke").strip()
    model = str(payload.get("model") or "").strip()
    try:
        concurrency = int(payload.get("concurrency") or 1)
    except (TypeError, ValueError) as exc:
        raise ConfigError("run launch concurrency must be an integer") from exc
    if concurrency < 1:
        raise ConfigError("run launch concurrency must be at least 1")
    try:
        raw_trace_mode = (
            RawTraceMode.OFF
            if _truthy(payload.get("no_raw_traces"))
            else RawTraceMode(str(payload.get("raw_traces") or RawTraceMode.REDACTED.value))
        )
    except ValueError as exc:
        allowed = ", ".join(mode.value for mode in RawTraceMode)
        raise ConfigError(f"raw trace mode must be one of: {allowed}") from exc
    allow_remote = _truthy(payload.get("allow_remote"))
    capability_preflight = _payload_bool(payload, "capability_preflight", default=True)
    strict_unknown_capabilities = _truthy(payload.get("strict_unknown_capabilities"))
    model_metadata = _payload_model_metadata(payload.get("model_metadata"))

    provider = ProviderStore().get(provider_name)
    suite = get_builtin_suite(suite_name)
    active_policy = _dashboard_request_policy(policy, allow_remote=allow_remote)
    try:
        enforce_provider_policy(
            provider,
            active_policy,
            raw_trace_mode=raw_trace_mode,
            concurrency=concurrency,
            suite=suite,
        )
    except PolicyError as exc:
        raise ConfigError(str(exc)) from exc
    capability_report = None
    if capability_preflight:
        capability_report = check_suite_compatibility(provider, suite, strict_unknown=strict_unknown_capabilities)
        AuditLogger(audit_log).emit(
            "dashboard_capability_preflight",
            source="dashboard",
            provider=provider.name,
            suite=suite.name,
            compatible=capability_report.compatible,
            strict_unknown=strict_unknown_capabilities,
            missing=[finding.key for finding in capability_report.missing],
            unknown=[finding.key for finding in capability_report.unknown],
        )
        if not capability_report.compatible:
            raise ConfigError(format_capability_report(capability_report))
    resolved_model = model or provider.default_model
    if not resolved_model:
        raise ConfigError("model is required when provider has no default_model")
    AuditLogger(audit_log).emit(
        "dashboard_run_launch_requested",
        source="dashboard",
        provider=provider.name,
        suite=suite.name,
        model=resolved_model,
        remote=provider.remote,
        allow_remote=allow_remote,
        raw_trace_mode=raw_trace_mode.value,
        concurrency=concurrency,
        capability_preflight=capability_preflight,
        strict_unknown_capabilities=strict_unknown_capabilities,
        dispatches_requests=True,
        writes_run_artifacts=True,
    )
    summary = BenchmarkRunner(
        provider,
        suite,
        output_dir=runs_dir,
        raw_trace_mode=raw_trace_mode,
        concurrency=concurrency,
    ).run(model=resolved_model, model_metadata=model_metadata)
    AuditLogger(audit_log).emit(
        "dashboard_run_launched",
        source="dashboard",
        run_id=summary.run_id,
        provider=summary.provider,
        suite=summary.suite,
        model=summary.model,
        passed=summary.passed,
        failed=summary.failed,
        concurrency=summary.concurrency,
    )
    return {
        "schema_version": "agentblaster.dashboard-run-launch.v1",
        "safety": {
            "preview_only": False,
            "dispatches_requests": True,
            "contacts_provider": True,
            "resolves_secrets": provider.api_key_ref is not None,
            "writes_run_artifacts": True,
            "policy_enforced": True,
            "capability_preflight": capability_preflight,
            "strict_unknown_capabilities": strict_unknown_capabilities,
        },
        "summary": summary.model_dump(mode="json"),
        "artifacts": {
            "manifest": "manifest.json",
            "suite": "suite.json",
            "results": "results.jsonl",
            "summary": "summary.json",
            "events": "events.jsonl",
            "integrity": "integrity.json",
        },
    }


def _dashboard_request_policy(policy: SecurityPolicy | None, *, allow_remote: bool) -> SecurityPolicy:
    active_policy = policy or load_policy(None)
    if allow_remote:
        return active_policy
    return active_policy.model_copy(update={"allow_remote_providers": False})


def render_dashboard_html(runs_dir: Path, *, auth_required: bool = False) -> str:
    runs = list_dashboard_runs(runs_dir)
    rows = "\n".join(_run_row(run) for run in runs)
    launch_panel = _launch_panel()
    provider_setup_panel = _provider_setup_panel()
    provider_auth_panel = _provider_auth_panel()
    catalog_panel = _catalog_panel()
    review_panel = _review_artifacts_panel(_dashboard_project_root(runs_dir))
    posture_panel = _security_posture_panel(runs, auth_required=auth_required)
    auth_notice = (
        '<p class="kicker" data-testid="auth-status">Dashboard token authentication enabled</p>'
        if auth_required
        else ""
    )
    empty_state = ""
    if not rows:
        empty_state = """
        <section class="empty" data-testid="empty-state">
          <p>No AgentBlaster runs were found in this directory.</p>
        </section>
        """
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentBlaster Dashboard</title>
  <style>
    :root {{
      --ink: #111713;
      --muted: #647067;
      --paper: #f5efe4;
      --card: rgba(255, 252, 245, 0.86);
      --line: #d7cbb7;
      --accent: #d66b1f;
      --accent-dark: #70340e;
      --good: #156c43;
      --bad: #9b2721;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      font-family: "Avenir Next", "Trebuchet MS", "Gill Sans", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(214, 107, 31, 0.22), transparent 34rem),
        linear-gradient(135deg, #fff8ec 0%, var(--paper) 48%, #dfe7d9 100%);
      min-height: 100vh;
    }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 40px 20px 64px; }}
    .hero {{
      display: grid;
      grid-template-columns: 1.3fr 0.7fr;
      gap: 24px;
      align-items: end;
      margin-bottom: 28px;
    }}
    h1 {{
      font-family: "Iowan Old Style", "Palatino", serif;
      font-size: clamp(42px, 8vw, 86px);
      line-height: 0.9;
      margin: 0;
      letter-spacing: -0.06em;
    }}
    .kicker {{ color: var(--accent-dark); font-weight: 800; letter-spacing: 0.14em; text-transform: uppercase; }}
    .posture {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin: 18px 0 26px; }}
    .posture-card {{ border: 1px solid var(--line); border-radius: 18px; padding: 14px 16px; background: var(--card); box-shadow: 0 10px 32px rgba(42, 31, 18, 0.08); }}
    .posture-card strong {{ display: block; font-size: 22px; margin: 2px 0 4px; }}
    .posture-card span {{ color: var(--muted); font-size: 13px; line-height: 1.35; }}
    .posture-card.good {{ border-color: rgba(21, 108, 67, 0.35); }}
    .posture-card.warn {{ border-color: rgba(155, 39, 33, 0.36); }}
    .subhead {{ color: var(--muted); max-width: 620px; font-size: 18px; line-height: 1.5; }}
    .panel {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 28px;
      box-shadow: 0 24px 70px rgba(76, 53, 25, 0.14);
      overflow: hidden;
      backdrop-filter: blur(12px);
    }}
    .launch {{
      padding: 22px;
      margin-bottom: 24px;
    }}
    .launch h2 {{ margin: 0 0 14px; font-family: "Iowan Old Style", "Palatino", serif; font-size: 32px; }}
    .catalog {{ padding: 22px; margin-bottom: 24px; }}
    .catalog h2 {{ margin: 0 0 8px; font-family: "Iowan Old Style", "Palatino", serif; font-size: 32px; }}
    .catalog-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 10px; margin-top: 16px; }}
    .catalog-card {{ border: 1px solid var(--line); border-radius: 18px; color: var(--ink); padding: 13px 14px; text-decoration: none; background: rgba(255,255,255,0.44); }}
    .catalog-card strong {{ display: block; margin-bottom: 4px; }}
    .catalog-card span {{ color: var(--muted); font-size: 13px; line-height: 1.35; }}
    form {{ display: grid; grid-template-columns: repeat(6, minmax(120px, 1fr)); gap: 12px; align-items: end; }}
    label {{ color: var(--accent-dark); display: grid; font-size: 12px; font-weight: 800; gap: 6px; letter-spacing: 0.08em; text-transform: uppercase; }}
    input, select {{
      border: 1px solid var(--line);
      border-radius: 14px;
      color: var(--ink);
      font: inherit;
      padding: 10px 11px;
      width: 100%;
      background: rgba(255,255,255,0.7);
    }}
    .check {{ align-items: center; display: flex; gap: 8px; letter-spacing: 0; text-transform: none; }}
    .check input {{ width: auto; }}
    button {{
      background: var(--ink);
      border: 0;
      border-radius: 16px;
      color: white;
      cursor: pointer;
      font: inherit;
      font-weight: 900;
      padding: 12px 16px;
    }}
    .links {{ display: flex; flex-wrap: wrap; gap: 7px; }}
    .links a {{
      background: rgba(112, 52, 14, 0.1);
      border: 1px solid rgba(112, 52, 14, 0.18);
      border-radius: 999px;
      color: var(--accent-dark);
      font-size: 12px;
      font-weight: 800;
      padding: 5px 9px;
      text-decoration: none;
    }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ padding: 15px 16px; text-align: left; border-bottom: 1px solid rgba(215, 203, 183, 0.78); }}
    th {{ color: var(--accent-dark); font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; }}
    tr:last-child td {{ border-bottom: 0; }}
    .run-id {{ font-weight: 800; }}
    .meta {{ color: var(--muted); font-size: 13px; margin-top: 3px; }}
    .status {{ border-radius: 999px; color: white; display: inline-block; font-weight: 800; padding: 6px 10px; }}
    .status.pass {{ background: var(--good); }}
    .status.fail {{ background: var(--bad); }}
    .status.review {{ background: var(--accent-dark); }}
    .empty {{ background: var(--card); border: 1px dashed var(--line); border-radius: 24px; padding: 28px; }}
    @media (max-width: 760px) {{
      .hero {{ grid-template-columns: 1fr; }}
      form {{ grid-template-columns: 1fr; }}
      .panel {{ overflow-x: auto; }}
      th, td {{ white-space: nowrap; }}
    }}
  </style>
</head>
<body>
  <main>
    {auth_notice}
    {posture_panel}
    <section class="hero">
      <div>
        <div class="kicker">Local agentic benchmark control</div>
        <h1>AgentBlaster</h1>
      </div>
      <p class="subhead">
        Browse completed runs, compare health signals, and inspect normalized telemetry without exposing raw traces.
      </p>
    </section>
    {launch_panel}
    {provider_setup_panel}
    {provider_auth_panel}
    {catalog_panel}
    {review_panel}
    {empty_state}
    <section class="panel" data-testid="runs-panel">
      <table data-testid="runs-table">
        <thead>
          <tr>
            <th>Run</th>
            <th>Status</th>
            <th>Provider</th>
            <th>Adapter</th>
            <th>Model</th>
            <th>Suite</th>
            <th>Provenance</th>
            <th>Suite SHA</th>
            <th>Cases</th>
            <th>Req/s</th>
            <th>Cost</th>
            <th>Avg queue</th>
            <th>Rate wait</th>
            <th>Avg latency</th>
            <th>Avg TTFT</th>
            <th>Decode tok/s</th>
            <th>Reports</th>
          </tr>
        </thead>
        <tbody>
          {rows}
        </tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""


def _dashboard_project_root(runs_dir: Path) -> Path:
    return runs_dir.parent if runs_dir.name == "runs" else runs_dir


def _review_artifacts_panel(project_root: Path) -> str:
    payload = dashboard_review_artifacts(project_root)
    artifacts = payload.get("artifacts") or []
    rows = "\n".join(_review_artifact_row(artifact) for artifact in artifacts[:12])
    if not rows:
        rows = '<tr><td colspan="5">No review artifacts found.</td></tr>'
    return f"""
    <section class="panel catalog" data-testid="review-artifacts-panel">
      <h2>Review evidence</h2>
      <p class="meta">Redaction-safe evidence index. Release bundles expose compact gate summaries; publication bundles expose readiness and security summaries when present.</p>
      <table data-testid="review-artifacts-table">
        <thead>
          <tr>
            <th>Artifact</th>
            <th>Status</th>
            <th>Schema</th>
            <th>Category</th>
            <th>Review summary</th>
          </tr>
        </thead>
        <tbody>
          {rows}
        </tbody>
      </table>
    </section>
    """


def _review_artifact_row(artifact: dict[str, Any]) -> str:
    path = html.escape(str(artifact.get("path") or "unknown"))
    name = html.escape(str(artifact.get("name") or path))
    href = artifact.get("href")
    artifact_label = (
        f'<a href="{html.escape(str(href))}" data-testid="review-artifact-link">{name}</a>'
        if href
        else name
    )
    status = html.escape(str(artifact.get("status") or "unknown"))
    status_class = "pass" if status == "pass" else "fail" if status == "fail" else "review"
    schema = html.escape(str(artifact.get("schema") or "unknown"))
    category = html.escape(str(artifact.get("category") or "unknown"))
    summary = html.escape(_review_artifact_summary_text(artifact))
    return f"""<tr data-testid="review-artifact-row">
  <td>{artifact_label}<div class="meta">{path}</div></td>
  <td><span class="status {status_class}">{status}</span></td>
  <td>{schema}</td>
  <td>{category}</td>
  <td>{summary}</td>
</tr>"""


def _review_artifact_summary_text(artifact: dict[str, Any]) -> str:
    parts = []
    protocol_repair_summaries = artifact.get("protocol_repair_posture_summaries")
    if isinstance(protocol_repair_summaries, list):
        for summary in protocol_repair_summaries[:3]:
            if not isinstance(summary, dict):
                continue
            label = str(summary.get("name") or summary.get("archive_path") or "protocol repair")
            label += (
                f": ready={str(summary.get('ready')).lower()}, "
                f"scorecard={summary.get('scorecard_tool_parser_repairs_valid', 0)}/"
                f"{summary.get('scorecard_tool_parser_repair_cases', 0)}, "
                f"gate={summary.get('matrix_gate_tool_parser_repairs_valid', 0)}/"
                f"{summary.get('matrix_gate_tool_parser_repair_cases', 0)}"
            )
            parts.append(label)
    workflow_readiness_summaries = artifact.get("workflow_readiness_summaries")
    if isinstance(workflow_readiness_summaries, list):
        for summary in workflow_readiness_summaries[:3]:
            if not isinstance(summary, dict):
                continue
            label = str(summary.get("name") or summary.get("archive_path") or "workflow readiness")
            label += (
                f": ready={str(summary.get('ready')).lower()}, "
                f"surfaces={summary.get('covered_required_surface_count', 0)}/"
                f"{summary.get('required_surface_count', 0)}, gaps={summary.get('gap_count', 0)}"
            )
            parts.append(label)
    security_posture_summaries = artifact.get("security_posture_summaries")
    if isinstance(security_posture_summaries, list):
        for summary in security_posture_summaries[:3]:
            if not isinstance(summary, dict):
                continue
            label = str(summary.get("name") or summary.get("archive_path") or "security posture")
            label += (
                f": ready={str(summary.get('ready')).lower()}, "
                f"blockers={summary.get('blockers', 0)}, warnings={summary.get('warnings', 0)}, "
                f"redaction={summary.get('redaction_finding_count', 0)}"
            )
            parts.append(label)
    summaries = artifact.get("matrix_gate_review_summaries")
    if isinstance(summaries, list):
        for summary in summaries[:3]:
            if not isinstance(summary, dict):
                continue
            label = str(summary.get("matrix_name") or summary.get("archive_path") or "matrix gate")
            failure_classes = _failure_class_summary_text(summary.get("failure_class_summary"))
            if failure_classes != "none":
                label += f": {failure_classes}"
            tool_loop_stops = _tool_loop_stop_summary_text(summary.get("tool_loop_stop_summary"))
            if tool_loop_stops != "none":
                label += f"; tool loops: {tool_loop_stops}"
            parser_cases = summary.get("tool_parser_repair_cases")
            if isinstance(parser_cases, int) and parser_cases:
                label += (
                    f"; parser repair: {summary.get('tool_parser_repairs_valid', 0)}/{parser_cases}, "
                    f"invalid tools: {summary.get('invalid_tool_call_count', 0)}"
                )
            gate_count = summary.get("failure_class_gate_count")
            if isinstance(gate_count, int) and gate_count:
                label += f" ({gate_count} class gate finding(s))"
            tool_loop_gate_count = summary.get("tool_loop_stop_gate_count")
            if isinstance(tool_loop_gate_count, int) and tool_loop_gate_count:
                label += f" ({tool_loop_gate_count} tool-loop gate finding(s))"
            parser_gate_count = summary.get("tool_parser_repair_gate_count")
            if isinstance(parser_gate_count, int) and parser_gate_count:
                label += f" ({parser_gate_count} parser-repair gate finding(s))"
            parts.append(label)
    harness_summaries = artifact.get("harness_review_summaries")
    if isinstance(harness_summaries, list):
        for summary in harness_summaries[:3]:
            if not isinstance(summary, dict):
                continue
            label = str(summary.get("suite_name") or summary.get("archive_path") or "harness")
            status = summary.get("review_status")
            if status:
                label += f": {status}"
            profile = summary.get("generator_profile")
            if profile:
                label += f" ({profile})"
            parts.append(label)
    suite_calibration_summaries = artifact.get("suite_calibration_summaries")
    if isinstance(suite_calibration_summaries, list):
        for summary in suite_calibration_summaries[:3]:
            if not isinstance(summary, dict):
                continue
            label = str(summary.get("suite") or summary.get("archive_path") or "suite calibration")
            label += f": passed={str(bool(summary.get('passed'))).lower()}"
            findings = _review_non_negative_int(summary.get("findings"))
            if findings:
                label += f", findings={findings}"
            parts.append(label)
    advisory_summaries = artifact.get("engine_advisory_summaries")
    if isinstance(advisory_summaries, list):
        for summary in advisory_summaries[:3]:
            if not isinstance(summary, dict):
                continue
            label = str(summary.get("engine") or summary.get("archive_path") or "engine advisory")
            priorities = summary.get("top_priorities")
            if isinstance(priorities, list) and priorities:
                areas = [str(item.get("area")) for item in priorities[:3] if isinstance(item, dict) and item.get("area")]
                if areas:
                    label += ": " + ", ".join(areas)
            parts.append(label)
    evidence_index_summaries = artifact.get("evidence_index_summaries")
    if isinstance(evidence_index_summaries, list):
        for summary in evidence_index_summaries[:3]:
            if not isinstance(summary, dict):
                continue
            label = str(summary.get("name") or summary.get("archive_path") or "evidence index")
            status_counts = summary.get("status_counts")
            if isinstance(status_counts, dict):
                label += ": " + ", ".join(f"{key}={value}" for key, value in sorted(status_counts.items()))
            readiness = summary.get("readiness")
            if isinstance(readiness, dict) and readiness.get("state"):
                label += f" ({readiness['state']})"
            cleanup_evidence = summary.get("cleanup_evidence")
            if isinstance(cleanup_evidence, dict) and cleanup_evidence.get("artifact_count"):
                label += f" cleanup={cleanup_evidence['artifact_count']}"
            parts.append(label)
    cleanup_report_summaries = artifact.get("cleanup_report_summaries")
    if isinstance(cleanup_report_summaries, list):
        for summary in cleanup_report_summaries[:3]:
            if not isinstance(summary, dict):
                continue
            label = str(summary.get("report_type") or "cleanup report")
            label += f": actions={summary.get('action_count', 0)}"
            if summary.get("audit_log_required") is True:
                label += " audit-required"
            parts.append(label)
    suite_audit_summaries = artifact.get("suite_audit_summaries")
    if isinstance(suite_audit_summaries, list):
        for summary in suite_audit_summaries[:3]:
            if not isinstance(summary, dict):
                continue
            label = str(summary.get("suite") or summary.get("archive_path") or "suite audit")
            label += f": findings={_review_non_negative_int(summary.get('finding_count'))}"
            duplicates = _review_non_negative_int(summary.get("duplicate_fingerprint_count"))
            if duplicates:
                label += f", duplicates={duplicates}"
            parts.append(label)
    metric_coverage_summaries = artifact.get("metric_coverage_summaries")
    if isinstance(metric_coverage_summaries, list):
        for summary in metric_coverage_summaries[:3]:
            if not isinstance(summary, dict):
                continue
            label = str(summary.get("provider") or summary.get("archive_path") or "metric coverage")
            label += f": score={summary.get('coverage_score')}"
            review_groups = summary.get("review_required_groups")
            if isinstance(review_groups, list) and review_groups:
                label += f", review_groups={len(review_groups)}"
            parts.append(label)
    matrix_pressure_summaries = artifact.get("matrix_pressure_summaries")
    if isinstance(matrix_pressure_summaries, list):
        for summary in matrix_pressure_summaries[:3]:
            if not isinstance(summary, dict):
                continue
            label = str(summary.get("matrix") or summary.get("archive_path") or "matrix pressure")
            label += (
                f": weighted={_review_non_negative_int(summary.get('concurrency_weighted_pressure_score'))}, "
                f"reuse={_review_non_negative_int(summary.get('shared_static_reuse_tokens'))}"
            )
            parts.append(label)
    matrix_saturation_summaries = artifact.get("matrix_saturation_summaries")
    if isinstance(matrix_saturation_summaries, list):
        for summary in matrix_saturation_summaries[:3]:
            if not isinstance(summary, dict):
                continue
            label = str(summary.get("matrix") or summary.get("archive_path") or "matrix saturation")
            label += (
                f": cmax={_review_non_negative_int(summary.get('max_concurrency'))}, "
                f"queue={summary.get('max_avg_queue_ms')}"
            )
            guidance = summary.get("guidance")
            if guidance:
                label += f", guidance={guidance}"
            parts.append(label)
    matrix_scorecard_summaries = artifact.get("matrix_scorecard_summaries")
    if isinstance(matrix_scorecard_summaries, list):
        for summary in matrix_scorecard_summaries[:3]:
            if not isinstance(summary, dict):
                continue
            label = str(summary.get("matrix") or summary.get("archive_path") or "matrix scorecard")
            label += (
                f": pass={summary.get('pass_rate_percent')}, "
                f"targets={_review_engine_target_ids_text(summary.get('engine_targets'))}, "
                f"architectures={_review_scorecard_group_names_text(summary.get('architecture_summary'), 'model_architecture')}, "
                f"quantization={_review_scorecard_group_names_text(summary.get('quantization_summary'), 'quantization')}, "
                f"telemetry={_telemetry_quality_review_text(summary.get('telemetry_quality_summary'))}, "
                f"stats={_stats_comparability_review_text(summary.get('stats_comparability_summary'))}, "
                f"parser_repair={summary.get('tool_parser_repairs_valid')}/{summary.get('tool_parser_repair_cases')}, "
                f"invalid_tools={summary.get('invalid_tool_call_count')}, "
                f"concurrency={_scorecard_concurrency_review_text(summary.get('concurrency_evidence'))}"
            )
            parts.append(label)
    publication_brief_summaries = artifact.get("publication_brief_summaries")
    if isinstance(publication_brief_summaries, list):
        for summary in publication_brief_summaries[:3]:
            if not isinstance(summary, dict):
                continue
            label = str(summary.get("name") or summary.get("archive_path") or "publication brief")
            label += (
                f": ready={str(summary.get('ready')).lower()}, "
                f"blockers={_review_non_negative_int(summary.get('claim_blockers'))}, "
                f"warnings={_review_non_negative_int(summary.get('claim_warnings'))}, "
                f"targets={_review_engine_target_ids_text(summary.get('engine_targets'))}"
            )
            parts.append(label)
    selftest_summaries = artifact.get("selftest_report_summaries")
    if isinstance(selftest_summaries, list):
        for summary in selftest_summaries[:3]:
            if not isinstance(summary, dict):
                continue
            run_id = str(summary.get("run_id") or summary.get("archive_path") or "selftest")
            tier = str(summary.get("tier") or "unknown")
            status = "pass" if summary.get("ok") is True else "fail"
            exit_code = _review_non_negative_int(summary.get("exit_code"))
            parts.append(f"{run_id}: {tier}={status} exit={exit_code}")
    sdlc_validation_summaries = artifact.get("sdlc_validation_manifest_summaries")
    if isinstance(sdlc_validation_summaries, list):
        for summary in sdlc_validation_summaries[:3]:
            if not isinstance(summary, dict):
                continue
            label = str(summary.get("name") or summary.get("archive_path") or "sdlc validation")
            label += (
                f": gates={_review_non_negative_int(summary.get('required_gate_count'))}, "
                f"chrome_steps={_review_non_negative_int(summary.get('chrome_validation_step_count'))}, "
                f"expected_artifacts={_review_non_negative_int(summary.get('expected_artifact_count'))}"
            )
            parts.append(label)
    benchmark_readiness_summaries = artifact.get("benchmark_readiness_summaries")
    if isinstance(benchmark_readiness_summaries, list):
        for summary in benchmark_readiness_summaries[:3]:
            if not isinstance(summary, dict):
                continue
            label = str(summary.get("provider") or summary.get("archive_path") or "benchmark readiness")
            label += f": ready={str(summary.get('ready')).lower()}"
            plaintext = _review_non_negative_int(summary.get("provider_auth_plaintext_fallbacks"))
            writable = _review_non_negative_int(summary.get("provider_auth_writable_backends"))
            if writable or plaintext:
                label += f", auth_writable={writable}, plaintext={plaintext}"
            parts.append(label)
    implementation_status_summaries = artifact.get("implementation_status_summaries")
    if isinstance(implementation_status_summaries, list):
        for summary in implementation_status_summaries[:3]:
            if not isinstance(summary, dict):
                continue
            label = str(summary.get("archive_path") or "implementation status")
            label += (
                f": {summary.get('implementation_status') or summary.get('status') or 'unknown'}, "
                f"missing={_review_non_negative_int(summary.get('missing_areas'))}, "
                f"harness_cases={_review_non_negative_int(summary.get('harness_engineering_case_count'))}, "
                f"stats_profiles={_review_non_negative_int(summary.get('stats_profile_count'))}"
            )
            parts.append(label)
    provider_contract_summaries = artifact.get("provider_contract_summaries")
    if isinstance(provider_contract_summaries, list):
        for summary in provider_contract_summaries[:3]:
            if not isinstance(summary, dict):
                continue
            label = str(summary.get("provider") or summary.get("matrix") or summary.get("archive_path") or "provider contract")
            evidence = summary.get("capability_evidence") if isinstance(summary.get("capability_evidence"), dict) else {}
            evidence_parts = []
            direct = evidence.get("directly_checked")
            if isinstance(direct, list) and direct:
                evidence_parts.append("direct=" + ", ".join(sorted(str(item) for item in direct[:6])))
            proxy_counts = evidence.get("proxy_checked_counts")
            if isinstance(proxy_counts, dict) and proxy_counts:
                evidence_parts.append("proxy=" + ", ".join(f"{key}={value}" for key, value in sorted(proxy_counts.items())))
            not_covered = evidence.get("not_covered_counts")
            if isinstance(not_covered, dict) and not_covered:
                evidence_parts.append("not_covered=" + ", ".join(f"{key}={value}" for key, value in sorted(not_covered.items())))
            if evidence_parts:
                label += ": " + "; ".join(evidence_parts)
            parts.append(label)
    publication_bundle_summaries = artifact.get("publication_bundle_summaries")
    if isinstance(publication_bundle_summaries, list):
        for summary in publication_bundle_summaries[:3]:
            if not isinstance(summary, dict):
                continue
            readiness = summary.get("publication_readiness")
            status = readiness.get("status") if isinstance(readiness, dict) else "unknown"
            media_kit = summary.get("media_kit") if isinstance(summary.get("media_kit"), dict) else {}
            missing = media_kit.get("missing_recommended_assets")
            missing_count = len(missing) if isinstance(missing, list) else 0
            label = str(summary.get("run_id") or summary.get("archive_path") or "publication bundle")
            label += f": {status}, media-missing={missing_count}"
            parts.append(label)
    matrix_publication_bundle_summaries = artifact.get("matrix_publication_bundle_summaries")
    if isinstance(matrix_publication_bundle_summaries, list):
        for summary in matrix_publication_bundle_summaries[:3]:
            if not isinstance(summary, dict):
                continue
            matrix = summary.get("matrix") if isinstance(summary.get("matrix"), dict) else {}
            media_kit = summary.get("media_kit") if isinstance(summary.get("media_kit"), dict) else {}
            missing = media_kit.get("missing_recommended_assets")
            missing_count = len(missing) if isinstance(missing, list) else 0
            label = str(matrix.get("artifact_stem") or summary.get("archive_path") or "matrix publication bundle")
            label += (
                f": media-missing={missing_count}, targets={_review_engine_target_ids_text(summary.get('engine_targets'))}, "
                f"architectures={_review_scorecard_group_names_text(summary.get('architecture_summary'), 'model_architecture')}, "
                f"quantization={_review_scorecard_group_names_text(summary.get('quantization_summary'), 'quantization')}"
            )
            parts.append(label)
    return "; ".join(parts) if parts else "none"


def _review_engine_target_ids_text(value: Any) -> str:
    if not isinstance(value, list):
        return "none"
    ids = [str(item.get("id")) for item in value if isinstance(item, dict) and item.get("id")]
    return ",".join(ids) if ids else "none"


def _review_scorecard_group_names_text(value: Any, key: str) -> str:
    if not isinstance(value, list):
        return "none"
    names = [str(item.get(key)) for item in value if isinstance(item, dict) and item.get(key)]
    return ",".join(names) if names else "none"


def _failure_class_summary_text(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return "none"
    parts = []
    for item in value:
        if isinstance(item, dict):
            parts.append(f"{item.get('failure_class', 'unclassified')}={item.get('count', 0)}")
    return ", ".join(parts) if parts else "none"


def _tool_loop_stop_summary_text(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return "none"
    parts = []
    for item in value:
        if isinstance(item, dict):
            parts.append(f"{item.get('stop_reason') or item.get('reason') or 'unknown'}={item.get('count', 0)}")
    return ", ".join(parts) if parts else "none"


def serve_dashboard(
    runs_dir: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    allow_non_loopback: bool = False,
    auth_token: str | None = None,
    audit_log: Path | None = None,
    policy: SecurityPolicy | None = None,
) -> None:
    assert_dashboard_bind_allowed(host, allow_non_loopback=allow_non_loopback, auth_configured=auth_token is not None)
    handler = make_dashboard_handler(runs_dir, auth_token=auth_token, audit_log=audit_log, policy=policy)
    server = ThreadingHTTPServer((host, port), handler)
    AuditLogger(audit_log).emit(
        "dashboard_started",
        runs_dir=str(runs_dir),
        host=host,
        port=port,
        allow_non_loopback=allow_non_loopback,
        auth_enabled=auth_token is not None,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return
    finally:
        server.server_close()


def make_dashboard_handler(
    runs_dir: Path,
    *,
    auth_token: str | None = None,
    audit_log: Path | None = None,
    policy: SecurityPolicy | None = None,
):
    auth_digest = _dashboard_auth_digest(auth_token) if auth_token else None

    class DashboardRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/login":
                if auth_token is None:
                    self._redirect("/")
                    return
                self._write_html(_login_html())
                return
            if not self._is_authenticated():
                self._reject_unauthenticated(parsed.path)
                return
            if parsed.path == "/logout":
                self._redirect("/login", clear_auth_cookie=True)
                return
            if parsed.path in {"", "/"}:
                self._write_html(render_dashboard_html(runs_dir, auth_required=auth_digest is not None))
                return
            if parsed.path.startswith("/catalog/"):
                catalog_id = unquote(parsed.path.removeprefix("/catalog/")).strip("/")
                try:
                    self._write_html(
                        render_dashboard_catalog_html(
                            catalog_id,
                            project_root=_dashboard_project_root(runs_dir),
                            policy=policy,
                            query=parse_qs(parsed.query, keep_blank_values=True),
                        )
                    )
                except ConfigError as exc:
                    self._write_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
                return
            if parsed.path.startswith("/runs/") and "/artifacts/" in parsed.path:
                try:
                    run_id, artifact_name = _parse_artifact_path(parsed.path)
                    artifact_path = dashboard_artifact_path(runs_dir, run_id, artifact_name)
                    self._write_file(artifact_path, REPORT_ARTIFACTS[artifact_name])
                except ConfigError as exc:
                    self._write_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
                return
            if parsed.path == "/api/runs":
                self._write_json({"runs": list_dashboard_runs(runs_dir)})
                return
            if parsed.path == "/api/providers":
                try:
                    self._write_json({"providers": dashboard_providers()})
                except ConfigError as exc:
                    self._write_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            if parsed.path == "/api/setup-status":
                try:
                    self._write_json(dashboard_setup_status(policy=policy))
                except ConfigError as exc:
                    self._write_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            if parsed.path == "/api/suites":
                self._write_json({"suites": dashboard_suites()})
                return
            if parsed.path == "/api/models":
                self._write_json(dashboard_model_targets())
                return
            if parsed.path == "/api/engine-targets":
                self._write_json(dashboard_engine_targets())
                return
            if parsed.path == "/api/local-engine-onboarding":
                self._write_json(dashboard_local_engine_onboarding())
                return
            if parsed.path == "/api/workflow-surfaces":
                self._write_json(dashboard_workflow_surfaces())
                return
            if parsed.path == "/api/telemetry-mappings":
                self._write_json(dashboard_telemetry_mappings())
                return
            if parsed.path == "/api/review-artifacts":
                try:
                    self._write_json(dashboard_review_artifacts(_dashboard_project_root(runs_dir)))
                except ConfigError as exc:
                    self._write_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            if parsed.path.startswith("/api/review-artifacts/"):
                artifact_path = unquote(parsed.path.removeprefix("/api/review-artifacts/")).strip("/")
                try:
                    self._write_json(dashboard_review_artifact_payload(_dashboard_project_root(runs_dir), artifact_path))
                except ConfigError as exc:
                    self._write_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            if parsed.path == "/api/catalogs":
                self._write_json(dashboard_catalog_index())
                return
            if parsed.path == "/api/run-plan":
                self._write_json(
                    {
                        "schema_version": "agentblaster.dashboard-run-plan-endpoint.v1",
                        "method": "POST",
                        "description": "Submit provider, suite, model, raw_traces, concurrency, allow_remote, and optional capability_preflight to build a no-dispatch run plan.",
                        "safety": {
                            "dispatches_requests": False,
                            "contacts_provider": False,
                            "resolves_secrets": False,
                            "writes_run_artifacts": False,
                            "policy_enforced": True,
                        },
                    }
                )
                return
            if parsed.path == "/api/campaign-preview":
                try:
                    self._write_json(dashboard_campaign_preview(parse_qs(parsed.query, keep_blank_values=True)))
                except ConfigError as exc:
                    self._write_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            if parsed.path.startswith("/api/runs/"):
                if parsed.path.endswith("/events"):
                    run_id = unquote(parsed.path.removeprefix("/api/runs/").removesuffix("/events")).strip("/")
                    try:
                        self._write_json(dashboard_run_events(runs_dir, run_id))
                    except ConfigError as exc:
                        self._write_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
                    return
                run_id = unquote(parsed.path.removeprefix("/api/runs/")).strip("/")
                try:
                    self._write_json(dashboard_run_payload(runs_dir, run_id))
                except ConfigError as exc:
                    self._write_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
                return
            self._write_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/login":
                if auth_token is None:
                    self._redirect("/")
                    return
                payload = self._read_form_payload()
                if auth_token is not None and hmac.compare_digest(str(payload.get("token") or ""), auth_token):
                    self._redirect("/", set_auth_cookie=auth_digest)
                    return
                self._write_html(_login_html("invalid dashboard token"), status=HTTPStatus.UNAUTHORIZED)
                return
            if not self._is_authenticated():
                self._reject_unauthenticated(parsed.path)
                return
            if parsed.path == "/providers":
                try:
                    configure_dashboard_provider_profile(self._read_form_payload(), audit_log=audit_log, policy=policy)
                except (ConfigError, ValidationError, ValueError) as exc:
                    self._write_html(_error_html(str(exc)), status=HTTPStatus.BAD_REQUEST)
                    return
                self.send_response(HTTPStatus.SEE_OTHER)
                self._security_headers()
                self.send_header("location", "/?provider=stored")
                self.end_headers()
                return
            if parsed.path == "/providers/auth":
                try:
                    payload = self._read_form_payload()
                    configure_dashboard_provider_auth(str(payload.get("provider") or ""), payload, audit_log=audit_log, policy=policy)
                except ConfigError as exc:
                    self._write_html(_error_html(str(exc)), status=HTTPStatus.BAD_REQUEST)
                    return
                self.send_response(HTTPStatus.SEE_OTHER)
                self._security_headers()
                self.send_header("location", "/?provider_auth=stored")
                self.end_headers()
                return
            if parsed.path == "/providers/auth/clear":
                try:
                    payload = self._read_form_payload()
                    clear_dashboard_provider_auth(
                        str(payload.get("provider") or ""),
                        delete_secret=_payload_bool(payload, "delete_secret"),
                        audit_log=audit_log,
                        policy=policy,
                    )
                except ConfigError as exc:
                    self._write_html(_error_html(str(exc)), status=HTTPStatus.BAD_REQUEST)
                    return
                self.send_response(HTTPStatus.SEE_OTHER)
                self._security_headers()
                self.send_header("location", "/?provider_auth=cleared")
                self.end_headers()
                return
            if parsed.path == "/run-plan":
                try:
                    payload = self._read_form_payload()
                    result = dashboard_run_plan(payload, audit_log=audit_log, policy=policy)
                except (ConfigError, ValidationError, ValueError) as exc:
                    self._write_html(_error_html(str(exc)), status=HTTPStatus.BAD_REQUEST)
                    return
                self._write_html(_run_plan_html(result))
                return
            if parsed.path == "/launch":
                try:
                    payload = self._read_form_payload()
                    launch = launch_dashboard_run(runs_dir, payload, audit_log=audit_log, policy=policy)
                except (ConfigError, ValidationError, ValueError) as exc:
                    self._write_html(_error_html(str(exc)), status=HTTPStatus.BAD_REQUEST)
                    return
                self.send_response(HTTPStatus.SEE_OTHER)
                self._security_headers()
                self.send_header("location", f"/?launched={quote(str(launch['summary']['run_id']))}")
                self.end_headers()
                return
            if parsed.path.startswith("/runs/") and parsed.path.endswith("/reports"):
                try:
                    run_id = unquote(parsed.path.removeprefix("/runs/").removesuffix("/reports")).strip("/")
                    payload = self._read_form_payload()
                    generate_dashboard_reports(runs_dir, run_id, _split_csv(str(payload.get("formats") or "")))
                except (ConfigError, ValidationError, ValueError) as exc:
                    self._write_html(_error_html(str(exc)), status=HTTPStatus.BAD_REQUEST)
                    return
                self.send_response(HTTPStatus.SEE_OTHER)
                self._security_headers()
                self.send_header("location", f"/?reports={quote(run_id)}")
                self.end_headers()
                return
            if parsed.path.startswith("/api/runs/") and parsed.path.endswith("/reports"):
                try:
                    run_id = unquote(parsed.path.removeprefix("/api/runs/").removesuffix("/reports")).strip("/")
                    payload = self._read_json_payload()
                    formats = payload.get("formats") or ["html", "md", "json", "publication", "card", "pdf"]
                    if isinstance(formats, str):
                        formats = _split_csv(formats)
                    if not isinstance(formats, list):
                        raise ConfigError("formats must be a list or comma-separated string")
                    result = generate_dashboard_reports(runs_dir, run_id, [str(item) for item in formats])
                except (ConfigError, ValidationError, ValueError) as exc:
                    self._write_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._write_json({"reports": result}, status=HTTPStatus.CREATED)
                return
            if parsed.path == "/api/providers":
                try:
                    provider = configure_dashboard_provider_profile(self._read_json_payload(), audit_log=audit_log, policy=policy)
                except (ConfigError, ValidationError, ValueError) as exc:
                    self._write_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._write_json({"provider": provider}, status=HTTPStatus.CREATED)
                return
            if parsed.path.startswith("/api/providers/") and parsed.path.endswith("/auth"):
                provider_name = unquote(parsed.path.removeprefix("/api/providers/").removesuffix("/auth")).strip("/")
                try:
                    auth = configure_dashboard_provider_auth(provider_name, self._read_json_payload(), audit_log=audit_log, policy=policy)
                except ConfigError as exc:
                    self._write_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._write_json({"auth": auth}, status=HTTPStatus.CREATED)
                return
            if parsed.path == "/api/run-plan":
                try:
                    result = dashboard_run_plan(self._read_json_payload(), audit_log=audit_log, policy=policy)
                except (ConfigError, ValidationError, ValueError) as exc:
                    self._write_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._write_json(result)
                return
            if parsed.path != "/api/runs":
                self._write_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)
                return
            try:
                payload = self._read_json_payload()
                launch = launch_dashboard_run(runs_dir, payload, audit_log=audit_log, policy=policy)
            except (ConfigError, ValidationError, ValueError) as exc:
                self._write_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._write_json(launch, status=HTTPStatus.CREATED)

        def do_DELETE(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if not self._is_authenticated():
                self._reject_unauthenticated(parsed.path)
                return
            if parsed.path.startswith("/api/providers/") and parsed.path.endswith("/auth"):
                provider_name = unquote(parsed.path.removeprefix("/api/providers/").removesuffix("/auth")).strip("/")
                query = parse_qs(parsed.query, keep_blank_values=True)
                try:
                    auth = clear_dashboard_provider_auth(
                        provider_name,
                        delete_secret=_truthy((query.get("delete_secret") or ["false"])[-1]),
                        audit_log=audit_log,
                        policy=policy,
                    )
                except ConfigError as exc:
                    self._write_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._write_json({"auth": auth})
                return
            self._write_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return

        def _is_authenticated(self) -> bool:
            if auth_token is None or auth_digest is None:
                return True
            authorization = self.headers.get("authorization", "")
            if authorization.lower().startswith("bearer "):
                candidate = authorization[7:].strip()
                if hmac.compare_digest(candidate, auth_token):
                    return True
            cookie_header = self.headers.get("cookie", "")
            if cookie_header:
                cookie = SimpleCookie()
                cookie.load(cookie_header)
                morsel = cookie.get(DASHBOARD_AUTH_COOKIE)
                if morsel is not None and hmac.compare_digest(morsel.value, auth_digest):
                    return True
            return False

        def _reject_unauthenticated(self, path: str) -> None:
            if path.startswith("/api/"):
                payload = json.dumps({"error": "dashboard authentication required"}).encode("utf-8")
                self.send_response(HTTPStatus.UNAUTHORIZED)
                self._security_headers()
                self.send_header("www-authenticate", 'Bearer realm="AgentBlaster Dashboard"')
                self.send_header("content-type", "application/json; charset=utf-8")
                self.send_header("content-length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            self._redirect("/login")

        def _redirect(
            self,
            location: str,
            *,
            set_auth_cookie: str | None = None,
            clear_auth_cookie: bool = False,
        ) -> None:
            self.send_response(HTTPStatus.SEE_OTHER)
            self._security_headers()
            self.send_header("location", location)
            if set_auth_cookie is not None:
                self.send_header(
                    "set-cookie",
                    f"{DASHBOARD_AUTH_COOKIE}={set_auth_cookie}; Path=/; HttpOnly; SameSite=Strict; Max-Age=28800",
                )
            if clear_auth_cookie:
                self.send_header(
                    "set-cookie",
                    f"{DASHBOARD_AUTH_COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0",
                )
            self.end_headers()

        def _write_html(self, body: str, *, status: HTTPStatus = HTTPStatus.OK) -> None:
            payload = body.encode("utf-8")
            self.send_response(status)
            self._security_headers()
            self.send_header("content-type", "text/html; charset=utf-8")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _write_file(self, path: Path, content_type: str) -> None:
            payload = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self._security_headers()
            self.send_header("content-type", content_type)
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _write_json(self, body: dict[str, Any], *, status: HTTPStatus = HTTPStatus.OK) -> None:
            payload = (json.dumps(body, sort_keys=True) + "\n").encode("utf-8")
            self.send_response(status)
            self._security_headers()
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _read_json_payload(self) -> dict[str, Any]:
            content_length = int(self.headers.get("content-length", "0"))
            if content_length <= 0:
                return {}
            raw = self.rfile.read(content_length).decode("utf-8")
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ConfigError("JSON payload must be an object")
            return payload

        def _read_form_payload(self) -> dict[str, Any]:
            content_length = int(self.headers.get("content-length", "0"))
            if content_length <= 0:
                return {}
            raw = self.rfile.read(content_length).decode("utf-8")
            parsed = parse_qs(raw, keep_blank_values=True)
            payload = {key: values[-1] for key, values in parsed.items() if values}
            return {
                **payload,
                "allow_remote": _truthy(payload.get("allow_remote")),
                "no_raw_traces": payload.get("raw_traces") == RawTraceMode.OFF.value,
                "concurrency": int(payload.get("concurrency") or 1),
            }

        def _security_headers(self) -> None:
            self.send_header("cache-control", "no-store")
            self.send_header("referrer-policy", "no-referrer")
            self.send_header("x-content-type-options", "nosniff")
            self.send_header(
                "content-security-policy",
                "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                "script-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
            )

    return DashboardRequestHandler


def _run_plan_html(result: dict[str, Any]) -> str:
    plan = result["plan"]
    safety = result["safety"]
    prompt_footprint = plan.get("prompt_footprint") if isinstance(plan.get("prompt_footprint"), dict) else {}
    prefill_pressure = (
        f"{prompt_footprint.get('prefill_pressure_level', 'unknown')} "
        f"({prompt_footprint.get('prefill_pressure_score', 0)})"
    )
    case_rows = "\n".join(
        f"""<tr>
  <td>{html.escape(str(case["case_id"]))}</td>
  <td>{html.escape(str(case["title"]))}</td>
  <td>{case["estimated_prompt_tokens"]}</td>
  <td>{case.get("static_prefix_tokens", 0)}</td>
  <td>{case.get("dynamic_prompt_tokens", 0)}</td>
  <td>{case["max_output_tokens"]}</td>
  <td>{html.escape(str(case.get("cancel_after_ms") or "none"))}</td>
  <td>{html.escape(str(case["streaming"]).lower())}</td>
  <td>{case["tool_schemas"]}</td>
  <td>{case["simulated_tools"]}</td>
  <td>{html.escape(_run_plan_case_surfaces(case))}</td>
  <td>{html.escape(','.join(case.get("prompt_surfaces", [])) or "none")}</td>
</tr>"""
        for case in plan["cases"]
    )
    safety_items = "\n".join(
        f"<li><strong>{html.escape(str(key))}</strong>: {html.escape(str(value).lower())}</li>"
        for key, value in safety.items()
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentBlaster Run Plan Preview</title>
  <style>
    body {{
      margin: 0;
      color: #111713;
      font-family: "Avenir Next", "Trebuchet MS", "Gill Sans", sans-serif;
      background: linear-gradient(135deg, #fff8ec 0%, #f5efe4 48%, #dfe7d9 100%);
      min-height: 100vh;
    }}
    main {{ max-width: 1040px; margin: 0 auto; padding: 40px 20px 64px; }}
    h1 {{ font-family: "Iowan Old Style", "Palatino", serif; font-size: clamp(38px, 7vw, 72px); line-height: 0.92; margin: 0 0 12px; letter-spacing: -0.05em; }}
    h2 {{ font-family: "Iowan Old Style", "Palatino", serif; font-size: 30px; margin: 0 0 12px; }}
    .panel {{ background: rgba(255, 252, 245, 0.9); border: 1px solid #d7cbb7; border-radius: 28px; box-shadow: 0 24px 70px rgba(76, 53, 25, 0.14); margin-top: 20px; padding: 22px; overflow-x: auto; }}
    .kicker {{ color: #70340e; font-weight: 800; letter-spacing: 0.14em; text-transform: uppercase; }}
    .grid {{ display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); }}
    .metric {{ border: 1px solid #d7cbb7; border-radius: 18px; padding: 14px 16px; }}
    .metric span {{ color: #647067; display: block; font-size: 12px; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; }}
    .metric strong {{ display: block; font-size: 22px; margin-top: 4px; }}
    .safety {{ line-height: 1.7; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid rgba(215, 203, 183, 0.78); padding: 12px 14px; text-align: left; }}
    th {{ color: #70340e; font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; }}
    a {{ color: #70340e; font-weight: 800; }}
  </style>
</head>
<body>
  <main data-testid="run-plan-panel">
    <a href="/">Back to dashboard</a>
    <p class="kicker">No-dispatch launch preview</p>
    <h1>Run plan</h1>
    <section class="panel">
      <h2>Summary</h2>
      <div class="grid">
        <div class="metric" data-testid="run-plan-provider"><span>Provider</span><strong>{html.escape(str(plan["provider"]))}</strong></div>
        <div class="metric" data-testid="run-plan-suite"><span>Suite</span><strong>{html.escape(str(plan["suite"]))}</strong></div>
        <div class="metric" data-testid="run-plan-model"><span>Model</span><strong>{html.escape(str(plan["model"]))}</strong></div>
        <div class="metric" data-testid="run-plan-cases"><span>Cases</span><strong>{plan["total_cases"]}</strong></div>
        <div class="metric" data-testid="run-plan-concurrency"><span>Concurrency</span><strong>{plan["concurrency"]}</strong></div>
        <div class="metric" data-testid="run-plan-cost"><span>Estimated cost</span><strong>{html.escape(str(plan["estimated_total_cost_usd"]))}</strong></div>
        <div class="metric" data-testid="run-plan-prefill-pressure"><span>Prefill pressure</span><strong>{html.escape(prefill_pressure)}</strong></div>
        <div class="metric" data-testid="run-plan-cache-reuse"><span>Potential cache reuse tokens</span><strong>{prompt_footprint.get("shared_static_reuse_tokens", 0)}</strong></div>
      </div>
    </section>
    <section class="panel">
      <h2>Safety contract</h2>
      <ul class="safety" data-testid="run-plan-safety">
        {safety_items}
      </ul>
    </section>
    <section class="panel">
      <h2>Planned cases</h2>
      <table data-testid="run-plan-cases-table">
        <thead>
          <tr>
            <th>Case</th>
            <th>Title</th>
            <th>Prompt tokens</th>
            <th>Static prefix</th>
            <th>Dynamic prompt</th>
            <th>Max output</th>
            <th>Cancel after</th>
            <th>Streaming</th>
            <th>Tool schemas</th>
            <th>Sim tools</th>
            <th>Capability surfaces</th>
            <th>Prompt surfaces</th>
          </tr>
        </thead>
        <tbody>
          {case_rows}
        </tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""


def _run_plan_case_surfaces(case: dict[str, Any]) -> str:
    surfaces = case.get("capability_surfaces")
    if not isinstance(surfaces, list) or not surfaces:
        return "none"
    return ", ".join(str(surface) for surface in surfaces)


def _review_artifact_entry(path: Path, *, root: Path, category: str) -> dict[str, Any]:
    size = path.stat().st_size
    relative_path = path.relative_to(root).as_posix()
    entry: dict[str, Any] = {
        "path": relative_path,
        "name": path.name,
        "category": category,
        "kind": path.suffix.lower().lstrip(".") or "file",
        "size_bytes": size,
        "publication_safe_candidate": True,
    }
    if path.suffix.lower() == ".json":
        entry["href"] = f"/api/review-artifacts/{quote(relative_path, safe='')}"
        entry.update(_json_review_summary(path, max_bytes=REVIEW_ARTIFACT_MAX_JSON_BYTES))
    elif path.suffix.lower() == ".zip":
        entry.update(_zip_review_summary(path))
    return entry


def _json_review_summary(path: Path, *, max_bytes: int) -> dict[str, Any]:
    size = path.stat().st_size
    if size > max_bytes:
        return {
            "schema": None,
            "status": "skipped-large-json",
            "status_source": "file-size",
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "schema": None,
            "status": "invalid-json",
            "status_source": "json-parse",
        }
    if not isinstance(payload, dict):
        return {
            "schema": None,
            "status": "invalid-json-root",
            "status_source": "json-root",
        }
    schema = payload.get("schema_version") or payload.get("schema") or payload.get("report_type")
    if _looks_like_matrix_gate_payload(payload) and schema != MATRIX_GATE_SCHEMA_VERSION:
        return {
            "schema": schema,
            "status": "invalid-schema",
            "status_source": "schema",
            "expected_schema": MATRIX_GATE_SCHEMA_VERSION,
            "top_level_keys": sorted(str(key) for key in payload.keys())[:20],
        }
    status, status_source = _review_status(payload)
    summary = {
        "schema": schema,
        "status": status,
        "status_source": status_source,
        "top_level_keys": sorted(str(key) for key in payload.keys())[:20],
    }
    matrix_gate_summary = _matrix_gate_json_review_summary(payload)
    if matrix_gate_summary:
        summary["matrix_gate_review_summaries"] = [matrix_gate_summary]
    harness_summary = _harness_json_review_summary(payload)
    if harness_summary:
        summary["harness_review_summaries"] = [harness_summary]
    suite_calibration_summary = _suite_calibration_json_review_summary(payload)
    if suite_calibration_summary:
        summary["suite_calibration_summaries"] = [suite_calibration_summary]
    engine_advisory_summary = _engine_advisory_json_review_summary(payload)
    if engine_advisory_summary:
        summary["engine_advisory_summaries"] = [engine_advisory_summary]
    evidence_index_summary = _evidence_index_json_review_summary(payload)
    if evidence_index_summary:
        summary["evidence_index_summaries"] = [evidence_index_summary]
    campaign_preflight_summary = _campaign_preflight_json_review_summary(payload)
    if campaign_preflight_summary:
        summary["campaign_preflight_summaries"] = [campaign_preflight_summary]
        summary["status"] = "review"
        summary["status_source"] = "campaign-preflight.review-summary"
    cleanup_summary = _cleanup_json_review_summary(payload)
    if cleanup_summary:
        summary["cleanup_report_summaries"] = [cleanup_summary]
    suite_audit_summary = _suite_audit_json_review_summary(payload)
    if suite_audit_summary:
        summary["suite_audit_summaries"] = [suite_audit_summary]
    metric_coverage_summary = _metric_coverage_json_review_summary(payload)
    if metric_coverage_summary:
        summary["metric_coverage_summaries"] = [metric_coverage_summary]
    normalized_telemetry_summary = _normalized_telemetry_json_review_summary(payload)
    if normalized_telemetry_summary:
        summary["normalized_telemetry_summaries"] = [normalized_telemetry_summary]
    matrix_pressure_summary = _matrix_pressure_json_review_summary(payload)
    if matrix_pressure_summary:
        summary["matrix_pressure_summaries"] = [matrix_pressure_summary]
    matrix_saturation_summary = _matrix_saturation_json_review_summary(payload)
    if matrix_saturation_summary:
        summary["matrix_saturation_summaries"] = [matrix_saturation_summary]
    matrix_scorecard_summary = _matrix_scorecard_json_review_summary(payload)
    if matrix_scorecard_summary:
        summary["matrix_scorecard_summaries"] = [matrix_scorecard_summary]
        summary["status"] = matrix_scorecard_summary["status"]
        summary["status_source"] = "matrix-scorecard.review"
    selftest_summary = _selftest_json_review_summary(payload)
    if selftest_summary:
        summary["selftest_report_summaries"] = [selftest_summary]
    publication_brief_summary = _publication_brief_json_review_summary(payload)
    if publication_brief_summary:
        summary["publication_brief_summaries"] = [publication_brief_summary]
    protocol_repair_summary = _protocol_repair_posture_json_review_summary(payload)
    if protocol_repair_summary:
        summary["protocol_repair_posture_summaries"] = [protocol_repair_summary]
    workflow_readiness_summary = _workflow_readiness_json_review_summary(payload)
    if workflow_readiness_summary:
        summary["workflow_readiness_summaries"] = [workflow_readiness_summary]
    security_posture_summary = _security_posture_json_review_summary(payload)
    if security_posture_summary:
        summary["security_posture_summaries"] = [security_posture_summary]
    sdlc_validation_manifest_summary = _sdlc_validation_manifest_json_review_summary(payload)
    if sdlc_validation_manifest_summary:
        summary["sdlc_validation_manifest_summaries"] = [sdlc_validation_manifest_summary]
    provider_audit_summary = _provider_audit_json_review_summary(payload)
    if provider_audit_summary:
        summary["provider_audit_summaries"] = [provider_audit_summary]
    benchmark_readiness_summary = _benchmark_readiness_json_review_summary(payload)
    if benchmark_readiness_summary:
        summary["benchmark_readiness_summaries"] = [benchmark_readiness_summary]
    implementation_status_summary = _implementation_status_json_review_summary(payload)
    if implementation_status_summary:
        summary["implementation_status_summaries"] = [implementation_status_summary]
    campaign_preflight_readiness_summaries = _campaign_preflight_benchmark_readiness_json_review_summaries(payload)
    if campaign_preflight_readiness_summaries:
        summary["benchmark_readiness_summaries"] = campaign_preflight_readiness_summaries
        summary["status"] = (
            "pass"
            if all(item.get("ready") is True for item in campaign_preflight_readiness_summaries)
            else "review"
        )
        summary["status_source"] = "benchmark-readiness-index.reports.ready"
    provider_contract_summary = _provider_contract_json_review_summary(payload)
    if provider_contract_summary:
        summary["provider_contract_summaries"] = [provider_contract_summary]
    return summary


def _review_status(payload: dict[str, Any]) -> tuple[str, str]:
    schema = payload.get("schema_version") or payload.get("schema")
    if schema == SELFTEST_REPORT_SCHEMA_VERSION:
        value = payload.get("ok")
        if isinstance(value, bool):
            return ("pass" if value else "fail", "selftest.ok")
        return "review", "selftest.ok"
    if schema == PUBLICATION_BRIEF_SCHEMA_VERSION:
        security = payload.get("security") if isinstance(payload.get("security"), dict) else {}
        if security.get("contains_secrets") is True or security.get("contains_raw_provider_payloads") is True:
            return "fail", "publication-brief.security"
        value = payload.get("ready")
        if isinstance(value, bool):
            return ("pass" if value else "review", "publication-brief.ready")
        return "review", "publication-brief.ready"
    if schema == PROTOCOL_REPAIR_POSTURE_SCHEMA_VERSION:
        value = payload.get("ready")
        if isinstance(value, bool):
            return ("pass" if value else "review", "protocol-repair.ready")
        return "review", "protocol-repair.ready"
    if schema == WORKFLOW_READINESS_SCHEMA_VERSION:
        value = payload.get("ready")
        if isinstance(value, bool):
            return ("pass" if value else "review", "workflow-readiness.ready")
        return "review", "workflow-readiness.ready"
    if schema == SECURITY_POSTURE_SCHEMA_VERSION:
        value = payload.get("ready")
        if isinstance(value, bool):
            return ("pass" if value else "fail", "security-posture.ready")
        return "review", "security-posture.ready"
    if schema == SDLC_VALIDATION_MANIFEST_SCHEMA_VERSION:
        security = payload.get("security") if isinstance(payload.get("security"), dict) else {}
        if security.get("contains_secrets") is True or security.get("contains_raw_provider_payloads") is True:
            return "fail", "sdlc-validation-manifest.security"
        return "review", "sdlc-validation-manifest.static"
    if schema == PROVIDER_AUDIT_SCHEMA_VERSION:
        if _review_non_negative_int(payload.get("errors")):
            return "fail", "provider-audit.errors"
        if _review_non_negative_int(payload.get("warnings")):
            return "review", "provider-audit.warnings"
        return "pass", "provider-audit.errors"
    if schema in {
        HARNESS_REVIEW_SCHEMA_VERSION,
        ENGINE_ADVISORY_SCHEMA_VERSION,
        EVIDENCE_INDEX_SCHEMA_VERSION,
        CLEANUP_PLAN_SCHEMA_VERSION,
        RETENTION_CLEANUP_SCHEMA_VERSION,
        SUITE_AUDIT_SCHEMA_VERSION,
        METRIC_COVERAGE_SCHEMA_VERSION,
        NORMALIZED_TELEMETRY_SCHEMA_VERSION,
        MATRIX_PRESSURE_SCHEMA_VERSION,
        MATRIX_SCORECARD_SCHEMA_VERSION,
        CAMPAIGN_PREFLIGHT_SCHEMA_VERSION,
    }:
        return "review", "review.status"
    if schema == IMPLEMENTATION_STATUS_SCHEMA_VERSION:
        missing_areas = _review_non_negative_int(payload.get("missing_areas"))
        status = payload.get("status")
        ok = missing_areas == 0 and status == "implementation-ready-for-validation"
        return ("pass" if ok else "fail", "implementation-status.status")
    ready = payload.get("ready")
    if isinstance(ready, bool):
        return ("pass" if ready else "review", "ready")
    for key in ("ok", "passed"):
        value = payload.get(key)
        if isinstance(value, bool):
            return ("pass" if value else "fail", key)
    summary = payload.get("summary")
    if isinstance(summary, dict):
        value = summary.get("comparable_core_ok")
        if isinstance(value, bool):
            return ("pass" if value else "review", "summary.comparable_core_ok")
    return "informational", "schema"


def _zip_review_schema(path: Path) -> str | None:
    name = path.name
    if name.endswith(".agentblaster-evidence.zip"):
        return "agentblaster.evidence-bundle"
    if name.endswith(".agentblaster-publication.zip"):
        return "agentblaster.publication-bundle"
    if name.endswith(".agentblaster-matrix-publication.zip"):
        return "agentblaster.matrix-publication-bundle"
    if name.endswith(".agentblaster-release-qualification.zip"):
        return "agentblaster.release-qualification-bundle"
    return None


def _zip_review_summary(path: Path) -> dict[str, Any]:
    schema = _zip_review_schema(path)
    if schema == "agentblaster.publication-bundle":
        return _publication_bundle_zip_review_summary(path, schema)
    if schema == "agentblaster.matrix-publication-bundle":
        return _matrix_publication_bundle_zip_review_summary(path, schema)
    if schema != "agentblaster.release-qualification-bundle":
        return {
            "schema": schema,
            "status": "not-opened",
            "status_source": "zip-name",
        }
    try:
        with ZipFile(path) as archive:
            try:
                info = archive.getinfo("manifest.json")
            except KeyError:
                return {
                    "schema": schema,
                    "status": "invalid-release-manifest",
                    "status_source": "zip-manifest",
                }
            if info.file_size > REVIEW_ARTIFACT_MAX_JSON_BYTES:
                return {
                    "schema": schema,
                    "status": "skipped-large-manifest",
                    "status_source": "zip-manifest-size",
                }
            payload = json.loads(archive.read(info).decode("utf-8"))
    except (BadZipFile, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {
            "schema": schema,
            "status": "invalid-zip",
            "status_source": "zip-manifest-parse",
        }
    if not isinstance(payload, dict):
        return {
            "schema": schema,
            "status": "invalid-release-manifest",
            "status_source": "zip-manifest-root",
        }
    status, status_source = _review_status(payload)
    summary: dict[str, Any] = {
        "schema": payload.get("schema") or schema,
        "status": status,
        "status_source": "manifest." + status_source,
        "manifest_top_level_keys": sorted(str(key) for key in payload.keys())[:20],
    }
    artifact_status = payload.get("artifact_status")
    if isinstance(artifact_status, dict):
        summary["artifact_status"] = {
            str(key): int(value)
            for key, value in artifact_status.items()
            if isinstance(value, int)
        }
    matrix_gate_summaries = _release_matrix_gate_review_summaries(payload)
    if matrix_gate_summaries:
        summary["matrix_gate_review_summaries"] = matrix_gate_summaries
    harness_summaries = _release_harness_review_summaries(payload)
    if harness_summaries:
        summary["harness_review_summaries"] = harness_summaries
    suite_calibration_summaries = _release_suite_calibration_review_summaries(payload)
    if suite_calibration_summaries:
        summary["suite_calibration_summaries"] = suite_calibration_summaries
    advisory_summaries = _release_engine_advisory_review_summaries(payload)
    if advisory_summaries:
        summary["engine_advisory_summaries"] = advisory_summaries
    evidence_index_summaries = _release_evidence_index_review_summaries(payload)
    if evidence_index_summaries:
        summary["evidence_index_summaries"] = evidence_index_summaries
    suite_audit_summaries = _release_suite_audit_review_summaries(payload)
    if suite_audit_summaries:
        summary["suite_audit_summaries"] = suite_audit_summaries
    metric_coverage_summaries = _release_metric_coverage_review_summaries(payload)
    if metric_coverage_summaries:
        summary["metric_coverage_summaries"] = metric_coverage_summaries
    normalized_telemetry_summaries = _release_normalized_telemetry_review_summaries(payload)
    if normalized_telemetry_summaries:
        summary["normalized_telemetry_summaries"] = normalized_telemetry_summaries
    matrix_pressure_summaries = _release_matrix_pressure_review_summaries(payload)
    if matrix_pressure_summaries:
        summary["matrix_pressure_summaries"] = matrix_pressure_summaries
    matrix_saturation_summaries = _release_matrix_saturation_review_summaries(payload)
    if matrix_saturation_summaries:
        summary["matrix_saturation_summaries"] = matrix_saturation_summaries
    matrix_scorecard_summaries = _release_matrix_scorecard_review_summaries(payload)
    if matrix_scorecard_summaries:
        summary["matrix_scorecard_summaries"] = matrix_scorecard_summaries
    selftest_summaries = _release_selftest_report_summaries(payload)
    if selftest_summaries:
        summary["selftest_report_summaries"] = selftest_summaries
    benchmark_readiness_summaries = _release_benchmark_readiness_review_summaries(payload)
    if benchmark_readiness_summaries:
        summary["benchmark_readiness_summaries"] = benchmark_readiness_summaries
    provider_audit_summaries = _release_provider_audit_review_summaries(payload)
    if provider_audit_summaries:
        summary["provider_audit_summaries"] = provider_audit_summaries
    implementation_status_summaries = _release_implementation_status_review_summaries(payload)
    if implementation_status_summaries:
        summary["implementation_status_summaries"] = implementation_status_summaries
    campaign_preflight_summaries = _release_campaign_preflight_review_summaries(payload)
    if campaign_preflight_summaries:
        summary["campaign_preflight_summaries"] = campaign_preflight_summaries
    provider_contract_summaries = _release_provider_contract_review_summaries(payload)
    if provider_contract_summaries:
        summary["provider_contract_summaries"] = provider_contract_summaries
    publication_summaries = _release_publication_bundle_review_summaries(payload)
    if publication_summaries:
        summary["publication_bundle_summaries"] = publication_summaries
    matrix_publication_summaries = _release_matrix_publication_bundle_review_summaries(payload)
    if matrix_publication_summaries:
        summary["matrix_publication_bundle_summaries"] = matrix_publication_summaries
    publication_brief_summaries = _release_publication_brief_review_summaries(payload)
    if publication_brief_summaries:
        summary["publication_brief_summaries"] = publication_brief_summaries
    protocol_repair_summaries = _release_protocol_repair_posture_review_summaries(payload)
    if protocol_repair_summaries:
        summary["protocol_repair_posture_summaries"] = protocol_repair_summaries
    workflow_readiness_summaries = _release_workflow_readiness_review_summaries(payload)
    if workflow_readiness_summaries:
        summary["workflow_readiness_summaries"] = workflow_readiness_summaries
    security_posture_summaries = _release_security_posture_review_summaries(payload)
    if security_posture_summaries:
        summary["security_posture_summaries"] = security_posture_summaries
    sdlc_validation_manifest_summaries = _release_sdlc_validation_manifest_review_summaries(payload)
    if sdlc_validation_manifest_summaries:
        summary["sdlc_validation_manifest_summaries"] = sdlc_validation_manifest_summaries
    return summary


def _release_protocol_repair_posture_review_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return _release_review_summaries_for_categories(
        payload,
        categories={"publication/protocol-repair"},
        archive_prefixes=("publication/protocol-repair/",),
    )


def _release_workflow_readiness_review_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return _release_review_summaries_for_categories(
        payload,
        categories={"readiness/workflow"},
        archive_prefixes=("readiness/workflow/",),
    )


def _release_security_posture_review_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return _release_review_summaries_for_categories(
        payload,
        categories={"security/posture"},
        archive_prefixes=("security/posture/",),
    )


def _release_review_summaries_for_categories(
    payload: dict[str, Any],
    *,
    categories: set[str],
    archive_prefixes: tuple[str, ...],
) -> list[dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    summaries: list[dict[str, Any]] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        archive_path = str(artifact.get("archive_path") or "")
        if category not in categories and not any(archive_path.startswith(prefix) for prefix in archive_prefixes):
            continue
        review_summary = artifact.get("review_summary")
        if not isinstance(review_summary, dict):
            continue
        summary = {str(key): value for key, value in review_summary.items()}
        if archive_path:
            summary["archive_path"] = archive_path
        if artifact.get("status") is not None:
            summary["artifact_status"] = artifact.get("status")
        summaries.append(summary)
    return summaries[:12]


def _publication_bundle_zip_review_summary(path: Path, schema: str | None) -> dict[str, Any]:
    try:
        with ZipFile(path) as archive:
            try:
                info = archive.getinfo(PUBLICATION_BUNDLE_MANIFEST)
            except KeyError:
                return {
                    "schema": schema,
                    "status": "invalid-publication-manifest",
                    "status_source": "zip-publication-manifest",
                }
            if info.file_size > REVIEW_ARTIFACT_MAX_JSON_BYTES:
                return {
                    "schema": schema,
                    "status": "skipped-large-manifest",
                    "status_source": "zip-publication-manifest-size",
                }
            payload = json.loads(archive.read(info).decode("utf-8"))
    except (BadZipFile, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {
            "schema": schema,
            "status": "invalid-zip",
            "status_source": "zip-publication-manifest-parse",
        }
    if not isinstance(payload, dict):
        return {
            "schema": schema,
            "status": "invalid-publication-manifest",
            "status_source": "zip-publication-manifest-root",
        }
    schema_values = {str(value) for value in (payload.get("schema_version"), payload.get("schema")) if value is not None}
    if PUBLICATION_BUNDLE_MANIFEST_SCHEMA_VERSION not in schema_values:
        return {
            "schema": schema,
            "status": "invalid-publication-manifest",
            "status_source": "zip-publication-manifest-schema",
        }
    publication_summary = _publication_bundle_review_summary(payload, archive_path=path.name)
    status, status_source = _publication_bundle_review_status(publication_summary)
    return {
        "schema": payload.get("schema_version") or schema,
        "status": status,
        "status_source": "publication-manifest." + status_source,
        "manifest_top_level_keys": sorted(str(key) for key in payload.keys())[:20],
        "publication_bundle_summaries": [publication_summary],
    }


def _matrix_publication_bundle_zip_review_summary(path: Path, schema: str | None) -> dict[str, Any]:
    try:
        with ZipFile(path) as archive:
            try:
                info = archive.getinfo(MATRIX_PUBLICATION_BUNDLE_MANIFEST)
            except KeyError:
                return {
                    "schema": schema,
                    "status": "invalid-matrix-publication-manifest",
                    "status_source": "zip-matrix-publication-manifest",
                }
            if info.file_size > REVIEW_ARTIFACT_MAX_JSON_BYTES:
                return {
                    "schema": schema,
                    "status": "skipped-large-manifest",
                    "status_source": "zip-matrix-publication-manifest-size",
                }
            payload = json.loads(archive.read(info).decode("utf-8"))
    except (BadZipFile, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {
            "schema": schema,
            "status": "invalid-zip",
            "status_source": "zip-matrix-publication-manifest-parse",
        }
    if not isinstance(payload, dict):
        return {
            "schema": schema,
            "status": "invalid-matrix-publication-manifest",
            "status_source": "zip-matrix-publication-manifest-root",
        }
    schema_values = {str(value) for value in (payload.get("schema_version"), payload.get("schema")) if value is not None}
    if MATRIX_PUBLICATION_BUNDLE_MANIFEST_SCHEMA_VERSION not in schema_values:
        return {
            "schema": schema,
            "status": "invalid-matrix-publication-manifest",
            "status_source": "zip-matrix-publication-manifest-schema",
        }
    summary = _matrix_publication_bundle_review_summary(payload, archive_path=path.name)
    status, status_source = _matrix_publication_bundle_review_status(summary)
    return {
        "schema": payload.get("schema_version") or schema,
        "status": status,
        "status_source": "matrix-publication-manifest." + status_source,
        "manifest_top_level_keys": sorted(str(key) for key in payload.keys())[:20],
        "matrix_publication_bundle_summaries": [summary],
    }


def _publication_bundle_review_summary(payload: dict[str, Any], *, archive_path: str) -> dict[str, Any]:
    readiness = payload.get("publication_readiness") if isinstance(payload.get("publication_readiness"), dict) else {}
    security = payload.get("security") if isinstance(payload.get("security"), dict) else {}
    return {
        "archive_path": archive_path,
        "schema_version": PUBLICATION_BUNDLE_MANIFEST_SCHEMA_VERSION,
        "run_id": payload.get("run_id"),
        "artifact_count": _review_non_negative_int(payload.get("artifact_count")),
        "artifacts": _review_summary_string_list(payload.get("artifacts")),
        "media_kit": _review_media_kit_summary(payload.get("media_kit")),
        "publication_readiness": {
            "schema_version": readiness.get("schema_version"),
            "status": str(readiness.get("status") or "unknown"),
            "ready_for_external_publication": bool(readiness.get("ready_for_external_publication")),
            "ready_for_internal_review": bool(readiness.get("ready_for_internal_review")),
            "blocker_count": _review_non_negative_int(readiness.get("blocker_count")),
            "warning_count": _review_non_negative_int(readiness.get("warning_count")),
        },
        "security": {
            "contains_raw_secrets": bool(security.get("contains_raw_secrets")),
            "contains_raw_provider_payloads": bool(security.get("contains_raw_provider_payloads")),
            "contains_results_jsonl": bool(security.get("contains_results_jsonl")),
        },
    }


def _publication_bundle_review_status(summary: dict[str, Any]) -> tuple[str, str]:
    security = summary.get("security") if isinstance(summary.get("security"), dict) else {}
    if any(
        security.get(key) is True
        for key in ("contains_raw_secrets", "contains_raw_provider_payloads", "contains_results_jsonl")
    ):
        return "fail", "security"
    readiness = summary.get("publication_readiness") if isinstance(summary.get("publication_readiness"), dict) else {}
    status = readiness.get("status")
    if status == "blocked":
        return "fail", "publication_readiness.status"
    media_status, media_status_source = _publication_media_kit_review_status(summary)
    if media_status == "review":
        return "review", media_status_source
    if status == "ready":
        return "pass", "publication_readiness.status"
    return "review", "publication_readiness.status"


def _publication_media_kit_review_status(summary: dict[str, Any]) -> tuple[str, str]:
    media_kit = summary.get("media_kit") if isinstance(summary.get("media_kit"), dict) else {}
    if media_kit.get("schema_version") != MEDIA_KIT_SCHEMA_VERSION:
        return "review", "media_kit.schema_version"
    missing = media_kit.get("missing_recommended_assets")
    if isinstance(missing, list) and missing:
        return "review", "media_kit.missing_recommended_assets"
    return "pass", "media_kit"


def _matrix_publication_bundle_review_summary(payload: dict[str, Any], *, archive_path: str) -> dict[str, Any]:
    security = payload.get("security") if isinstance(payload.get("security"), dict) else {}
    matrix = payload.get("matrix") if isinstance(payload.get("matrix"), dict) else {}
    return {
        "archive_path": archive_path,
        "schema_version": MATRIX_PUBLICATION_BUNDLE_MANIFEST_SCHEMA_VERSION,
        "artifact_count": _review_non_negative_int(payload.get("artifact_count")),
        "artifacts": _review_summary_string_list(payload.get("artifacts")),
        "matrix": {
            "artifact_stem": matrix.get("artifact_stem"),
            "summary_artifact": matrix.get("summary_artifact"),
            "scorecard_artifact": matrix.get("scorecard_artifact"),
        },
        "engine_targets": _compact_engine_targets(payload.get("engine_targets")),
        "architecture_summary": _compact_scorecard_group_summary(
            payload.get("architecture_summary"),
            key="model_architecture",
        ),
        "quantization_summary": _compact_scorecard_group_summary(
            payload.get("quantization_summary"),
            key="quantization",
        ),
        "media_kit": _review_media_kit_summary(payload.get("media_kit")),
        "security": {
            "contains_raw_secrets": bool(security.get("contains_raw_secrets")),
            "contains_raw_provider_payloads": bool(security.get("contains_raw_provider_payloads")),
            "contains_results_jsonl": bool(security.get("contains_results_jsonl")),
            "contains_per_run_raw_traces": bool(security.get("contains_per_run_raw_traces")),
        },
    }


def _matrix_publication_bundle_review_status(summary: dict[str, Any]) -> tuple[str, str]:
    security = summary.get("security") if isinstance(summary.get("security"), dict) else {}
    if any(
        security.get(key) is True
        for key in (
            "contains_raw_secrets",
            "contains_raw_provider_payloads",
            "contains_results_jsonl",
            "contains_per_run_raw_traces",
        )
    ):
        return "fail", "security"
    media_kit = summary.get("media_kit") if isinstance(summary.get("media_kit"), dict) else {}
    if media_kit.get("schema_version") != MEDIA_KIT_SCHEMA_VERSION:
        return "review", "media_kit.schema_version"
    missing = media_kit.get("missing_recommended_assets")
    if isinstance(missing, list) and missing:
        return "review", "media_kit.missing_recommended_assets"
    return "pass", "media_kit"


def _review_media_kit_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {
            "schema_version": None,
            "asset_count": 0,
            "missing_recommended_assets": [],
            "available_recommended_sets": [],
            "asset_roles": [],
        }
    assets = value.get("assets") if isinstance(value.get("assets"), list) else []
    recommended_sets = value.get("recommended_sets") if isinstance(value.get("recommended_sets"), list) else []
    return {
        "schema_version": value.get("schema_version"),
        "asset_count": _review_non_negative_int(value.get("asset_count")),
        "missing_recommended_assets": _review_summary_string_list(value.get("missing_recommended_assets")),
        "available_recommended_sets": [
            str(item.get("name"))
            for item in recommended_sets
            if isinstance(item, dict) and item.get("available") is True and item.get("name")
        ][:12],
        "asset_roles": [
            {
                "artifact": str(item.get("artifact")),
                "role": str(item.get("role")),
                "media_type": str(item.get("media_type")),
                "present": bool(item.get("present")),
            }
            for item in assets[:20]
            if isinstance(item, dict) and item.get("artifact")
        ],
    }


def _release_matrix_gate_review_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    summaries = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        archive_path = str(artifact.get("archive_path") or "")
        if category != "gates/matrix" and not archive_path.startswith("gates/matrix/"):
            continue
        review_summary = artifact.get("review_summary")
        if not isinstance(review_summary, dict):
            continue
        safe_summary = {
            "archive_path": archive_path,
            "schema_version": review_summary.get("schema_version") or artifact.get("schema"),
            "status": artifact.get("status"),
        }
        for key in (
            "matrix_name",
            "pass_rate_percent",
            "failure_class_summary",
            "failure_class_artifacts_missing",
            "tool_loop_stop_summary",
            "tool_loop_artifacts_missing",
            "invalid_tool_call_count",
            "tool_parser_repair_cases",
            "tool_parser_repairs_valid",
            "tool_parser_repair_valid_rate_percent",
            "tool_parser_repair_artifacts_missing",
            "failure_class_gate_count",
            "failure_class_gate_findings",
            "tool_loop_stop_gate_count",
            "tool_loop_stop_gate_findings",
            "tool_parser_repair_gate_count",
            "tool_parser_repair_gate_findings",
        ):
            if key in review_summary:
                safe_summary[key] = review_summary[key]
        summaries.append(safe_summary)
    return summaries[:12]


def _release_harness_review_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    summaries = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        archive_path = str(artifact.get("archive_path") or "")
        if category != "harness/review" and not archive_path.startswith("harness/review/"):
            continue
        review_summary = artifact.get("review_summary")
        if not isinstance(review_summary, dict):
            continue
        safe_summary = {
            "archive_path": archive_path,
            "schema_version": review_summary.get("schema_version") or artifact.get("schema"),
            "status": artifact.get("status"),
        }
        for key in (
            "suite_name",
            "case_count",
            "generated",
            "generator_profile",
            "review_status",
            "human_review_required",
            "calibration_required_before_release_gate",
            "surface_counts",
            "assertion_counts",
        ):
            if key in review_summary:
                safe_summary[key] = review_summary[key]
        summaries.append(safe_summary)
    return summaries[:12]


def _release_suite_calibration_review_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    summaries = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        archive_path = str(artifact.get("archive_path") or "")
        if category != "harness/calibration" and not archive_path.startswith("harness/calibration/"):
            continue
        review_summary = artifact.get("review_summary")
        if not isinstance(review_summary, dict):
            continue
        safe_summary = {
            "archive_path": archive_path,
            "schema_version": review_summary.get("schema_version") or artifact.get("schema"),
            "status": artifact.get("status"),
        }
        for key in (
            "suite",
            "generated",
            "require_release_gate",
            "passed",
            "known_good_runs",
            "known_bad_cases",
            "failure_taxonomy_entries",
            "findings",
            "warnings",
        ):
            if key in review_summary:
                safe_summary[key] = review_summary[key]
        summaries.append(safe_summary)
    return summaries[:12]


def _release_engine_advisory_review_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    summaries = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        archive_path = str(artifact.get("archive_path") or "")
        if category != "advisory/engine" and not archive_path.startswith("advisory/engine/"):
            continue
        review_summary = artifact.get("review_summary")
        if not isinstance(review_summary, dict):
            continue
        safe_summary = {
            "archive_path": archive_path,
            "schema_version": review_summary.get("schema_version") or artifact.get("schema"),
            "status": artifact.get("status"),
        }
        for key in ("engine", "priority_count", "highest_priority", "no_dispatch", "top_priorities"):
            if key in review_summary:
                safe_summary[key] = review_summary[key]
        summaries.append(safe_summary)
    return summaries[:12]


def _release_evidence_index_review_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    summaries = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        archive_path = str(artifact.get("archive_path") or "")
        if category != "evidence/index" and not archive_path.startswith("evidence/index/"):
            continue
        review_summary = artifact.get("review_summary")
        if not isinstance(review_summary, dict):
            continue
        safe_summary = {
            "archive_path": archive_path,
            "schema_version": review_summary.get("schema_version") or artifact.get("schema"),
            "status": artifact.get("status"),
        }
        for key in ("name", "artifact_count", "status_counts", "readiness", "cleanup_evidence"):
            if key in review_summary:
                safe_summary[key] = review_summary[key]
        summaries.append(safe_summary)
    return summaries[:12]


def _release_suite_audit_review_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    summaries = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        archive_path = str(artifact.get("archive_path") or "")
        if category != "governance/suite-audit" and not archive_path.startswith("governance/suite-audit/"):
            continue
        review_summary = artifact.get("review_summary")
        if not isinstance(review_summary, dict):
            continue
        safe_summary = {
            "archive_path": archive_path,
            "schema_version": review_summary.get("schema_version") or artifact.get("schema"),
            "status": artifact.get("status"),
        }
        for key in (
            "suite",
            "total_cases",
            "finding_count",
            "finding_codes",
            "provenance_counts",
            "risk_counts",
            "duplicate_fingerprint_count",
        ):
            if key in review_summary:
                safe_summary[key] = review_summary[key]
        summaries.append(safe_summary)
    return summaries[:12]


def _release_metric_coverage_review_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    summaries = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        archive_path = str(artifact.get("archive_path") or "")
        if category != "metrics/coverage" and not archive_path.startswith("metrics/coverage/"):
            continue
        review_summary = artifact.get("review_summary")
        if not isinstance(review_summary, dict):
            continue
        safe_summary = {
            "archive_path": archive_path,
            "schema_version": review_summary.get("schema_version") or artifact.get("schema"),
            "status": artifact.get("status"),
        }
        for key in (
            "provider",
            "contract",
            "native_adapter",
            "coverage_score",
            "field_count",
            "counts",
            "publication_grade_group_count",
            "advisory_group_count",
            "partial_group_count",
            "unavailable_group_count",
            "publication_grade_groups",
            "review_required_groups",
        ):
            if key in review_summary:
                safe_summary[key] = review_summary[key]
        summaries.append(safe_summary)
    return summaries[:12]


def _release_normalized_telemetry_review_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    summaries = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        archive_path = str(artifact.get("archive_path") or "")
        if category != "metrics/normalized-telemetry" and not archive_path.startswith("metrics/normalized-telemetry/"):
            continue
        review_summary = artifact.get("review_summary")
        if not isinstance(review_summary, dict):
            continue
        safe_summary = {
            "archive_path": archive_path,
            "schema_version": review_summary.get("schema_version") or artifact.get("schema"),
            "status": artifact.get("status"),
        }
        for key in (
            "contract",
            "native_adapter",
            "stats_profile",
            "populated_field_count",
            "missing_field_count",
            "publication_grade_field_count",
            "advisory_field_count",
            "raw_provenance_field_count",
            "comparison_guidance",
            "quality_counts",
            "stats_requires_labeling",
            "stats_guidance",
            "stats_publication_grade_fields",
            "stats_advisory_fields",
            "missing_stats_fields",
        ):
            if key in review_summary:
                safe_summary[key] = review_summary[key]
        summaries.append(safe_summary)
    return summaries[:12]


def _release_matrix_pressure_review_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    summaries = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        archive_path = str(artifact.get("archive_path") or "")
        if category != "audits/matrix-pressure" and not archive_path.startswith("audits/matrix-pressure/"):
            continue
        review_summary = artifact.get("review_summary")
        if not isinstance(review_summary, dict):
            continue
        safe_summary = {
            "archive_path": archive_path,
            "schema_version": review_summary.get("schema_version") or artifact.get("schema"),
            "status": artifact.get("status"),
        }
        for key in (
            "matrix",
            "run_count",
            "case_count",
            "scheduled_prompt_tokens",
            "concurrent_window_prompt_tokens",
            "prefill_pressure_score",
            "concurrency_weighted_pressure_score",
            "shared_static_prefix_groups",
            "shared_static_prefix_tokens",
            "shared_static_reuse_tokens",
            "engines",
            "models",
            "suites",
            "concurrency_levels",
            "highest_pressure_runs",
        ):
            if key in review_summary:
                safe_summary[key] = review_summary[key]
        summaries.append(safe_summary)
    return summaries[:12]


def _release_matrix_saturation_review_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    summaries = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        archive_path = str(artifact.get("archive_path") or "")
        if category != "audits/matrix-saturation" and not archive_path.startswith("audits/matrix-saturation/"):
            continue
        review_summary = artifact.get("review_summary")
        if not isinstance(review_summary, dict):
            continue
        safe_summary = {
            "archive_path": archive_path,
            "schema_version": review_summary.get("schema_version") or artifact.get("schema"),
            "status": artifact.get("status"),
        }
        for key in (
            "matrix",
            "ok",
            "entry_count",
            "group_count",
            "result_artifacts_loaded",
            "result_artifacts_missing",
            "max_concurrency",
            "multi_level_group_count",
            "concurrency_levels",
            "max_avg_queue_ms",
            "max_avg_rate_limit_wait_ms",
            "queue_wait_finding_count",
            "rate_limit_wait_finding_count",
            "guidance",
            "highest_queue_wait_entries",
            "highest_rate_limit_wait_entries",
        ):
            if key in review_summary:
                safe_summary[key] = review_summary[key]
        summaries.append(safe_summary)
    return summaries[:12]


def _release_publication_bundle_review_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    summaries = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        archive_path = str(artifact.get("archive_path") or "")
        is_run_publication_archive = (
            archive_path.startswith("publication/")
            and not archive_path.startswith("publication/matrix/")
            and not archive_path.startswith("publication/brief/")
        )
        if category != "publication" and not is_run_publication_archive:
            continue
        review_summary = artifact.get("review_summary")
        if not isinstance(review_summary, dict):
            continue
        safe_summary = {
            "archive_path": archive_path,
            "schema_version": review_summary.get("schema_version") or artifact.get("manifest_schema") or artifact.get("schema"),
            "status": artifact.get("status"),
        }
        for key in (
            "run_id",
            "artifact_count",
            "artifacts",
            "media_kit",
            "publication_readiness",
            "security",
        ):
            if key in review_summary:
                safe_summary[key] = review_summary[key]
        summaries.append(safe_summary)
    return summaries[:12]


def _release_matrix_publication_bundle_review_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    summaries = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        archive_path = str(artifact.get("archive_path") or "")
        if category != "publication/matrix" and not archive_path.startswith("publication/matrix/"):
            continue
        review_summary = artifact.get("review_summary")
        if not isinstance(review_summary, dict):
            continue
        safe_summary = _matrix_publication_bundle_review_summary(review_summary, archive_path=archive_path)
        safe_summary["schema_version"] = review_summary.get("schema_version") or artifact.get("manifest_schema") or artifact.get("schema")
        safe_summary["status"] = artifact.get("status")
        summaries.append(safe_summary)
    return summaries[:12]


def _release_publication_brief_review_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    summaries = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        archive_path = str(artifact.get("archive_path") or "")
        if category != "publication/brief" and not archive_path.startswith("publication/brief/"):
            continue
        review_summary = artifact.get("review_summary")
        if not isinstance(review_summary, dict):
            continue
        safe_summary = _publication_brief_review_summary(review_summary)
        safe_summary["archive_path"] = archive_path
        safe_summary["status"] = artifact.get("status") or safe_summary.get("status")
        summaries.append(safe_summary)
    return summaries[:12]


def _release_matrix_scorecard_review_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    summaries = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        archive_path = str(artifact.get("archive_path") or "")
        if category != "reports/matrix-scorecard" and not archive_path.startswith("reports/matrix-scorecard/"):
            continue
        review_summary = artifact.get("review_summary")
        if not isinstance(review_summary, dict):
            continue
        safe_summary = _matrix_scorecard_review_summary(review_summary)
        safe_summary["archive_path"] = archive_path
        safe_summary["status"] = artifact.get("status") or safe_summary.get("status")
        summaries.append(safe_summary)
    return summaries[:12]


def _release_selftest_report_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    summaries = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        archive_path = str(artifact.get("archive_path") or "")
        if (
            category == "selftest/validation-manifest"
            or archive_path.startswith("selftest/validation-manifest/")
            or archive_path.endswith("/sdlc-validation-manifest.json")
        ):
            continue
        if category != "selftest" and not archive_path.startswith("selftest/"):
            continue
        review_summary = artifact.get("review_summary")
        if not isinstance(review_summary, dict):
            continue
        safe_summary = _selftest_review_summary(review_summary)
        safe_summary["archive_path"] = archive_path
        safe_summary["status"] = artifact.get("status") or safe_summary.get("status")
        summaries.append(safe_summary)
    return summaries[:12]


def _release_sdlc_validation_manifest_review_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    summaries = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        archive_path = str(artifact.get("archive_path") or "")
        if (
            category != "selftest/validation-manifest"
            and not archive_path.startswith("selftest/validation-manifest/")
            and not archive_path.endswith("/sdlc-validation-manifest.json")
        ):
            continue
        review_summary = artifact.get("review_summary")
        if not isinstance(review_summary, dict):
            continue
        safe_summary = _sdlc_validation_manifest_review_summary(review_summary)
        safe_summary["archive_path"] = archive_path
        safe_summary["status"] = artifact.get("status") or safe_summary.get("status")
        summaries.append(safe_summary)
    return summaries[:12]


def _release_benchmark_readiness_review_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    summaries = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        archive_path = str(artifact.get("archive_path") or "")
        if category != "readiness/benchmark" and not archive_path.startswith("readiness/benchmark/"):
            continue
        review_summary = artifact.get("review_summary")
        if not isinstance(review_summary, dict):
            continue
        safe_summary = _benchmark_readiness_review_summary(review_summary)
        safe_summary["archive_path"] = archive_path
        safe_summary["status"] = artifact.get("status") or safe_summary.get("status")
        summaries.append(safe_summary)
    return summaries[:12]


def _release_provider_audit_review_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    summaries = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        archive_path = str(artifact.get("archive_path") or "")
        if category != "security/provider-audit" and not archive_path.startswith("security/provider-audit/"):
            continue
        review_summary = artifact.get("review_summary")
        if not isinstance(review_summary, dict):
            continue
        safe_summary = _provider_audit_review_summary(review_summary)
        safe_summary["archive_path"] = archive_path
        safe_summary["status"] = artifact.get("status") or safe_summary.get("status")
        summaries.append(safe_summary)
    return summaries[:12]


def _release_implementation_status_review_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    summaries = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        archive_path = str(artifact.get("archive_path") or "")
        if category != "readiness/implementation" and not archive_path.startswith("readiness/implementation/"):
            continue
        review_summary = artifact.get("review_summary")
        if not isinstance(review_summary, dict):
            continue
        safe_summary = _implementation_status_review_summary(review_summary)
        safe_summary["archive_path"] = archive_path
        safe_summary["status"] = artifact.get("status") or safe_summary.get("status")
        summaries.append(safe_summary)
    return summaries[:12]


def _release_provider_contract_review_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    summaries = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        archive_path = str(artifact.get("archive_path") or "")
        if (
            category not in {"audits/provider-contract", "audits/provider-contract-matrix"}
            and not archive_path.startswith("audits/provider-contract/")
            and not archive_path.startswith("audits/provider-contract-matrix/")
        ):
            continue
        review_summary = artifact.get("review_summary")
        if not isinstance(review_summary, dict):
            continue
        safe_summary = _provider_contract_review_summary(review_summary)
        safe_summary["archive_path"] = archive_path
        safe_summary["status"] = artifact.get("status")
        summaries.append(safe_summary)
    return summaries[:12]


def _release_campaign_preflight_review_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    summaries = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        category = str(artifact.get("category") or "")
        archive_path = str(artifact.get("archive_path") or "")
        if category != "readiness/campaign-preflight" and not archive_path.startswith("readiness/campaign-preflight/"):
            continue
        review_summary = artifact.get("review_summary")
        if not isinstance(review_summary, dict):
            continue
        safe_summary = {
            "archive_path": archive_path,
            "schema_version": review_summary.get("schema_version") or artifact.get("schema"),
            "review_summary_schema_version": review_summary.get("review_summary_schema_version"),
            "status": artifact.get("status"),
            "matrix_count": _review_non_negative_int(review_summary.get("matrix_count")),
            "run_count": _review_non_negative_int(review_summary.get("run_count")),
            "total_cases": _review_non_negative_int(review_summary.get("total_cases")),
            "includes_provider_audit": bool(review_summary.get("includes_provider_audit")),
            "includes_benchmark_readiness": bool(review_summary.get("includes_benchmark_readiness")),
            "benchmark_readiness_report_count": _review_non_negative_int(
                review_summary.get("benchmark_readiness_report_count")
            ),
            "contains_local_paths": bool(review_summary.get("contains_local_paths")),
            "external_publication_safe": bool(review_summary.get("external_publication_safe")),
        }
        summaries.append({key: value for key, value in safe_summary.items() if value is not None})
    return summaries[:12]


def _provider_contract_json_review_summary(payload: dict[str, Any]) -> dict[str, Any] | None:
    schema = payload.get("schema_version") or payload.get("schema")
    if schema not in {"agentblaster.provider-contract-check.v1", "agentblaster.provider-contract-matrix.v1"}:
        return None
    return _provider_contract_review_summary(payload)


def _provider_contract_review_summary(payload: dict[str, Any]) -> dict[str, Any]:
    schema = str(payload.get("schema_version") or payload.get("schema") or "unknown")
    provider = payload.get("provider") if isinstance(payload.get("provider"), dict) else {}
    matrix = payload.get("matrix") if isinstance(payload.get("matrix"), dict) else {}
    report_summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    summary: dict[str, Any] = {
        "schema_version": schema,
        "mode": payload.get("mode"),
        "ok": payload.get("ok"),
    }
    if provider:
        summary["provider"] = provider.get("name")
        summary["contract"] = provider.get("contract")
    elif payload.get("provider") is not None:
        summary["provider"] = payload.get("provider")
    if payload.get("contract") is not None:
        summary["contract"] = payload.get("contract")
    if matrix:
        summary["matrix"] = matrix.get("name")
        summary["target_count"] = _review_non_negative_int(matrix.get("target_count"))
    elif payload.get("matrix") is not None:
        summary["matrix"] = payload.get("matrix")
    if payload.get("target_count") is not None:
        summary["target_count"] = _review_non_negative_int(payload.get("target_count"))
    if payload.get("model") is not None:
        summary["model"] = payload.get("model")
    check_counts = {
        key: _review_non_negative_int(report_summary.get(key))
        for key in (
            "planned",
            "passed",
            "failed",
            "skipped",
            "planned_checks",
            "passed_checks",
            "failed_checks",
            "skipped_checks",
        )
        if key in report_summary
    }
    if check_counts:
        summary["checks"] = check_counts
    evidence = _compact_provider_contract_capability_evidence(payload.get("capability_evidence"))
    if evidence["directly_checked"] or evidence["proxy_checked_counts"] or evidence["not_covered_counts"]:
        summary["capability_evidence"] = evidence
    return {key: value for key, value in summary.items() if value is not None}


def _compact_provider_contract_capability_evidence(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"directly_checked": [], "proxy_checked_counts": {}, "not_covered_counts": {}}
    directly_checked = value.get("directly_checked") if isinstance(value.get("directly_checked"), list) else []
    proxy_counts: dict[str, int] = {}
    not_covered_counts: dict[str, int] = {}
    proxy_count_map = value.get("proxy_checked_counts")
    if isinstance(proxy_count_map, dict):
        _merge_review_count_map(proxy_counts, proxy_count_map)
    else:
        _count_review_capability_items(proxy_counts, value.get("proxy_checked"))
    not_covered_count_map = value.get("not_covered_counts")
    if isinstance(not_covered_count_map, dict):
        _merge_review_count_map(not_covered_counts, not_covered_count_map)
    else:
        _count_review_capability_items(not_covered_counts, value.get("not_covered"))
    return {
        "directly_checked": sorted({str(item) for item in directly_checked}),
        "proxy_checked_counts": dict(sorted(proxy_counts.items())),
        "not_covered_counts": dict(sorted(not_covered_counts.items())),
    }


def _count_review_capability_items(counts: dict[str, int], value: Any) -> None:
    if not isinstance(value, list):
        return
    for item in value:
        if isinstance(item, dict) and item.get("capability"):
            capability = str(item["capability"])
            counts[capability] = counts.get(capability, 0) + 1


def _merge_review_count_map(target: dict[str, int], value: Any) -> None:
    if not isinstance(value, dict):
        return
    for key, count in value.items():
        target[str(key)] = target.get(str(key), 0) + _review_non_negative_int(count)


def _harness_json_review_summary(payload: dict[str, Any]) -> dict[str, Any] | None:
    schema = payload.get("schema_version") or payload.get("schema")
    if schema != HARNESS_REVIEW_SCHEMA_VERSION:
        return None
    suite = payload.get("suite") if isinstance(payload.get("suite"), dict) else {}
    review = payload.get("review") if isinstance(payload.get("review"), dict) else {}
    generator = payload.get("generator") if isinstance(payload.get("generator"), dict) else {}
    surface_counts = payload.get("surface_counts") if isinstance(payload.get("surface_counts"), dict) else {}
    assertion_counts = payload.get("assertion_counts") if isinstance(payload.get("assertion_counts"), dict) else {}
    summary: dict[str, Any] = {
        "archive_path": str(suite.get("name") or "harness-review.json"),
        "schema_version": HARNESS_REVIEW_SCHEMA_VERSION,
        "status": "review",
        "suite_name": suite.get("name"),
        "case_count": _review_non_negative_int(suite.get("case_count")),
        "generated": bool(payload.get("generated")),
        "generator_profile": generator.get("profile"),
        "review_status": review.get("status"),
        "human_review_required": bool(review.get("human_review_required")),
        "calibration_required_before_release_gate": bool(review.get("calibration_required_before_release_gate")),
    }
    compact_surfaces = {
        key: _review_non_negative_int(surface_counts.get(key))
        for key in (
            "tool_schema_cases",
            "multi_tool_catalog_cases",
            "tool_loop_cases",
            "mcp_profile_cases",
            "lcp_profile_cases",
            "skill_cases",
            "cache_control_cases",
            "cancellation_cases",
        )
        if key in surface_counts
    }
    compact_assertions = {
        key: _review_non_negative_int(assertion_counts.get(key))
        for key in ("substring", "json_fields", "tool_name", "tool_result")
        if key in assertion_counts
    }
    if compact_surfaces:
        summary["surface_counts"] = compact_surfaces
    if compact_assertions:
        summary["assertion_counts"] = compact_assertions
    return {key: value for key, value in summary.items() if value is not None}


def _suite_calibration_json_review_summary(payload: dict[str, Any]) -> dict[str, Any] | None:
    schema = payload.get("schema_version") or payload.get("schema")
    if schema != CALIBRATION_REPORT_SCHEMA_VERSION:
        return None
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "archive_path": str(payload.get("suite") or "suite-calibration-report.json"),
        "schema_version": CALIBRATION_REPORT_SCHEMA_VERSION,
        "status": "pass" if payload.get("passed") is True else "fail",
        "suite": payload.get("suite"),
        "generated": bool(payload.get("generated")),
        "require_release_gate": bool(payload.get("require_release_gate")),
        "passed": bool(payload.get("passed")),
        "known_good_runs": _review_non_negative_int(summary.get("known_good_runs")),
        "known_bad_cases": _review_non_negative_int(summary.get("known_bad_cases")),
        "failure_taxonomy_entries": _review_non_negative_int(summary.get("failure_taxonomy_entries")),
        "findings": _review_non_negative_int(summary.get("findings")),
        "warnings": _review_non_negative_int(summary.get("warnings")),
    }


def _engine_advisory_json_review_summary(payload: dict[str, Any]) -> dict[str, Any] | None:
    schema = payload.get("schema_version") or payload.get("schema")
    if schema != ENGINE_ADVISORY_SCHEMA_VERSION:
        return None
    summary_block = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    summary = {
        "archive_path": str(payload.get("engine") or "engine-advisory.json"),
        "schema_version": ENGINE_ADVISORY_SCHEMA_VERSION,
        "status": "review",
        "engine": payload.get("engine"),
        "priority_count": _review_non_negative_int(summary_block.get("priority_count")),
        "highest_priority": summary_block.get("highest_priority"),
        "no_dispatch": bool(summary_block.get("no_dispatch")),
        "top_priorities": _compact_engine_priorities(payload.get("priorities")),
    }
    return {key: value for key, value in summary.items() if value is not None}


def _evidence_index_json_review_summary(payload: dict[str, Any]) -> dict[str, Any] | None:
    schema = payload.get("schema_version") or payload.get("schema")
    if schema != EVIDENCE_INDEX_SCHEMA_VERSION:
        return None
    cleanup_evidence = _review_cleanup_evidence_summary(payload.get("cleanup_evidence"))
    summary = {
        "archive_path": str(payload.get("name") or "evidence-index.json"),
        "schema_version": EVIDENCE_INDEX_SCHEMA_VERSION,
        "status": "review",
        "name": payload.get("name"),
        "artifact_count": _review_non_negative_int(payload.get("artifact_count")),
        "status_counts": _review_int_map(payload.get("status_counts")),
        "readiness": _review_readiness_summary(payload.get("readiness")),
    }
    if cleanup_evidence:
        summary["cleanup_evidence"] = cleanup_evidence
    return {key: value for key, value in summary.items() if value is not None}


def _cleanup_json_review_summary(payload: dict[str, Any]) -> dict[str, Any] | None:
    schema = payload.get("schema_version") or payload.get("schema")
    if schema not in {CLEANUP_PLAN_SCHEMA_VERSION, RETENTION_CLEANUP_SCHEMA_VERSION}:
        return None
    security = payload.get("security") if isinstance(payload.get("security"), dict) else {}
    selectors = payload.get("selectors") if isinstance(payload.get("selectors"), dict) else {}
    actions = payload.get("actions") if isinstance(payload.get("actions"), list) else []
    return {
        "schema_version": schema,
        "report_type": payload.get("report_type"),
        "execute": bool(payload.get("execute")),
        "action_count": _review_non_negative_int(payload.get("action_count")),
        "selector_count": len([key for key, value in selectors.items() if value is True]),
        "action_types": sorted(
            {
                str(item.get("action"))
                for item in actions
                if isinstance(item, dict) and item.get("action")
            }
        ),
        "contains_raw_secrets": bool(security.get("contains_raw_secrets")),
        "contains_raw_provider_payloads": bool(security.get("contains_raw_provider_payloads")),
        "reads_keyring_values": bool(security.get("reads_keyring_values")),
        "contacts_providers": bool(security.get("contacts_providers")),
        "contains_local_paths": bool(security.get("contains_local_paths", True)),
        "direct_publication_safe": bool(security.get("direct_publication_safe")),
        "audit_log_required": bool(security.get("audit_log_required")),
    }


def _campaign_preflight_json_review_summary(payload: dict[str, Any]) -> dict[str, Any] | None:
    schema = payload.get("schema_version") or payload.get("schema")
    if schema != CAMPAIGN_PREFLIGHT_SCHEMA_VERSION:
        return None
    review_summary = payload.get("review_summary") if isinstance(payload.get("review_summary"), dict) else {}
    security = review_summary.get("security") if isinstance(review_summary.get("security"), dict) else {}
    manifest_security = payload.get("security") if isinstance(payload.get("security"), dict) else {}
    uses_review_summary = bool(review_summary)
    benchmark_readiness = payload.get("benchmark_readiness") if isinstance(payload.get("benchmark_readiness"), dict) else {}
    return {
        "schema_version": CAMPAIGN_PREFLIGHT_SCHEMA_VERSION,
        "review_summary_schema_version": review_summary.get("schema_version"),
        "matrix_count": _review_non_negative_int(review_summary.get("matrix_count") or payload.get("matrix_count")),
        "run_count": _review_non_negative_int(review_summary.get("run_count")),
        "total_cases": _review_non_negative_int(review_summary.get("total_cases")),
        "includes_provider_audit": bool(
            review_summary.get("includes_provider_audit") or payload.get("includes_provider_audit")
        ),
        "includes_benchmark_readiness": bool(
            review_summary.get("includes_benchmark_readiness") or payload.get("includes_benchmark_readiness")
        ),
        "benchmark_readiness_report_count": _review_non_negative_int(
            review_summary.get("benchmark_readiness_report_count") or benchmark_readiness.get("report_count")
        ),
        "contains_local_paths": bool(
            security.get("contains_local_paths")
            if uses_review_summary
            else manifest_security.get("contains_local_paths", True)
        ),
        "external_publication_safe": bool(security.get("external_publication_safe")) if uses_review_summary else False,
    }


def _suite_audit_json_review_summary(payload: dict[str, Any]) -> dict[str, Any] | None:
    schema = payload.get("schema_version") or payload.get("schema")
    if schema != SUITE_AUDIT_SCHEMA_VERSION:
        return None
    findings = payload.get("findings") if isinstance(payload.get("findings"), list) else []
    dataset_hygiene = payload.get("dataset_hygiene") if isinstance(payload.get("dataset_hygiene"), dict) else {}
    finding_codes = sorted(
        {
            str(item.get("code"))
            for item in findings
            if isinstance(item, dict) and item.get("code")
        }
    )
    summary = {
        "archive_path": str(payload.get("suite") or "suite-audit.json"),
        "schema_version": SUITE_AUDIT_SCHEMA_VERSION,
        "status": "review",
        "suite": payload.get("suite"),
        "total_cases": _review_non_negative_int(payload.get("total_cases")),
        "finding_count": len(findings),
        "finding_codes": finding_codes[:12],
        "provenance_counts": _review_int_map(payload.get("provenance_counts")),
        "risk_counts": _review_int_map(payload.get("risk_counts")),
        "duplicate_fingerprint_count": _review_non_negative_int(dataset_hygiene.get("duplicate_fingerprint_count")),
    }
    return {key: value for key, value in summary.items() if value is not None}


def _metric_coverage_json_review_summary(payload: dict[str, Any]) -> dict[str, Any] | None:
    schema = payload.get("schema_version") or payload.get("schema")
    if schema != METRIC_COVERAGE_SCHEMA_VERSION:
        return None
    provider = payload.get("provider") if isinstance(payload.get("provider"), dict) else {}
    summary_block = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    comparability = payload.get("comparability") if isinstance(payload.get("comparability"), dict) else {}
    claim_contract = payload.get("claim_contract") if isinstance(payload.get("claim_contract"), dict) else {}
    summary = {
        "archive_path": str(provider.get("name") or "metric-coverage.json"),
        "schema_version": METRIC_COVERAGE_SCHEMA_VERSION,
        "status": "review",
        "provider": provider.get("name"),
        "contract": provider.get("contract"),
        "native_adapter": provider.get("native_adapter"),
        "coverage_score": summary_block.get("coverage_score"),
        "field_count": _review_non_negative_int(summary_block.get("field_count")),
        "counts": _review_int_map(summary_block.get("counts")),
        "publication_grade_group_count": _review_non_negative_int(comparability.get("publication_grade_group_count")),
        "advisory_group_count": _review_non_negative_int(comparability.get("advisory_group_count")),
        "partial_group_count": _review_non_negative_int(comparability.get("partial_group_count")),
        "unavailable_group_count": _review_non_negative_int(comparability.get("unavailable_group_count")),
        "publication_grade_groups": _review_summary_string_list(comparability.get("publication_grade_groups")),
        "review_required_groups": _review_summary_string_list(comparability.get("review_required_groups")),
        "claim_contract": _review_compact_metric_claim_contract(claim_contract),
    }
    return {key: value for key, value in summary.items() if value is not None}


def _review_compact_metric_claim_contract(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "schema_version": value.get("schema_version"),
        "claim_status_counts": _review_int_map(value.get("claim_status_counts")),
        "leaderboard_eligible_groups": _review_summary_string_list(value.get("leaderboard_eligible_groups")),
        "disclosure_required_groups": _review_summary_string_list(value.get("disclosure_required_groups")),
        "primary_score_policy": value.get("primary_score_policy"),
    }


def _normalized_telemetry_json_review_summary(payload: dict[str, Any]) -> dict[str, Any] | None:
    schema = payload.get("schema_version") or payload.get("schema")
    if schema != NORMALIZED_TELEMETRY_SCHEMA_VERSION:
        return None
    values = payload.get("values") if isinstance(payload.get("values"), dict) else {}
    quality = payload.get("quality") if isinstance(payload.get("quality"), dict) else {}
    comparison = payload.get("comparison_readiness") if isinstance(payload.get("comparison_readiness"), dict) else {}
    stats = payload.get("stats_comparability") if isinstance(payload.get("stats_comparability"), dict) else {}
    quality_counts: dict[str, int] = {}
    for status in quality.values():
        key = str(status)
        quality_counts[key] = quality_counts.get(key, 0) + 1
    populated_field_count = len(
        [
            field
            for field, value in values.items()
            if value is not None and field not in {"raw_usage", "raw_stats"}
        ]
    )
    summary = {
        "schema_version": NORMALIZED_TELEMETRY_SCHEMA_VERSION,
        "status": "review",
        "contract": payload.get("contract"),
        "native_adapter": payload.get("native_adapter"),
        "stats_profile": payload.get("stats_profile"),
        "populated_field_count": populated_field_count,
        "missing_field_count": len(payload.get("missing") if isinstance(payload.get("missing"), list) else []),
        "publication_grade_field_count": _review_non_negative_int(comparison.get("publication_grade_field_count")),
        "advisory_field_count": _review_non_negative_int(comparison.get("advisory_field_count")),
        "raw_provenance_field_count": _review_non_negative_int(comparison.get("raw_provenance_field_count")),
        "comparison_guidance": comparison.get("guidance"),
        "quality_counts": quality_counts,
        "stats_requires_labeling": bool(stats.get("requires_labeling")),
        "stats_guidance": stats.get("guidance"),
        "stats_publication_grade_fields": _review_summary_string_list(stats.get("publication_grade_fields")),
        "stats_advisory_fields": _review_summary_string_list(stats.get("advisory_fields")),
        "missing_stats_fields": _review_summary_string_list(stats.get("missing_stats_fields")),
    }
    return {key: value for key, value in summary.items() if value is not None}


def _matrix_pressure_json_review_summary(payload: dict[str, Any]) -> dict[str, Any] | None:
    schema = payload.get("schema_version") or payload.get("schema")
    if schema != MATRIX_PRESSURE_SCHEMA_VERSION:
        return None
    summary = _matrix_pressure_review_summary(payload)
    summary["archive_path"] = str(payload.get("matrix") or "matrix-pressure.json")
    summary["status"] = "review"
    return summary


def _matrix_saturation_json_review_summary(payload: dict[str, Any]) -> dict[str, Any] | None:
    schema = payload.get("schema_version") or payload.get("schema")
    if schema != MATRIX_SATURATION_SCHEMA_VERSION:
        return None
    summary = _matrix_saturation_review_summary(payload)
    summary["archive_path"] = str((payload.get("matrix") or {}).get("name") if isinstance(payload.get("matrix"), dict) else "matrix-saturation.json")
    summary["status"] = "pass" if payload.get("ok") is True else ("fail" if payload.get("ok") is False else "review")
    return summary


def _matrix_saturation_review_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    matrix = payload.get("matrix") if isinstance(payload.get("matrix"), dict) else {}
    evidence = payload.get("concurrency_evidence") if isinstance(payload.get("concurrency_evidence"), dict) else {}
    return {
        "schema_version": MATRIX_SATURATION_SCHEMA_VERSION,
        "matrix": matrix.get("name"),
        "ok": payload.get("ok"),
        "entry_count": _review_non_negative_int(summary.get("entry_count")),
        "group_count": _review_non_negative_int(summary.get("group_count")),
        "result_artifacts_loaded": _review_non_negative_int(summary.get("result_artifacts_loaded")),
        "result_artifacts_missing": _review_non_negative_int(summary.get("result_artifacts_missing")),
        "max_concurrency": _review_non_negative_int(evidence.get("max_concurrency") or summary.get("max_concurrency")),
        "multi_level_group_count": _review_non_negative_int(evidence.get("multi_level_group_count")),
        "concurrency_levels": _review_int_list(evidence.get("concurrency_levels")),
        "max_avg_queue_ms": _review_number_or_none(evidence.get("max_avg_queue_ms")),
        "max_avg_rate_limit_wait_ms": _review_number_or_none(evidence.get("max_avg_rate_limit_wait_ms")),
        "queue_wait_finding_count": _review_non_negative_int(evidence.get("queue_wait_finding_count")),
        "rate_limit_wait_finding_count": _review_non_negative_int(evidence.get("rate_limit_wait_finding_count")),
        "guidance": evidence.get("guidance"),
        "highest_queue_wait_entries": _compact_concurrency_entries(evidence.get("highest_queue_wait_entries")),
        "highest_rate_limit_wait_entries": _compact_concurrency_entries(evidence.get("highest_rate_limit_wait_entries")),
    }


def _matrix_scorecard_json_review_summary(payload: dict[str, Any]) -> dict[str, Any] | None:
    schema = payload.get("schema_version") or payload.get("schema") or payload.get("report_type")
    if schema != MATRIX_SCORECARD_SCHEMA_VERSION:
        return None
    return _matrix_scorecard_review_summary(payload)


def _selftest_json_review_summary(payload: dict[str, Any]) -> dict[str, Any] | None:
    schema = payload.get("schema_version") or payload.get("schema")
    if schema != SELFTEST_REPORT_SCHEMA_VERSION:
        return None
    return _selftest_review_summary(payload)


def _review_artifact_basename(value: Any, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return Path(value).name
    return default


def _publication_brief_json_review_summary(payload: dict[str, Any]) -> dict[str, Any] | None:
    schema = payload.get("schema_version") or payload.get("schema")
    if schema != PUBLICATION_BRIEF_SCHEMA_VERSION:
        return None
    return _publication_brief_review_summary(payload)


def _publication_brief_review_summary(payload: dict[str, Any]) -> dict[str, Any]:
    claim_readiness = payload.get("claim_readiness") if isinstance(payload.get("claim_readiness"), dict) else {}
    security = payload.get("security") if isinstance(payload.get("security"), dict) else {}
    proof_points = payload.get("proof_points") if isinstance(payload.get("proof_points"), list) else []
    disclosures = payload.get("disclosures") if isinstance(payload.get("disclosures"), list) else []
    matrix_scorecards = payload.get("matrix_scorecards") if isinstance(payload.get("matrix_scorecards"), list) else []
    ready = payload.get("ready")
    status = "informational"
    if ready is True:
        status = "pass"
    elif ready is False:
        status = "review"
    if security.get("contains_secrets") is True or security.get("contains_raw_provider_payloads") is True:
        status = "fail"
    artifact_name = _review_artifact_basename(payload.get("name"), "publication-brief.json")
    return {
        "schema_version": PUBLICATION_BRIEF_SCHEMA_VERSION,
        "archive_path": artifact_name,
        "status": status,
        "name": artifact_name,
        "ready": ready if isinstance(ready, bool) else None,
        "source_artifact_count": _review_non_negative_int(security.get("source_artifact_count")),
        "proof_point_count": len(proof_points),
        "disclosure_count": len(disclosures),
        "matrix_scorecard_count": len(matrix_scorecards),
        "engine_targets": _compact_engine_targets(payload.get("engine_targets")),
        "architecture_summary": _compact_scorecard_group_summary(
            payload.get("architecture_summary"),
            key="model_architecture",
        ),
        "quantization_summary": _compact_scorecard_group_summary(
            payload.get("quantization_summary"),
            key="quantization",
        ),
        **(
            {"protocol_repair_summary": _compact_protocol_repair_summary(payload.get("protocol_repair_summary"))}
            if isinstance(payload.get("protocol_repair_summary"), dict)
            else {}
        ),
        "claim_checks": _review_non_negative_int(claim_readiness.get("checks") or payload.get("claim_checks")),
        "claim_blockers": _review_non_negative_int(claim_readiness.get("blockers") or payload.get("claim_blockers")),
        "claim_warnings": _review_non_negative_int(claim_readiness.get("warnings") or payload.get("claim_warnings")),
        "contains_raw_provider_payloads": bool(security.get("contains_raw_provider_payloads")),
        "contains_secrets": bool(security.get("contains_secrets")),
    }


def _protocol_repair_posture_json_review_summary(payload: dict[str, Any]) -> dict[str, Any] | None:
    schema = payload.get("schema_version") or payload.get("schema")
    if schema != PROTOCOL_REPAIR_POSTURE_SCHEMA_VERSION:
        return None
    scorecard = payload.get("scorecard_summary") if isinstance(payload.get("scorecard_summary"), dict) else {}
    gate = payload.get("matrix_gate_summary") if isinstance(payload.get("matrix_gate_summary"), dict) else {}
    security = payload.get("security") if isinstance(payload.get("security"), dict) else {}
    artifact_name = _review_artifact_basename(payload.get("name"), "protocol-repair.json")
    return {
        "schema_version": PROTOCOL_REPAIR_POSTURE_SCHEMA_VERSION,
        "archive_path": artifact_name,
        "status": payload.get("status"),
        "name": artifact_name,
        "ready": payload.get("ready") if isinstance(payload.get("ready"), bool) else None,
        "scorecard_source_count": _review_non_negative_int(scorecard.get("source_count")),
        "scorecard_invalid_tool_call_count": _review_non_negative_int(scorecard.get("invalid_tool_call_count")),
        "scorecard_tool_parser_repair_cases": _review_non_negative_int(scorecard.get("tool_parser_repair_cases")),
        "scorecard_tool_parser_repairs_valid": _review_non_negative_int(scorecard.get("tool_parser_repairs_valid")),
        "matrix_gate_source_count": _review_non_negative_int(gate.get("source_count")),
        "matrix_gate_invalid_tool_call_count": _review_non_negative_int(gate.get("invalid_tool_call_count")),
        "matrix_gate_tool_parser_repair_cases": _review_non_negative_int(gate.get("tool_parser_repair_cases")),
        "matrix_gate_tool_parser_repairs_valid": _review_non_negative_int(gate.get("tool_parser_repairs_valid")),
        "matrix_gate_tool_parser_repair_artifacts_missing": _review_non_negative_int(
            gate.get("tool_parser_repair_artifacts_missing")
        ),
        "disclosure_count": len(payload.get("disclosures") if isinstance(payload.get("disclosures"), list) else []),
        "recommendation_count": len(payload.get("recommendations") if isinstance(payload.get("recommendations"), list) else []),
        "contains_raw_provider_payloads": bool(security.get("contains_raw_provider_payloads")),
        "contains_secrets": bool(security.get("contains_secrets")),
    }


def _workflow_readiness_json_review_summary(payload: dict[str, Any]) -> dict[str, Any] | None:
    schema = payload.get("schema_version") or payload.get("schema")
    if schema != WORKFLOW_READINESS_SCHEMA_VERSION:
        return None
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    security = payload.get("security") if isinstance(payload.get("security"), dict) else {}
    artifact_name = _review_artifact_basename(payload.get("name"), "workflow-readiness.json")
    return {
        "schema_version": WORKFLOW_READINESS_SCHEMA_VERSION,
        "archive_path": artifact_name,
        "status": payload.get("status"),
        "name": artifact_name,
        "ready": payload.get("ready") if isinstance(payload.get("ready"), bool) else None,
        "source_count": _review_non_negative_int(summary.get("source_count")),
        "case_count": _review_non_negative_int(summary.get("case_count")),
        "required_surface_count": _review_non_negative_int(summary.get("required_surface_count")),
        "covered_required_surface_count": _review_non_negative_int(summary.get("covered_required_surface_count")),
        "gap_count": _review_non_negative_int(summary.get("gap_count")),
        "max_concurrency": _review_non_negative_int(summary.get("max_concurrency")),
        "concurrency_levels": _review_int_list(summary.get("concurrency_levels")),
        "required_surfaces": _review_summary_string_list(payload.get("required_surfaces")),
        "contains_raw_provider_payloads": bool(security.get("contains_raw_provider_payloads")),
        "contains_secrets": bool(security.get("contains_secrets")),
        "contacts_providers": bool(security.get("contacts_providers")),
    }


def _security_posture_json_review_summary(payload: dict[str, Any]) -> dict[str, Any] | None:
    schema = payload.get("schema_version") or payload.get("schema")
    if schema != SECURITY_POSTURE_SCHEMA_VERSION:
        return None
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    security = payload.get("security") if isinstance(payload.get("security"), dict) else {}
    secret_backend = (
        payload.get("secret_backend_posture") if isinstance(payload.get("secret_backend_posture"), dict) else {}
    )
    artifact_name = _review_artifact_basename(payload.get("name"), "security-posture.json")
    return {
        "schema_version": SECURITY_POSTURE_SCHEMA_VERSION,
        "archive_path": artifact_name,
        "status": payload.get("status"),
        "name": artifact_name,
        "ready": payload.get("ready") if isinstance(payload.get("ready"), bool) else None,
        "blockers": _review_non_negative_int(summary.get("blockers")),
        "warnings": _review_non_negative_int(summary.get("warnings")),
        "provider_audit_count": _review_non_negative_int(summary.get("provider_audit_count")),
        "redaction_scan_count": _review_non_negative_int(summary.get("redaction_scan_count")),
        "review_artifact_count": _review_non_negative_int(summary.get("review_artifact_count")),
        "redaction_finding_count": _review_non_negative_int(summary.get("redaction_finding_count")),
        "unsafe_review_artifact_count": _review_non_negative_int(summary.get("unsafe_review_artifact_count")),
        "keyring_optional": bool(secret_backend.get("keyring_optional")),
        "keyring_dependency_available": bool(secret_backend.get("keyring_dependency_available")),
        "contains_raw_provider_payloads": bool(security.get("contains_raw_provider_payloads")),
        "contains_secrets": bool(security.get("contains_secrets")),
        "reads_keyring_values": bool(security.get("reads_keyring_values")),
        "resolves_secret_references": bool(security.get("resolves_secret_references")),
        "contacts_providers": bool(security.get("contacts_providers")),
    }


def _compact_protocol_repair_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "status": value.get("status"),
        "source_scorecard_count": _review_non_negative_int(value.get("source_scorecard_count")),
        "invalid_tool_call_count": _review_non_negative_int(value.get("invalid_tool_call_count")),
        "tool_parser_repair_cases": _review_non_negative_int(value.get("tool_parser_repair_cases")),
        "tool_parser_repairs_valid": _review_non_negative_int(value.get("tool_parser_repairs_valid")),
        "tool_parser_repair_valid_rate_percent": _review_number_or_none(
            value.get("tool_parser_repair_valid_rate_percent")
        ),
        "matrix_gate_invalid_tool_call_count": _review_non_negative_int(
            value.get("matrix_gate_invalid_tool_call_count")
        ),
        "matrix_gate_tool_parser_repair_cases": _review_non_negative_int(
            value.get("matrix_gate_tool_parser_repair_cases")
        ),
        "matrix_gate_tool_parser_repairs_valid": _review_non_negative_int(
            value.get("matrix_gate_tool_parser_repairs_valid")
        ),
        "matrix_gate_tool_parser_repair_valid_rate_percent": _review_number_or_none(
            value.get("matrix_gate_tool_parser_repair_valid_rate_percent")
        ),
        "matrix_gate_tool_parser_repair_artifacts_missing": _review_non_negative_int(
            value.get("matrix_gate_tool_parser_repair_artifacts_missing")
        ),
    }


def _sdlc_validation_manifest_json_review_summary(payload: dict[str, Any]) -> dict[str, Any] | None:
    schema = payload.get("schema_version") or payload.get("schema")
    if schema != SDLC_VALIDATION_MANIFEST_SCHEMA_VERSION:
        return None
    return _sdlc_validation_manifest_review_summary(payload)


def _sdlc_validation_manifest_review_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    gui = payload.get("gui") if isinstance(payload.get("gui"), dict) else {}
    release_evidence = payload.get("release_evidence") if isinstance(payload.get("release_evidence"), dict) else {}
    security = payload.get("security") if isinstance(payload.get("security"), dict) else {}
    stable_selectors = gui.get("stable_selectors") if isinstance(gui.get("stable_selectors"), list) else []
    api_surfaces = gui.get("api_surfaces") if isinstance(gui.get("api_surfaces"), list) else []
    expected_artifacts = (
        release_evidence.get("expected_artifacts")
        if isinstance(release_evidence.get("expected_artifacts"), list)
        else []
    )
    status = "review"
    if security.get("contains_secrets") is True or security.get("contains_raw_provider_payloads") is True:
        status = "fail"
    artifact_name = _review_artifact_basename(payload.get("name"), "sdlc-validation-manifest.json")
    return {
        "schema_version": SDLC_VALIDATION_MANIFEST_SCHEMA_VERSION,
        "archive_path": artifact_name,
        "status": status,
        "name": artifact_name,
        "tier_count": _review_non_negative_int(summary.get("tier_count") or payload.get("tier_count")),
        "required_gate_count": _review_non_negative_int(summary.get("required_gate_count") or payload.get("required_gate_count")),
        "blocking_gate_count": _review_non_negative_int(summary.get("blocking_gate_count") or payload.get("blocking_gate_count")),
        "chrome_flow_count": _review_non_negative_int(summary.get("chrome_flow_count") or payload.get("chrome_flow_count")),
        "chrome_validation_step_count": _review_non_negative_int(
            summary.get("chrome_validation_step_count") or payload.get("chrome_validation_step_count")
        ),
        "chrome_tool": gui.get("chrome_tool") or payload.get("chrome_tool"),
        "stable_selector_count": len(stable_selectors) or _review_non_negative_int(payload.get("stable_selector_count")),
        "api_surface_count": len(api_surfaces) or _review_non_negative_int(payload.get("api_surface_count")),
        "expected_artifact_count": len(expected_artifacts) or _review_non_negative_int(payload.get("expected_artifact_count")),
        "runs_tests": bool(security.get("runs_tests") or payload.get("runs_tests")),
        "contacts_providers": bool(security.get("contacts_providers") or payload.get("contacts_providers")),
        "contains_raw_provider_payloads": bool(
            security.get("contains_raw_provider_payloads") or payload.get("contains_raw_provider_payloads")
        ),
        "contains_secrets": bool(security.get("contains_secrets") or payload.get("contains_secrets")),
    }


def _benchmark_readiness_json_review_summary(payload: dict[str, Any]) -> dict[str, Any] | None:
    schema = payload.get("schema_version") or payload.get("schema")
    if schema != READINESS_SCHEMA_VERSION:
        return None
    return _benchmark_readiness_review_summary(payload)


def _provider_audit_json_review_summary(payload: dict[str, Any]) -> dict[str, Any] | None:
    schema = payload.get("schema_version") or payload.get("schema")
    if schema != PROVIDER_AUDIT_SCHEMA_VERSION:
        return None
    return _provider_audit_review_summary(payload)


def _implementation_status_json_review_summary(payload: dict[str, Any]) -> dict[str, Any] | None:
    schema = payload.get("schema_version") or payload.get("schema")
    if schema != IMPLEMENTATION_STATUS_SCHEMA_VERSION:
        return None
    return _implementation_status_review_summary(payload)


def _campaign_preflight_benchmark_readiness_json_review_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    schema = payload.get("schema_version") or payload.get("schema")
    if schema != CAMPAIGN_PREFLIGHT_BENCHMARK_READINESS_INDEX_SCHEMA_VERSION:
        return []
    reports = payload.get("reports")
    if not isinstance(reports, list):
        return []
    summaries = []
    for report in reports[:20]:
        if not isinstance(report, dict):
            continue
        summary = _benchmark_readiness_review_summary(report)
        if report.get("source_path") and "archive_path" not in summary:
            summary["archive_path"] = str(report["source_path"])
        summaries.append(summary)
    return summaries


def _benchmark_readiness_review_summary(payload: dict[str, Any]) -> dict[str, Any]:
    report_summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else payload
    status = "pass" if payload.get("ready") is True else ("review" if payload.get("ready") is False else "informational")
    summary = {
        "schema_version": READINESS_SCHEMA_VERSION,
        "archive_path": str(payload.get("provider") or "benchmark-readiness.json"),
        "status": status,
        "provider": payload.get("provider"),
        "suite": payload.get("suite"),
        "model": payload.get("model"),
        "ready": payload.get("ready") if isinstance(payload.get("ready"), bool) else None,
        "strict_unknown": payload.get("strict_unknown") if isinstance(payload.get("strict_unknown"), bool) else None,
        "policy_ok": report_summary.get("policy_ok") if isinstance(report_summary.get("policy_ok"), bool) else None,
        "suite_compatible": report_summary.get("suite_compatible") if isinstance(report_summary.get("suite_compatible"), bool) else None,
        "contract_checks_planned": _review_non_negative_int(report_summary.get("contract_checks_planned")),
        "contract_capabilities_directly_checked": _review_non_negative_int(
            report_summary.get("contract_capabilities_directly_checked")
        ),
        "contract_capabilities_proxy_checked": _review_non_negative_int(
            report_summary.get("contract_capabilities_proxy_checked")
        ),
        "contract_capabilities_not_covered": _review_non_negative_int(
            report_summary.get("contract_capabilities_not_covered")
        ),
        "metric_coverage_score": report_summary.get("metric_coverage_score"),
        "provider_auth_writable_backends": _review_non_negative_int(report_summary.get("provider_auth_writable_backends")),
        "provider_auth_plaintext_fallbacks": _review_non_negative_int(report_summary.get("provider_auth_plaintext_fallbacks")),
        "provider_auth_prewrite_policy_guards_recommended": _review_non_negative_int(
            report_summary.get("provider_auth_prewrite_policy_guards_recommended")
        ),
        "blocking_findings": _review_non_negative_int(report_summary.get("blocking_findings")),
        "warnings": _review_non_negative_int(report_summary.get("warnings")),
        "provider_auth_posture": _compact_provider_auth_posture(payload.get("provider_auth_posture")),
    }
    return {key: value for key, value in summary.items() if value is not None}


def _provider_audit_review_summary(payload: dict[str, Any]) -> dict[str, Any]:
    embedded = payload.get("provider_audit_summaries")
    if isinstance(embedded, list) and embedded and isinstance(embedded[0], dict):
        return {str(key): value for key, value in embedded[0].items()}
    providers = payload.get("providers") if isinstance(payload.get("providers"), list) else []
    finding_codes = sorted(
        {
            str(finding.get("code"))
            for provider in providers
            if isinstance(provider, dict)
            for finding in (provider.get("findings") if isinstance(provider.get("findings"), list) else [])
            if isinstance(finding, dict) and finding.get("code")
        }
    )
    policy_controls = payload.get("policy_controls") if isinstance(payload.get("policy_controls"), dict) else {}
    errors = _review_non_negative_int(payload.get("errors"))
    warnings = _review_non_negative_int(payload.get("warnings"))
    secret_backend = _compact_secret_backend_posture(payload.get("secret_backend_posture"))
    status = "fail" if errors else ("review" if warnings else "pass")
    return {
        "schema_version": PROVIDER_AUDIT_SCHEMA_VERSION,
        "archive_path": "provider-audit.json",
        "status": status,
        "total_providers": _review_non_negative_int(payload.get("total_providers")),
        "remote_providers": _review_non_negative_int(payload.get("remote_providers")),
        "policy_ok_count": _review_non_negative_int(payload.get("policy_ok")),
        "error_count": errors,
        "warning_count": warnings,
        "plaintext_dotenv_provider_count": sum(
            1 for provider in providers if isinstance(provider, dict) and provider.get("api_key_ref_plaintext_fallback")
        ),
        "writable_secret_backend_count": sum(
            1 for provider in providers if isinstance(provider, dict) and provider.get("api_key_ref_writable_backend")
        ),
        "prewrite_policy_guard_recommended_count": sum(
            1 for provider in providers if isinstance(provider, dict) and provider.get("prewrite_policy_guard_recommended")
        ),
        "keyring_required_provider_count": sum(
            1 for provider in providers if isinstance(provider, dict) and provider.get("keyring_backend_required")
        ),
        "keyring_dependency_available": secret_backend.get("keyring_dependency_available"),
        "secret_backend_posture": secret_backend,
        "provider_auth_posture": _compact_provider_auth_posture(
            [
                {
                    "provider": provider.get("name"),
                    "api_key_ref_kind": provider.get("api_key_ref_kind"),
                    "api_key_ref_configured": provider.get("api_key_ref_configured"),
                    "api_key_ref_writable_backend": provider.get("api_key_ref_writable_backend"),
                    "api_key_ref_plaintext_fallback": provider.get("api_key_ref_plaintext_fallback"),
                    "prewrite_policy_guard_recommended": provider.get("prewrite_policy_guard_recommended"),
                }
                for provider in providers
                if isinstance(provider, dict)
            ]
        ),
        "finding_codes": finding_codes[:12],
        "policy_controls": {str(key): bool(value) for key, value in policy_controls.items()},
        "shareable_summary_only": True,
    }


def _compact_provider_auth_posture(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    posture = []
    for item in value:
        if not isinstance(item, dict):
            continue
        posture.append(
            {
                "provider": item.get("provider"),
                "api_key_ref_kind": item.get("api_key_ref_kind"),
                "api_key_ref_configured": bool(item.get("api_key_ref_configured")),
                "api_key_ref_writable_backend": bool(item.get("api_key_ref_writable_backend")),
                "api_key_ref_plaintext_fallback": bool(item.get("api_key_ref_plaintext_fallback")),
                "prewrite_policy_guard_recommended": bool(item.get("prewrite_policy_guard_recommended")),
            }
        )
    return posture[:12]


def _compact_secret_backend_posture(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    supported = value.get("supported_secret_ref_kinds") if isinstance(value.get("supported_secret_ref_kinds"), list) else []
    recommended = (
        value.get("recommended_enterprise_backends") if isinstance(value.get("recommended_enterprise_backends"), list) else []
    )
    return {
        "env_reference_portable": bool(value.get("env_reference_portable")),
        "keyring_optional": bool(value.get("keyring_optional")),
        "keyring_dependency_available": bool(value.get("keyring_dependency_available")),
        "dotenv_plaintext_fallback_supported": bool(value.get("dotenv_plaintext_fallback_supported")),
        "dotenv_plaintext_fallback_enterprise_default": bool(value.get("dotenv_plaintext_fallback_enterprise_default")),
        "supported_secret_ref_kinds": [str(item) for item in supported[:6]],
        "recommended_enterprise_backends": [str(item) for item in recommended[:6]],
    }


def _implementation_status_review_summary(payload: dict[str, Any]) -> dict[str, Any]:
    suite_inventory = payload.get("suite_inventory") if isinstance(payload.get("suite_inventory"), dict) else {}
    requirements = payload.get("requirements_inventory") if isinstance(payload.get("requirements_inventory"), dict) else {}
    target_engines = requirements.get("target_engines") if isinstance(requirements.get("target_engines"), dict) else {}
    provider_contracts = (
        requirements.get("provider_contracts") if isinstance(requirements.get("provider_contracts"), dict) else {}
    )
    model_targets = requirements.get("model_targets") if isinstance(requirements.get("model_targets"), dict) else {}
    agentic = requirements.get("agentic_workflows") if isinstance(requirements.get("agentic_workflows"), dict) else {}
    harness = requirements.get("harness_engineering") if isinstance(requirements.get("harness_engineering"), dict) else {}
    stats = requirements.get("stats_comparability") if isinstance(requirements.get("stats_comparability"), dict) else {}
    enterprise = (
        requirements.get("enterprise_controls") if isinstance(requirements.get("enterprise_controls"), dict) else {}
    )
    publication = (
        requirements.get("publication_governance")
        if isinstance(requirements.get("publication_governance"), dict)
        else {}
    )
    selftest = requirements.get("selftest_harness") if isinstance(requirements.get("selftest_harness"), dict) else {}
    validation = payload.get("validation") if isinstance(payload.get("validation"), dict) else {}
    implementation_status = payload.get("implementation_status") or payload.get("status")
    missing_areas = _review_non_negative_int(payload.get("missing_areas"))
    status = "pass" if missing_areas == 0 and implementation_status == "implementation-ready-for-validation" else "fail"
    return {
        "schema_version": IMPLEMENTATION_STATUS_SCHEMA_VERSION,
        "archive_path": str(payload.get("archive_path") or "implementation-status.json"),
        "status": status,
        "implementation_status": implementation_status,
        "implemented_areas": _review_non_negative_int(payload.get("implemented_areas")),
        "partial_areas": _review_non_negative_int(payload.get("partial_areas")),
        "missing_areas": missing_areas,
        "built_in_suite_count": _review_non_negative_int(
            suite_inventory.get("built_in_suite_count") or payload.get("built_in_suite_count")
        ),
        "harness_engineering_suite_present": bool(
            suite_inventory.get("harness_engineering_suite_present")
            or payload.get("harness_engineering_suite_present")
        ),
        "harness_engineering_case_count": len(
            _review_summary_string_list(
                suite_inventory.get("harness_engineering_cases") or payload.get("harness_engineering_cases")
            )
        )
        or _review_non_negative_int(payload.get("harness_engineering_case_count")),
        "target_engine_count": _review_non_negative_int(target_engines.get("count") or payload.get("target_engine_count")),
        "provider_preset_count": _review_non_negative_int(
            provider_contracts.get("preset_count") or payload.get("provider_preset_count")
        ),
        "model_target_count": _review_non_negative_int(model_targets.get("catalog_count") or payload.get("model_target_count")),
        "initial_model_targets_present": bool(
            model_targets.get("initial_targets_present") or payload.get("initial_model_targets_present")
        ),
        "agent_profile_count": _review_non_negative_int(agentic.get("profile_count") or payload.get("agent_profile_count")),
        "harness_profile_count": _review_non_negative_int(
            harness.get("profile_count") or payload.get("harness_profile_count")
        ),
        "stats_profile_count": _review_non_negative_int(stats.get("profile_count") or payload.get("stats_profile_count")),
        "stats_metric_provider_count": _review_non_negative_int(
            stats.get("metric_provider_count") or payload.get("stats_metric_provider_count")
        ),
        "stats_publication_requires_labels": bool(
            stats.get("publication_requires_labels_for_non_native_stats")
            or payload.get("stats_publication_requires_labels")
        ),
        "keyring_optional": bool(enterprise.get("keyring_optional") or payload.get("keyring_optional")),
        "secret_backends": _review_summary_string_list(enterprise.get("secret_backends") or payload.get("secret_backends")),
        "publication_governance_consumers": len(
            _review_summary_string_list(publication.get("redaction_safe_summary_consumers"))
        )
        or _review_non_negative_int(payload.get("publication_governance_consumers")),
        "selftest_report_schema": selftest.get("report_schema") or payload.get("selftest_report_schema"),
        "chrome_codex_gate_present": bool(selftest.get("chrome_codex_gate_present") or payload.get("chrome_codex_gate_present")),
        "tests_run_by_this_command": bool(validation.get("tests_run_by_this_command") or payload.get("tests_run_by_this_command")),
        "shareable_summary_only": True,
    }


def _selftest_review_summary(payload: dict[str, Any]) -> dict[str, Any]:
    status = "pass" if payload.get("ok") is True else ("fail" if payload.get("ok") is False else "review")
    summary = {
        "schema_version": SELFTEST_REPORT_SCHEMA_VERSION,
        "archive_path": str(payload.get("run_id") or "selftest-report.json"),
        "status": status,
        "run_id": payload.get("run_id"),
        "tier": payload.get("tier"),
        "ok": payload.get("ok"),
        "exit_code": _review_non_negative_int(payload.get("exit_code")),
        "duration_ms": _review_number_or_none(payload.get("duration_ms")),
        "browser": payload.get("browser"),
        "headed": bool(payload.get("headed")),
        "marker_expression": payload.get("marker_expression"),
        "junit_xml_present": bool(payload.get("junit_xml") or payload.get("junit_xml_present")),
    }
    return {key: value for key, value in summary.items() if value is not None}


def _matrix_scorecard_review_summary(payload: dict[str, Any]) -> dict[str, Any]:
    matrix = payload.get("matrix") if isinstance(payload.get("matrix"), dict) else {}
    scorecard = payload.get("scorecard") if isinstance(payload.get("scorecard"), dict) else {}
    failure_class_summary = scorecard.get("failure_class_summary") if isinstance(scorecard, dict) else []
    tool_loop_stop_summary = scorecard.get("tool_loop_stop_summary") if isinstance(scorecard, dict) else []
    failed_runs = _review_non_negative_int(matrix.get("failed_runs"))
    failed_cases = _review_non_negative_int(scorecard.get("failed_cases"))
    status = "pass" if failed_runs == 0 and failed_cases == 0 else "review"
    return {
        "schema_version": MATRIX_SCORECARD_SCHEMA_VERSION,
        "archive_path": str(matrix.get("name") or "matrix-scorecard.json"),
        "status": status,
        "matrix": matrix.get("name"),
        "completed_runs": _review_non_negative_int(matrix.get("completed_runs")),
        "total_runs": _review_non_negative_int(matrix.get("total_runs")),
        "failed_runs": failed_runs,
        "entry_count": _review_non_negative_int(scorecard.get("entry_count")),
        "result_artifacts_loaded": _review_non_negative_int(scorecard.get("result_artifacts_loaded")),
        "total_cases": _review_non_negative_int(scorecard.get("total_cases")),
        "passed_cases": _review_non_negative_int(scorecard.get("passed_cases")),
        "failed_cases": failed_cases,
        "pass_rate_percent": _review_number_or_none(scorecard.get("pass_rate_percent")),
        "judge_rubric_cases": _review_non_negative_int(scorecard.get("judge_rubric_cases")),
        "judge_verdicts_valid": _review_non_negative_int(scorecard.get("judge_verdicts_valid")),
        "invalid_tool_call_count": _review_non_negative_int(scorecard.get("invalid_tool_call_count")),
        "tool_parser_repair_cases": _review_non_negative_int(scorecard.get("tool_parser_repair_cases")),
        "tool_parser_repairs_valid": _review_non_negative_int(scorecard.get("tool_parser_repairs_valid")),
        "tool_parser_repair_valid_rate_percent": _review_number_or_none(
            scorecard.get("tool_parser_repair_valid_rate_percent")
        ),
        "failure_class_summary": failure_class_summary if isinstance(failure_class_summary, list) else [],
        "tool_loop_stop_summary": tool_loop_stop_summary if isinstance(tool_loop_stop_summary, list) else [],
        "telemetry_quality_summary": _compact_telemetry_quality_summary(scorecard.get("telemetry_quality_summary")),
        "stats_comparability_summary": _compact_stats_comparability_summary(scorecard.get("stats_comparability_summary")),
        "concurrency_evidence": _compact_scorecard_concurrency_evidence(scorecard.get("concurrency_evidence")),
        "engine_targets": _compact_engine_targets(scorecard.get("engine_targets")),
        "architecture_summary": _compact_scorecard_group_summary(
            payload.get("architecture_summary"),
            key="model_architecture",
        ),
        "quantization_summary": _compact_scorecard_group_summary(
            payload.get("quantization_summary"),
            key="quantization",
        ),
    }


def _matrix_pressure_review_summary(payload: dict[str, Any]) -> dict[str, Any]:
    totals = payload.get("totals") if isinstance(payload.get("totals"), dict) else {}
    return {
        "schema_version": MATRIX_PRESSURE_SCHEMA_VERSION,
        "matrix": payload.get("matrix"),
        "run_count": _review_non_negative_int(payload.get("run_count")),
        "case_count": _review_non_negative_int(totals.get("case_count")),
        "scheduled_prompt_tokens": _review_non_negative_int(totals.get("scheduled_prompt_tokens")),
        "concurrent_window_prompt_tokens": _review_non_negative_int(totals.get("concurrent_window_prompt_tokens")),
        "prefill_pressure_score": _review_non_negative_int(totals.get("prefill_pressure_score")),
        "concurrency_weighted_pressure_score": _review_non_negative_int(totals.get("concurrency_weighted_pressure_score")),
        "shared_static_prefix_groups": _review_non_negative_int(totals.get("shared_static_prefix_groups")),
        "shared_static_prefix_tokens": _review_non_negative_int(totals.get("shared_static_prefix_tokens")),
        "shared_static_reuse_tokens": _review_non_negative_int(totals.get("shared_static_reuse_tokens")),
        "engines": _review_summary_string_list(payload.get("engines")),
        "models": _review_summary_string_list(payload.get("models")),
        "suites": _review_summary_string_list(payload.get("suites")),
        "concurrency_levels": _review_int_list(payload.get("concurrency_levels")),
        "highest_pressure_runs": _compact_matrix_pressure_runs(payload.get("highest_pressure_runs")),
    }


def _compact_matrix_pressure_runs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    runs = []
    for item in value:
        if not isinstance(item, dict):
            continue
        runs.append(
            {
                "index": _review_non_negative_int(item.get("index")),
                "engine": item.get("engine"),
                "model": item.get("model"),
                "suite": item.get("suite"),
                "concurrency": _review_non_negative_int(item.get("concurrency")),
                "prefill_pressure_level": item.get("prefill_pressure_level"),
                "concurrent_window_prompt_tokens": _review_non_negative_int(item.get("concurrent_window_prompt_tokens")),
                "concurrency_weighted_pressure_score": _review_non_negative_int(
                    item.get("concurrency_weighted_pressure_score")
                ),
                "shared_static_reuse_tokens": _review_non_negative_int(item.get("shared_static_reuse_tokens")),
            }
        )
    return runs[:5]


def _compact_concurrency_entries(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    entries = []
    for item in value:
        if not isinstance(item, dict):
            continue
        entries.append(
            {
                "group_id": item.get("group_id"),
                "run_id": item.get("run_id"),
                "engine": item.get("engine"),
                "provider": item.get("provider"),
                "model": item.get("model"),
                "suite": item.get("suite"),
                "concurrency": _review_non_negative_int(item.get("concurrency")),
                "rank_metric": item.get("rank_metric"),
                "rank_value": _review_number_or_none(item.get("rank_value")),
                "avg_queue_ms": _review_number_or_none(item.get("avg_queue_ms")),
                "avg_rate_limit_wait_ms": _review_number_or_none(item.get("avg_rate_limit_wait_ms")),
            }
        )
    return entries[:5]


def _compact_scorecard_concurrency_evidence(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "schema_version": value.get("schema_version"),
        "entry_count": _review_non_negative_int(value.get("entry_count")),
        "artifact_loaded_count": _review_non_negative_int(value.get("artifact_loaded_count")),
        "concurrency_levels": _review_int_list(value.get("concurrency_levels")),
        "multi_level": bool(value.get("multi_level")),
        "max_concurrency": _review_non_negative_int(value.get("max_concurrency")),
        "max_avg_queue_ms": _review_number_or_none(value.get("max_avg_queue_ms")),
        "max_avg_rate_limit_wait_ms": _review_number_or_none(value.get("max_avg_rate_limit_wait_ms")),
        "guidance": value.get("guidance"),
        "highest_queue_wait_entries": _compact_concurrency_entries(value.get("highest_queue_wait_entries")),
        "highest_rate_limit_wait_entries": _compact_concurrency_entries(value.get("highest_rate_limit_wait_entries")),
    }


def _compact_engine_targets(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    targets: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        targets.append(
            {
                "id": str(item.get("id")),
                "display_name": str(item.get("display_name")) if item.get("display_name") is not None else None,
                "primary_scoring_contract": (
                    str(item.get("primary_scoring_contract"))
                    if item.get("primary_scoring_contract") is not None
                    else None
                ),
            }
        )
    return targets[:12]


def _compact_scorecard_group_summary(value: Any, *, key: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                key: str(item.get(key) or "unknown"),
                "runs": _review_non_negative_int(item.get("runs")),
                "failed_runs": _review_non_negative_int(item.get("failed_runs")),
                "completed_runs": _review_non_negative_int(item.get("completed_runs")),
                "result_artifacts_loaded": _review_non_negative_int(item.get("result_artifacts_loaded")),
                "total_cases": _review_non_negative_int(item.get("total_cases")),
                "passed": _review_non_negative_int(item.get("passed")),
                "failed": _review_non_negative_int(item.get("failed")),
                "pass_rate_percent": _review_number_or_none(item.get("pass_rate_percent")),
                "avg_latency_ms": _review_number_or_none(item.get("avg_latency_ms")),
                "avg_decode_tokens_per_second": _review_number_or_none(item.get("avg_decode_tokens_per_second")),
                "judge_rubric_cases": _review_non_negative_int(item.get("judge_rubric_cases")),
                "judge_verdicts_valid": _review_non_negative_int(item.get("judge_verdicts_valid")),
                "invalid_tool_call_count": _review_non_negative_int(item.get("invalid_tool_call_count")),
                "tool_parser_repair_cases": _review_non_negative_int(item.get("tool_parser_repair_cases")),
                "tool_parser_repairs_valid": _review_non_negative_int(item.get("tool_parser_repairs_valid")),
                "tool_parser_repair_valid_rate_percent": _review_number_or_none(
                    item.get("tool_parser_repair_valid_rate_percent")
                ),
            }
        )
    return rows[:12]


def _compact_telemetry_quality_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "quality_counts": _review_int_map(value.get("quality_counts")),
        "guidance_counts": _review_int_map(value.get("guidance_counts")),
        "entries_with_advisory_quality": _review_non_negative_int(value.get("entries_with_advisory_quality")),
        "entries_with_unknown_quality": _review_non_negative_int(value.get("entries_with_unknown_quality")),
        "entries_with_comparison_guidance": _review_non_negative_int(value.get("entries_with_comparison_guidance")),
    }


def _compact_stats_comparability_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "schema_version": value.get("schema_version"),
        "profile_counts": _review_int_map(value.get("profile_counts")),
        "guidance_counts": _review_int_map(value.get("guidance_counts")),
        "entries_requiring_labeling": _review_non_negative_int(value.get("entries_requiring_labeling")),
    }


def _telemetry_quality_review_text(value: Any) -> str:
    if not isinstance(value, dict):
        return "none"
    counts = value.get("quality_counts")
    if not isinstance(counts, dict) or not counts:
        return "none"
    return ",".join(f"{key}={counts[key]}" for key in sorted(counts))


def _stats_comparability_review_text(value: Any) -> str:
    if not isinstance(value, dict):
        return "none"
    profiles = value.get("profile_counts")
    if not isinstance(profiles, dict) or not profiles:
        profile_text = "none"
    else:
        profile_text = ",".join(f"{key}={profiles[key]}" for key in sorted(profiles))
    return f"profiles={profile_text},label={_review_non_negative_int(value.get('entries_requiring_labeling'))}"


def _scorecard_concurrency_review_text(value: Any) -> str:
    if not isinstance(value, dict):
        return "none"
    levels = value.get("concurrency_levels")
    levels_text = ",".join(str(item) for item in levels) if isinstance(levels, list) and levels else "n/a"
    guidance = value.get("guidance") or "n/a"
    return f"levels={levels_text}, queue={value.get('max_avg_queue_ms')}, guidance={guidance}"


def _review_readiness_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "ready": bool(value.get("ready")),
        "state": str(value.get("state") or "unknown"),
        "blocking_artifact_count": _review_non_negative_int(value.get("blocking_artifact_count")),
        "review_artifact_count": _review_non_negative_int(value.get("review_artifact_count")),
        "blocking_statuses": _review_summary_string_list(value.get("blocking_statuses")),
        "review_statuses": _review_summary_string_list(value.get("review_statuses")),
    }


def _review_cleanup_evidence_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "artifact_count": _review_non_negative_int(value.get("artifact_count")),
        "manual_report_count": _review_non_negative_int(value.get("manual_report_count")),
        "retention_report_count": _review_non_negative_int(value.get("retention_report_count")),
        "planned_report_count": _review_non_negative_int(value.get("planned_report_count")),
        "executed_report_count": _review_non_negative_int(value.get("executed_report_count")),
        "audit_log_required_count": _review_non_negative_int(value.get("audit_log_required_count")),
        "contains_local_paths": bool(value.get("contains_local_paths")),
        "direct_publication_safe": bool(value.get("direct_publication_safe")),
        "shareable_summary_only": bool(value.get("shareable_summary_only")),
    }


def _review_summary_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value[:12] if item is not None]


def _review_int_list(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    return [_review_non_negative_int(item) for item in value[:12]]


def _review_number_or_none(value: Any) -> float | int | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed.is_integer():
        return int(parsed)
    return parsed


def _compact_engine_priorities(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    priorities = []
    for item in value:
        if not isinstance(item, dict):
            continue
        priorities.append(
            {
                "priority": _review_non_negative_int(item.get("priority")),
                "area": str(item.get("area") or "unknown"),
                "aligned_artifacts_or_suites": _compact_string_list(item.get("aligned_artifacts_or_suites")),
            }
        )
    return priorities[:8]


def _compact_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value[:8] if item is not None]


def _review_non_negative_int(value: Any) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


def _review_int_map(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): _review_non_negative_int(raw)
        for key, raw in value.items()
    }


def _matrix_gate_json_review_summary(payload: dict[str, Any]) -> dict[str, Any] | None:
    has_failure_classes = isinstance(payload.get("failure_class_summary"), list) and bool(payload["failure_class_summary"])
    has_tool_loop_stops = isinstance(payload.get("tool_loop_stop_summary"), list) and bool(payload["tool_loop_stop_summary"])
    try:
        failure_class_artifacts_missing = int(payload.get("failure_class_artifacts_missing") or 0)
    except (TypeError, ValueError):
        failure_class_artifacts_missing = 0
    try:
        tool_loop_artifacts_missing = int(payload.get("tool_loop_artifacts_missing") or 0)
    except (TypeError, ValueError):
        tool_loop_artifacts_missing = 0
    findings = payload.get("findings")
    has_class_findings = isinstance(findings, list) and any(
        isinstance(item, dict) and str(item.get("metric") or "").startswith("failure_class.")
        for item in findings
    )
    has_tool_loop_findings = isinstance(findings, list) and any(
        isinstance(item, dict) and str(item.get("metric") or "").startswith("tool_loop_stop_reason.")
        for item in findings
    )
    has_tool_parser_fields = any(
        key in payload
        for key in (
            "invalid_tool_call_count",
            "tool_parser_repair_cases",
            "tool_parser_repairs_valid",
            "tool_parser_repair_valid_rate_percent",
            "tool_parser_repair_artifacts_missing",
        )
    )
    has_tool_parser_findings = isinstance(findings, list) and any(
        isinstance(item, dict)
        and str(item.get("metric") or "")
        in {
            "invalid_tool_calls",
            "tool_parser_repair_valid_rate",
            "tool_parser_repair_result_artifacts_missing",
        }
        for item in findings
    )
    if (
        not has_failure_classes
        and not has_tool_loop_stops
        and not has_class_findings
        and not has_tool_loop_findings
        and not has_tool_parser_fields
        and not has_tool_parser_findings
        and failure_class_artifacts_missing <= 0
        and tool_loop_artifacts_missing <= 0
    ):
        return None
    summary: dict[str, Any] = {
        "archive_path": str(payload.get("matrix_name") or "matrix-gate.json"),
        "schema_version": str(payload.get("schema_version") or payload.get("schema") or MATRIX_GATE_SCHEMA_VERSION),
        "status": "pass" if payload.get("ok") is True else "fail" if payload.get("ok") is False else "review",
    }
    for key in (
        "matrix_name",
        "pass_rate_percent",
        "failure_class_summary",
        "failure_class_artifacts_missing",
        "tool_loop_stop_summary",
        "tool_loop_artifacts_missing",
        "invalid_tool_call_count",
        "tool_parser_repair_cases",
        "tool_parser_repairs_valid",
        "tool_parser_repair_valid_rate_percent",
        "tool_parser_repair_artifacts_missing",
    ):
        if key in payload:
            summary[key] = payload[key]
    failure_class_findings = _json_failure_class_findings(findings)
    if failure_class_findings:
        summary["failure_class_gate_count"] = len(failure_class_findings)
        summary["failure_class_gate_findings"] = failure_class_findings[:12]
    tool_loop_stop_findings = _json_tool_loop_stop_findings(findings)
    if tool_loop_stop_findings:
        summary["tool_loop_stop_gate_count"] = len(tool_loop_stop_findings)
        summary["tool_loop_stop_gate_findings"] = tool_loop_stop_findings[:12]
    tool_parser_findings = _json_tool_parser_repair_findings(findings)
    if tool_parser_findings:
        summary["tool_parser_repair_gate_count"] = len(tool_parser_findings)
        summary["tool_parser_repair_gate_findings"] = tool_parser_findings[:12]
    return summary


def _looks_like_matrix_gate_payload(payload: dict[str, Any]) -> bool:
    if payload.get("schema_version") == MATRIX_GATE_SCHEMA_VERSION or payload.get("schema") == MATRIX_GATE_SCHEMA_VERSION:
        return True
    return "matrix_name" in payload and "findings" in payload and (
        "thresholds" in payload
        or "failure_class_summary" in payload
        or "tool_loop_stop_summary" in payload
        or "pass_rate_percent" in payload
    )


def _json_failure_class_findings(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    findings = []
    for item in value:
        if not isinstance(item, dict):
            continue
        metric = str(item.get("metric") or "")
        if metric.startswith("failure_class."):
            findings.append(
                {
                    "metric": metric,
                    "failure_class": metric.split(".", 1)[1] or "unclassified",
                    "actual": item.get("actual"),
                    "threshold": item.get("threshold"),
                }
            )
    return findings


def _json_tool_loop_stop_findings(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    findings = []
    for item in value:
        if not isinstance(item, dict):
            continue
        metric = str(item.get("metric") or "")
        if metric.startswith("tool_loop_stop_reason."):
            findings.append(
                {
                    "metric": metric,
                    "stop_reason": metric.split(".", 1)[1] or "unknown",
                    "actual": item.get("actual"),
                    "threshold": item.get("threshold"),
                }
            )
    return findings


def _json_tool_parser_repair_findings(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    findings = []
    for item in value:
        if not isinstance(item, dict):
            continue
        metric = str(item.get("metric") or "")
        if metric in {
            "invalid_tool_calls",
            "tool_parser_repair_valid_rate",
            "tool_parser_repair_result_artifacts_missing",
        }:
            findings.append(
                {
                    "metric": metric,
                    "actual": item.get("actual"),
                    "threshold": item.get("threshold"),
                }
            )
    return findings


def _is_blocked_review_artifact(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    return "raw" in parts or path.name in REVIEW_ARTIFACT_BLOCKED_NAMES


def _safe_review_artifact_path(root: Path, artifact_path: str) -> Path:
    relative = Path(artifact_path)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ConfigError("invalid review artifact path")
    if not relative.parts or relative.parts[0] not in REVIEW_ARTIFACT_DIRS:
        raise ConfigError("review artifact path is outside known review directories")
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ConfigError("review artifact path escapes project root") from exc
    if not path.exists() or not path.is_file():
        raise ConfigError(f"unknown review artifact: {artifact_path}")
    if _is_blocked_review_artifact(path):
        raise ConfigError("blocked review artifact path")
    if path.suffix.lower() not in REVIEW_ARTIFACT_SUFFIXES:
        raise ConfigError("unsupported review artifact type")
    return path


def _query_value(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key) or []
    for value in values:
        stripped = value.strip()
        if stripped:
            return stripped
    return None


def _query_csv(query: dict[str, list[str]], key: str) -> list[str] | None:
    value = _query_value(query, key)
    if value is None:
        return None
    return _split_csv(value)


def _dashboard_auth_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _run_row(run: dict[str, Any]) -> str:
    status_class = "pass" if run["ok"] else "fail"
    status_label = "pass" if run["ok"] else "fail"
    return f"""<tr data-testid="run-row" data-run-id="{html.escape(run["run_id"])}">
  <td>
    <div class="run-id">{html.escape(run["run_id"])}</div>
    <div class="meta">{html.escape(run["created_at"])}</div>
  </td>
  <td><span class="status {status_class}">{status_label}</span></td>
  <td>{html.escape(run["provider"])}<div class="meta">{html.escape(_provider_brief(run["provider_metadata"]))}</div></td>
  <td>{html.escape(_adapter_brief(run["provider_metadata"]))}</td>
  <td>{html.escape(run["model"])}<div class="meta">{html.escape(_model_metadata_brief(run["model_metadata"]))}</div></td>
  <td>{html.escape(run["suite"])}</td>
  <td>{html.escape(_suite_provenance_brief(run["suite_provenance"]))}</td>
  <td><span class="meta">{html.escape(_hash_brief(run.get("suite_sha256")))}</span></td>
  <td>{run["passed"]}/{run["total_cases"]}</td>
  <td>{_display_metric(run["requests_per_second"])}</td>
  <td>{_display_metric(run["total_cost_usd"])}</td>
  <td>{_display_metric(run["avg_queue_ms"])}</td>
  <td>{_display_metric(run["avg_rate_limit_wait_ms"])}</td>
  <td>{_display_metric(run["avg_latency_ms"])}</td>
  <td>{_display_metric(run["avg_ttft_ms"])}</td>
  <td>{_display_metric(run["avg_decode_tokens_per_second"])}</td>
  <td>{_artifact_links(run)}</td>
</tr>"""


def _launch_panel() -> str:
    try:
        providers = dashboard_providers()
        provider_error = ""
    except ConfigError as exc:
        providers = []
        provider_error = f"<p class=\"meta\">Provider config error: {html.escape(str(exc))}</p>"
    provider_options = _provider_options(providers)
    suite_options = _suite_options(dashboard_suites())
    return f"""
    <section class="panel launch" data-testid="launch-panel">
      <h2>Launch a local run</h2>
      <p class="meta">Preview launch safety first with <code>POST /api/run-plan</code>; it enforces policy without resolving secrets, contacting providers, or writing run artifacts. Launch uses the same policy gate, then dispatches provider requests and writes run artifacts.</p>
      <form method="post" action="/launch" data-testid="launch-form">
        <label>Provider
          <select name="provider" required data-testid="provider-select">
            {provider_options}
          </select>
        </label>
        <label>Suite
          <select name="suite" required data-testid="suite-select">
            {suite_options}
          </select>
        </label>
        <label>Model
          <input name="model" placeholder="provider default or model id" data-testid="model-input">
        </label>
        <label>Concurrency
          <input name="concurrency" type="number" min="1" value="1" data-testid="concurrency-input">
        </label>
        <label>Raw traces
          <select name="raw_traces" data-testid="raw-traces-select">
            <option value="redacted">redacted</option>
            <option value="off">off</option>
          </select>
        </label>
        <label class="check">
          <input name="allow_remote" type="checkbox" value="true" data-testid="allow-remote-input">
          allow remote provider
        </label>
        <label>Capability gate
          <select name="capability_preflight" data-testid="capability-preflight-select">
            <option value="true">preflight required</option>
            <option value="false">skip preflight</option>
          </select>
        </label>
        <label class="check">
          <input name="strict_unknown_capabilities" type="checkbox" value="true" data-testid="strict-unknown-capabilities-input">
          strict unknown capabilities
        </label>
        <button type="submit" formaction="/run-plan" data-testid="run-plan-submit">Preview plan</button>
        <button type="submit" data-testid="launch-submit">Launch</button>
      </form>
      {provider_error}
      <p class="meta">Remote providers are blocked by default unless explicitly allowed. Secrets are resolved from provider references, not browser input.</p>
    </section>
    """


def _provider_setup_panel() -> str:
    return """
    <section class="panel launch" data-testid="provider-setup-panel">
      <h2>Provider setup</h2>
      <form method="post" action="/providers" data-testid="provider-setup-form">
        <label>Name
          <input name="name" required placeholder="remote-openai" data-testid="provider-setup-name-input">
        </label>
        <label>Contract
          <select name="contract" required data-testid="provider-setup-contract-select">
            <option value="openai">OpenAI Chat</option>
            <option value="openai-responses">OpenAI Responses</option>
            <option value="anthropic">Anthropic Messages</option>
            <option value="native">native</option>
          </select>
        </label>
        <label>Base URL
          <input name="base_url" required placeholder="https://api.openai.com/v1" data-testid="provider-setup-base-url-input">
        </label>
        <label>Default model
          <input name="default_model" placeholder="model id" data-testid="provider-setup-model-input">
        </label>
        <label>API-key env
          <input name="api_key_env" placeholder="OPENAI_API_KEY" data-testid="provider-setup-api-key-env-input">
        </label>
        <label>TLS verify
          <select name="tls_verify" data-testid="provider-setup-tls-select">
            <option value="true">verify TLS</option>
            <option value="false">insecure TLS</option>
          </select>
        </label>
        <label class="check">
          <input name="remote" type="checkbox" value="true" data-testid="provider-setup-remote-input">
          remote provider
        </label>
        <button type="submit" data-testid="provider-setup-submit">Save provider</button>
      </form>
      <p class="meta">Provider setup stores endpoint metadata and optional secret references only. Enter raw API keys in the auth setup panel only when using the optional keyring backend or explicit plaintext dotenv fallback.</p>
    </section>
    """


def _provider_auth_panel() -> str:
    try:
        providers = dashboard_providers()
        provider_error = ""
    except ConfigError as exc:
        providers = []
        provider_error = f'<p class="meta">Provider config error: {html.escape(str(exc))}</p>'
    provider_options = _provider_options(providers)
    return f"""
    <section class="panel launch" data-testid="provider-auth-panel">
      <h2>Provider auth setup</h2>
      <form method="post" action="/providers/auth" data-testid="provider-auth-form">
        <label>Provider
          <select name="provider" required data-testid="provider-auth-select">
            {provider_options}
          </select>
        </label>
        <label>Secret backend
          <select name="method" required data-testid="provider-auth-method-select">
            <option value="env">env reference</option>
            <option value="keyring">keyring / Keychain</option>
            <option value="dotenv">dotenv plaintext fallback</option>
          </select>
        </label>
        <label>Env var / dotenv var
          <input name="env_var" placeholder="OPENAI_API_KEY" data-testid="provider-auth-env-input">
        </label>
        <label>API key
          <input name="api_key" type="password" autocomplete="new-password" placeholder="keyring or dotenv only" data-testid="provider-auth-api-key-input">
        </label>
        <label>Dotenv file
          <input name="dotenv_file" placeholder=".agentblaster.local.env" data-testid="provider-auth-dotenv-file-input">
        </label>
        <label class="check">
          <input type="checkbox" name="allow_plaintext_secret_file" value="true" data-testid="provider-auth-allow-plaintext-input">
          Allow plaintext dotenv fallback for local development only.
        </label>
        <button type="submit" data-testid="provider-auth-submit">Store reference</button>
      </form>
      {provider_error}
      <ul class="meta" data-testid="provider-auth-posture">
        <li>Env mode stores only a variable reference and never accepts raw API-key material.</li>
        <li>Keyring mode accepts raw API-key entry only to write through the optional OS credential backend or Apple Keychain.</li>
        <li>Dotenv mode is an explicit plaintext fallback for approved local development and requires the plaintext checkbox.</li>
        <li>Provider config stores secret references only; setup status and auth responses do not echo submitted key values.</li>
      </ul>
      <form method="post" action="/providers/auth/clear" data-testid="provider-auth-clear-form">
        <label>Provider
          <select name="provider" required data-testid="provider-auth-clear-select">
            {provider_options}
          </select>
        </label>
        <label class="check">
          <input type="checkbox" name="delete_secret" value="true" data-testid="provider-auth-delete-secret-checkbox">
          Delete writable keyring/dotenv secret when the current reference uses that storage.
        </label>
        <button type="submit" data-testid="provider-auth-clear-submit">Clear auth reference</button>
      </form>
      <p class="meta">Clear removes the provider reference from AgentBlaster config. It refuses to delete environment-variable secrets; unset those in your shell, CI, or enterprise secret manager.</p>
    </section>
    """


def _catalog_panel() -> str:
    index = dashboard_catalog_index()
    catalogs = index["catalogs"]
    try:
        model_count = len(dashboard_model_targets()["model_targets"])
        engine_count = len(dashboard_engine_targets()["targets"])
        surface_count = len(dashboard_workflow_surfaces()["surfaces"])
    except Exception:  # noqa: BLE001 - catalog panel must not block run browsing
        model_count = 0
        engine_count = 0
        surface_count = 0
    links = "\n".join(
        (
            f'<a class="catalog-card" data-testid="catalog-link" '
            f'href="/catalog/{html.escape(item["id"])}" data-api-href="{html.escape(item["href"])}">'
            f'<strong>{html.escape(item["id"].replace("-", " ").title())}</strong>'
            f'<span>{html.escape(item["description"])}</span>'
            '</a>'
        )
        for item in catalogs
        if item["id"] in {
            "models",
            "engine-targets",
            "local-engine-onboarding",
            "workflow-surfaces",
            "telemetry-mappings",
            "campaign-preview",
            "setup-status",
            "providers",
            "review-artifacts",
            "suites",
            "run-plan",
            "run-launch",
        }
    )
    return f"""
    <section class="panel catalog" data-testid="catalog-panel" aria-label="Planning catalogs">
      <h2>Planning catalogs</h2>
      <p class="meta">Review setup metadata before dispatch: {engine_count} engine targets, {model_count} model targets, {surface_count} workflow surfaces, and the local-engine onboarding checklist. Catalog links are read-only and redaction-safe.</p>
      <div class="catalog-grid">
        {links}
      </div>
    </section>
    """


def _security_posture_panel(runs: list[dict[str, Any]], *, auth_required: bool) -> str:
    try:
        providers = dashboard_providers()
        provider_error = ""
    except ConfigError as exc:
        providers = []
        provider_error = f"Provider config unavailable: {html.escape(str(exc))}"
    remote_providers = [provider for provider in providers if provider["remote"]]
    insecure_tls_providers = [provider for provider in providers if provider.get("tls_verify") is False]
    full_trace_runs = [run for run in runs if run["raw_trace_mode"] == RawTraceMode.FULL.value]
    redacted_or_off_runs = [
        run for run in runs if run["raw_trace_mode"] in {RawTraceMode.REDACTED.value, RawTraceMode.OFF.value}
    ]
    cards = [
        _posture_card(
            testid="posture-auth",
            label="Dashboard auth",
            value="enabled" if auth_required else "loopback-only",
            detail="Token required for this session." if auth_required else "No dashboard token configured; keep bind host on loopback.",
            severity="good" if auth_required else "warn",
        ),
        _posture_card(
            testid="posture-remote-providers",
            label="Remote providers",
            value=str(len(remote_providers)),
            detail=(
                "Remote launch remains blocked unless explicitly allowed."
                if remote_providers
                else "No remote providers configured."
            ),
            severity="warn" if remote_providers else "good",
        ),
        _posture_card(
            testid="posture-raw-traces",
            label="Full raw traces",
            value=str(len(full_trace_runs)),
            detail=(
                "Full raw trace runs exist; report downloads remain allowlisted."
                if full_trace_runs
                else f"{len(redacted_or_off_runs)} run(s) use redacted or disabled raw traces."
            ),
            severity="warn" if full_trace_runs else "good",
        ),
        _posture_card(
            testid="posture-artifacts",
            label="Artifact serving",
            value="allowlisted",
            detail="Reports and metrics summaries are served; raw traces and manifests are not linked.",
            severity="good",
        ),
        _posture_card(
            testid="posture-tls",
            label="Insecure TLS providers",
            value=str(len(insecure_tls_providers)),
            detail=(
                "One or more providers disable certificate verification."
                if insecure_tls_providers
                else "TLS certificate verification remains enabled for configured providers."
            ),
            severity="warn" if insecure_tls_providers else "good",
        ),
    ]
    if provider_error:
        cards.append(
            _posture_card(
                testid="posture-provider-config",
                label="Provider config",
                value="error",
                detail=provider_error,
                severity="warn",
            )
        )
    return f"""
    <section class="posture" data-testid="security-posture-panel" aria-label="Security posture">
      {"".join(cards)}
    </section>
    """


def _posture_card(*, testid: str, label: str, value: str, detail: str, severity: str) -> str:
    return f"""<div class="posture-card {html.escape(severity)}" data-testid="{html.escape(testid)}">
      <span>{html.escape(label)}</span>
      <strong>{html.escape(value)}</strong>
      <span>{html.escape(detail)}</span>
    </div>"""


def _provider_options(providers: list[dict[str, Any]]) -> str:
    if not providers:
        return '<option value="" disabled selected>No configured providers</option>'
    return "\n".join(
        (
            f'<option value="{html.escape(provider["name"])}">'
            f'{html.escape(provider["name"])} ({html.escape(provider["contract"])})'
            f'{" remote" if provider["remote"] else ""}</option>'
        )
        for provider in providers
    )


def _suite_options(suites: list[dict[str, Any]]) -> str:
    return "\n".join(
        f'<option value="{html.escape(suite["name"])}">{html.escape(suite["name"])} ({suite["case_count"]})</option>'
        for suite in suites
    )


def _run_artifacts(run_id: str, run_dir: Path) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []
    for artifact_name in REPORT_ARTIFACTS:
        if (run_dir / artifact_name).exists():
            artifacts.append(
                {
                    "name": artifact_name,
                    "label": _artifact_label(artifact_name),
                    "href": f"/runs/{quote(run_id, safe='')}/artifacts/{quote(artifact_name, safe='')}",
                }
            )
    return artifacts


def _artifact_links(run: dict[str, Any]) -> str:
    artifacts = run.get("artifacts", [])
    form = (
        f'<form method="post" action="/runs/{html.escape(quote(run["run_id"], safe=""))}/reports" '
        f'data-testid="report-generate-form">'
        '<input type="hidden" name="formats" value="html,md,json,publication,card,pdf">'
        '<button type="submit">Generate</button>'
        "</form>"
    )
    if not artifacts:
        return f'<span class="meta">not generated</span>{form}'
    links = []
    for artifact in artifacts:
        links.append(
            f'<a data-testid="report-artifact-link" href="{html.escape(artifact["href"])}">'
            f'{html.escape(artifact["label"])}</a>'
        )
    return f'<div class="links">{"".join(links)}{form}</div>'


def _artifact_label(artifact_name: str) -> str:
    labels = {
        "report.html": "HTML",
        "report.md": "MD",
        "report.pdf": "PDF",
        "summary.json": "summary",
        "publication.json": "publication",
        "report-card.svg": "card",
        "report-card.png": "card png",
        "metrics/prometheus-summary.json": "metrics",
    }
    return labels.get(artifact_name, artifact_name)


def _parse_artifact_path(path: str) -> tuple[str, str]:
    relative = path.removeprefix("/runs/")
    if "/artifacts/" not in relative:
        raise ConfigError("invalid artifact path")
    run_id, artifact_name = relative.split("/artifacts/", 1)
    run_id = unquote(run_id).strip("/")
    artifact_name = unquote(artifact_name).strip("/")
    if not run_id or not artifact_name or artifact_name not in REPORT_ARTIFACTS:
        raise ConfigError("unknown dashboard artifact")
    return run_id, artifact_name


def dashboard_artifact_path(runs_dir: Path, run_id: str, artifact_name: str) -> Path:
    if artifact_name not in REPORT_ARTIFACTS:
        raise ConfigError("unknown dashboard artifact")
    run_dir = dashboard_run_dir(runs_dir, run_id)
    artifact_path = run_dir / artifact_name
    if not artifact_path.exists() or not artifact_path.is_file():
        raise ConfigError(f"artifact does not exist: {artifact_name}")
    return artifact_path


def dashboard_run_dir(runs_dir: Path, run_id: str) -> Path:
    if not runs_dir.exists():
        raise ConfigError(f"runs directory does not exist: {runs_dir}")
    for run_dir in sorted(path for path in runs_dir.iterdir() if path.is_dir()):
        try:
            manifest = load_manifest(run_dir)
        except ConfigError:
            continue
        if manifest.run_id != run_id:
            continue
        return run_dir
    raise ConfigError(f"unknown run: {run_id}")


def _valid_env_var_name(value: str) -> bool:
    if not value or value[0].isdigit():
        return False
    return all(character.isalnum() or character == "_" for character in value)


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _payload_bool(payload: dict[str, Any], key: str, *, default: bool = False) -> bool:
    if key not in payload or payload.get(key) in {None, ""}:
        return default
    return _truthy(payload.get(key))


def _truthy(value: Any) -> bool:
    return str(value or "").lower() in {"1", "true", "yes", "on"}


def _error_html(message: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>AgentBlaster Dashboard Error</title></head>
<body>
  <h1>AgentBlaster Dashboard Error</h1>
  <p>{html.escape(message)}</p>
  <p><a href="/">Back to dashboard</a></p>
</body>
</html>
"""


def _login_html(error: str | None = None) -> str:
    error_html = f'<p class="error">{html.escape(error)}</p>' if error else ""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentBlaster Dashboard Login</title>
  <style>
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      font-family: "Avenir Next", "Trebuchet MS", sans-serif;
      color: #111713;
      background:
        radial-gradient(circle at top left, rgba(214, 107, 31, 0.22), transparent 32rem),
        linear-gradient(135deg, #fff8ec 0%, #f5efe4 52%, #dfe7d9 100%);
    }}
    main {{
      width: min(420px, calc(100vw - 32px));
      padding: 28px;
      border: 1px solid #d7cbb7;
      border-radius: 24px;
      background: rgba(255, 252, 245, 0.9);
      box-shadow: 0 22px 70px rgba(40, 30, 18, 0.14);
    }}
    h1 {{ margin: 0 0 8px; font-family: "Iowan Old Style", Georgia, serif; font-size: 42px; }}
    p {{ color: #647067; line-height: 1.5; }}
    label {{ display: grid; gap: 8px; font-weight: 700; }}
    input {{ padding: 12px; border: 1px solid #b9aa93; border-radius: 12px; font: inherit; }}
    button {{ margin-top: 16px; width: 100%; padding: 12px 14px; border: 0; border-radius: 12px; background: #111713; color: #fffdf6; font-weight: 800; cursor: pointer; }}
    .error {{ color: #9b2721; font-weight: 700; }}
  </style>
</head>
<body>
  <main data-testid="dashboard-login">
    <h1>AgentBlaster</h1>
    <p>Enter the dashboard token configured by the operator.</p>
    {error_html}
    <form method="post" action="/login">
      <label>Dashboard token
        <input name="token" type="password" autocomplete="current-password" required autofocus data-testid="dashboard-token-input">
      </label>
      <button type="submit" data-testid="dashboard-login-submit">Unlock dashboard</button>
    </form>
  </main>
</body>
</html>
"""


def _average_metric(values: list[float | int | None]) -> float | None:
    numeric_values = [float(value) for value in values if value is not None]
    if not numeric_values:
        return None
    return round(sum(numeric_values) / len(numeric_values), 3)


def _sum_metric(values: list[float | int | None]) -> float | None:
    numeric_values = [float(value) for value in values if value is not None]
    if not numeric_values:
        return None
    return round(sum(numeric_values), 9)


def _display_metric(value: Any) -> str:
    if value is None:
        return ""
    return html.escape(str(value))


def _payload_model_metadata(value: Any) -> ModelMetadata | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ConfigError("model_metadata must be an object")
    metadata = ModelMetadata.model_validate(value)
    return None if metadata.is_empty() else metadata


def _model_metadata_brief(metadata: dict[str, Any]) -> str:
    parts = [
        metadata.get("architecture"),
        metadata.get("quantization"),
        f"ctx {metadata.get('context_length')}" if metadata.get("context_length") else None,
    ]
    return " / ".join(str(part) for part in parts if part) or "metadata not captured"


def _provider_brief(metadata: dict[str, Any]) -> str:
    parts = [
        metadata.get("base_url_host"),
        "remote" if metadata.get("remote") else "local",
        "tls=verify" if metadata.get("tls_verify", True) else "tls=insecure",
    ]
    return " / ".join(str(part) for part in parts if part)


def _adapter_brief(metadata: dict[str, Any]) -> str:
    parts = [
        metadata.get("adapter_name"),
        metadata.get("adapter_version"),
    ]
    return " / ".join(str(part) for part in parts if part) or "not captured"


def _suite_provenance_brief(provenance: dict[str, Any]) -> str:
    parts = [
        provenance.get("origin"),
        provenance.get("generator_profile"),
        f"seed {provenance.get('generator_seed')}" if provenance.get("generator_seed") is not None else None,
    ]
    return " / ".join(str(part) for part in parts if part) or "not captured"


def _hash_brief(value: Any) -> str:
    if not value:
        return "not captured"
    return str(value)[:12]


def _is_loopback_host(host: str) -> bool:
    if host in LOOPBACK_HOSTS:
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False
