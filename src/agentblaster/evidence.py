from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import tomllib
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from agentblaster.config import ProviderStore
from agentblaster.errors import ConfigError
from agentblaster.mcp import available_mcp_profiles, mcp_profile_tool_schemas
from agentblaster.policy import load_policy
from agentblaster.provider_audit import audit_providers
from agentblaster.release import build_release_provenance
from agentblaster.skills import available_skill_packs, skill_pack_text
from agentblaster.suite_audit import audit_suite
from agentblaster.suites import get_builtin_suite, load_suite_file
from agentblaster.toolsim import SAFE_TOOL_SCHEMAS


ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def create_evidence_bundle(
    *,
    output_dir: Path,
    suite: str = "smoke",
    suite_file: Path | None = None,
    policy: Path | None = None,
    project_root: Path | None = None,
    include_provider_audit: bool = False,
) -> Path:
    """Create a redaction-safe static governance evidence bundle."""

    root = (project_root or Path.cwd()).resolve()
    suite_definition = load_suite_file(suite_file) if suite_file else get_builtin_suite(suite)
    bundle_id = _safe_bundle_id(suite_definition.name)
    artifacts: dict[str, bytes] = {}

    artifacts["suite-audit.json"] = _json_bytes(audit_suite(suite_definition).model_dump(mode="json"))
    artifacts["catalogs/simulated-tools.json"] = _json_bytes(_simulated_tools_catalog())
    artifacts["catalogs/mcp-profiles.json"] = _json_bytes(_mcp_profiles_catalog())
    artifacts["catalogs/skills.json"] = _json_bytes(_skills_catalog())
    artifacts["release-provenance.json"] = _json_bytes(_release_provenance(root))
    if policy is not None:
        try:
            artifacts["policy.yaml"] = policy.read_bytes()
        except OSError as exc:
            raise ConfigError(f"unable to read policy file {policy}: {exc}") from exc
    if include_provider_audit:
        provider_policy = load_policy(policy) if policy is not None else load_policy(None)
        artifacts["provider-audit.json"] = _json_bytes(
            audit_providers(ProviderStore().list(), provider_policy).model_dump(mode="json")
        )

    manifest = {
        "schema": "agentblaster.evidence-bundle",
        "schema_version": 1,
        "created_at": _utc_now(),
        "suite": suite_definition.name,
        "suite_file": str(suite_file) if suite_file else None,
        "policy_file": str(policy) if policy else None,
        "includes_provider_audit": include_provider_audit,
        "project_root": str(root),
        "artifacts": [
            {
                "path": name,
                "sha256": sha256(data).hexdigest(),
                "size_bytes": len(data),
            }
            for name, data in sorted(artifacts.items())
        ],
        "security": {
            "contains_provider_config": False,
            "contains_redacted_provider_audit": include_provider_audit,
            "contains_raw_secrets": False,
            "contains_raw_provider_payloads": False,
            "contains_raw_traces": False,
            "notes": "Static evidence bundle only. Does not contact providers, resolve secrets, or execute tools.",
        },
    }
    artifacts["manifest.json"] = _json_bytes(manifest)

    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{bundle_id}.agentblaster-evidence.zip"
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name, data in sorted(artifacts.items()):
            info = ZipInfo(name, ZIP_TIMESTAMP)
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, data)
    return output


def _simulated_tools_catalog() -> dict[str, Any]:
    items = []
    for name, schema in sorted(SAFE_TOOL_SCHEMAS.items()):
        function = schema.get("function", {})
        parameters = function.get("parameters", {}) if isinstance(function, dict) else {}
        required = parameters.get("required", []) if isinstance(parameters, dict) else []
        items.append(
            {
                "name": name,
                "description": str(function.get("description", "")) if isinstance(function, dict) else "",
                "required_arguments": list(required) if isinstance(required, list) else [],
                "host_execution": False,
            }
        )
    return {"catalog": "agentblaster.simulated-tools", "items": items}


def _mcp_profiles_catalog() -> dict[str, Any]:
    items = []
    for profile in available_mcp_profiles():
        schemas = mcp_profile_tool_schemas(profile)
        items.append(
            {
                "name": profile,
                "tool_count": len(schemas),
                "tool_names": [_tool_schema_display_name(schema) for schema in schemas],
                "host_execution": False,
            }
        )
    return {"catalog": "agentblaster.mcp-profiles", "items": items}


def _skills_catalog() -> dict[str, Any]:
    items = []
    for name in available_skill_packs():
        text = skill_pack_text(name)
        lines = text.splitlines()
        heading = next((line.lstrip("# ").strip() for line in lines if line.strip()), name)
        items.append(
            {
                "name": name,
                "heading": heading,
                "line_count": len(lines),
                "char_count": len(text),
                "host_execution": False,
            }
        )
    return {"catalog": "agentblaster.skills", "items": items}


def _release_provenance(project_root: Path) -> dict[str, Any]:
    pyproject = project_root / "pyproject.toml"
    if not pyproject.exists():
        raise ConfigError(f"pyproject.toml not found at project root: {project_root}")
    try:
        pyproject_data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"invalid pyproject.toml at {pyproject}: {exc}") from exc
    return build_release_provenance(
        pyproject_data,
        project_root=project_root,
        include_installed=False,
        include_source_hashes=True,
    )


def _tool_schema_display_name(schema: dict[str, Any]) -> str:
    function = schema.get("function")
    if isinstance(function, dict) and isinstance(function.get("name"), str):
        return function["name"]
    name = schema.get("name")
    return name if isinstance(name, str) else "unnamed"


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _safe_bundle_id(name: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_", "."} else "-" for char in name).strip("-") or "suite"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
