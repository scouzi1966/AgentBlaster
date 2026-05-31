from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from agentblaster.adapters import ProviderAdapter, adapter_for
from agentblaster.models import (
    AdapterResponse,
    ApiContract,
    BenchmarkResult,
    ProviderConfig,
    RawTraceMode,
    RunManifest,
)
from agentblaster.redaction import redact_value

SMOKE_CASE_ID = "protocol-smoke-chat"


def new_run_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"run_{timestamp}_{uuid4().hex[:8]}"


class ArtifactWriter:
    def __init__(self, output_dir: Path, manifest: RunManifest) -> None:
        self.run_dir = output_dir / manifest.run_id
        self.manifest = manifest

    def initialize(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / "manifest.json").write_text(
            json.dumps(self.manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def write_raw_response(self, case_id: str, raw: dict, mode: RawTraceMode) -> str | None:
        if mode is RawTraceMode.OFF:
            return None
        raw_dir = self.run_dir / "raw"
        raw_dir.mkdir(exist_ok=True)
        payload = raw if mode is RawTraceMode.FULL else redact_value(raw)
        path = raw_dir / f"{case_id}.response.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return str(path.relative_to(self.run_dir))

    def append_result(self, result: BenchmarkResult) -> None:
        with (self.run_dir / "results.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(result.model_dump_json(exclude_none=True) + "\n")


class SmokeRunner:
    def __init__(
        self,
        provider: ProviderConfig,
        *,
        adapter: ProviderAdapter | None = None,
        output_dir: Path = Path("runs"),
        raw_trace_mode: RawTraceMode = RawTraceMode.REDACTED,
    ) -> None:
        self.provider = provider
        self.adapter = adapter or adapter_for(provider)
        self.output_dir = output_dir
        self.raw_trace_mode = raw_trace_mode

    def run(self, model: str | None = None) -> BenchmarkResult:
        resolved_model = model or self.provider.default_model
        if not resolved_model:
            raise ValueError("model is required when provider has no default_model")

        run_id = new_run_id()
        manifest = RunManifest(
            run_id=run_id,
            suite="smoke",
            provider=self.provider.name,
            contract=self.provider.contract,
            model=resolved_model,
            raw_trace_mode=self.raw_trace_mode,
            created_at=datetime.now(UTC).isoformat(),
        )
        writer = ArtifactWriter(self.output_dir, manifest)
        writer.initialize()

        response = self.adapter.smoke_chat(resolved_model)
        raw_response_path = writer.write_raw_response(SMOKE_CASE_ID, response.raw, self.raw_trace_mode)
        result = self._result_from_response(run_id, resolved_model, response, raw_response_path)
        writer.append_result(result)
        return result

    def _result_from_response(
        self,
        run_id: str,
        model: str,
        response: AdapterResponse,
        raw_response_path: str | None,
    ) -> BenchmarkResult:
        input_tokens, output_tokens, total_tokens = normalize_usage(response.contract, response.raw)
        expected_seen = "agentblaster-ok" in response.text.lower()
        ok = 200 <= response.status_code < 300 and expected_seen
        message = "ok" if ok else response.text[:240] or f"HTTP {response.status_code}"

        return BenchmarkResult(
            run_id=run_id,
            case_id=SMOKE_CASE_ID,
            suite="smoke",
            provider=self.provider.name,
            contract=response.contract,
            model=model,
            ok=ok,
            status_code=response.status_code,
            latency_ms=round(response.latency_ms, 3),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            failure_class=None if ok else "model_quality",
            message=message,
            raw_response_path=raw_response_path,
        )


def normalize_usage(contract: ApiContract, raw: dict) -> tuple[int | None, int | None, int | None]:
    usage = raw.get("usage")
    if not isinstance(usage, dict):
        return None, None, None

    if contract is ApiContract.OPENAI:
        input_tokens = _optional_int(usage.get("prompt_tokens"))
        output_tokens = _optional_int(usage.get("completion_tokens"))
        total_tokens = _optional_int(usage.get("total_tokens"))
        return input_tokens, output_tokens, total_tokens

    if contract is ApiContract.ANTHROPIC:
        input_tokens = _optional_int(usage.get("input_tokens"))
        output_tokens = _optional_int(usage.get("output_tokens"))
        cache_read = _optional_int(usage.get("cache_read_input_tokens")) or 0
        cache_write = _optional_int(usage.get("cache_creation_input_tokens")) or 0
        total_tokens = None
        if input_tokens is not None or output_tokens is not None:
            total_tokens = (input_tokens or 0) + (output_tokens or 0) + cache_read + cache_write
        return input_tokens, output_tokens, total_tokens

    return None, None, None


def _optional_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
