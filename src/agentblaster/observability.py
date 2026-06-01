from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx


@dataclass(frozen=True)
class PrometheusScrape:
    phase: str
    url: str
    scraped_at: str
    latency_ms: float | None
    ok: bool
    status_code: int | None = None
    text: str = ""
    error: str | None = None

    def metadata(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "url": self.url,
            "scraped_at": self.scraped_at,
            "latency_ms": self.latency_ms,
            "ok": self.ok,
            "status_code": self.status_code,
            "error": self.error,
        }


PROMETHEUS_ARTIFACTS = [
    "metrics/prometheus-before.prom",
    "metrics/prometheus-after.prom",
    "metrics/prometheus-summary.json",
]


def scrape_prometheus_metrics(url: str, *, phase: str, timeout_seconds: float = 2.0) -> PrometheusScrape:
    started = datetime.now(UTC)
    timer = started.timestamp()
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.get(url)
    except httpx.HTTPError as exc:
        completed = datetime.now(UTC)
        return PrometheusScrape(
            phase=phase,
            url=url,
            scraped_at=completed.isoformat(),
            latency_ms=round(max((completed.timestamp() - timer) * 1000, 0.0), 3),
            ok=False,
            error=str(exc),
        )

    completed = datetime.now(UTC)
    return PrometheusScrape(
        phase=phase,
        url=url,
        scraped_at=completed.isoformat(),
        latency_ms=round(max((completed.timestamp() - timer) * 1000, 0.0), 3),
        ok=response.is_success,
        status_code=response.status_code,
        text=response.text if response.is_success else "",
        error=None if response.is_success else response.text[:240],
    )


def prometheus_summary(before: PrometheusScrape | None, after: PrometheusScrape | None) -> dict[str, Any]:
    before_samples = parse_prometheus_samples(before.text if before else "")
    after_samples = parse_prometheus_samples(after.text if after else "")
    common_keys = sorted(set(before_samples) & set(after_samples))
    deltas = {
        key: {
            "before": before_samples[key],
            "after": after_samples[key],
            "delta": round(after_samples[key] - before_samples[key], 6),
        }
        for key in common_keys
    }
    return {
        "format": "agentblaster-prometheus-summary-v1",
        "before": before.metadata() if before else None,
        "after": after.metadata() if after else None,
        "sample_count_before": len(before_samples),
        "sample_count_after": len(after_samples),
        "deltas": deltas,
    }


def parse_prometheus_samples(text: str) -> dict[str, float]:
    samples: dict[str, float] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) < 2:
            continue
        try:
            samples[parts[0]] = float(parts[1])
        except ValueError:
            continue
    return samples


def prometheus_summary_json(before: PrometheusScrape | None, after: PrometheusScrape | None) -> str:
    return json.dumps(prometheus_summary(before, after), indent=2, sort_keys=True) + "\n"
