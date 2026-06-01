from __future__ import annotations

import time
from threading import Lock
from typing import Any, Callable


def request_interval_seconds(rate_limits: dict[str, Any]) -> float | None:
    intervals: list[float] = []
    requests_per_second = _number(_first_present(rate_limits.get("requests_per_second"), rate_limits.get("rps")))
    requests_per_minute = _number(
        _first_present(
            rate_limits.get("requests_per_minute"),
            rate_limits.get("rpm"),
            rate_limits.get("max_requests_per_minute"),
        )
    )
    if requests_per_second and requests_per_second > 0:
        intervals.append(1 / requests_per_second)
    if requests_per_minute and requests_per_minute > 0:
        intervals.append(60 / requests_per_minute)
    return max(intervals) if intervals else None


def rate_limit_max_concurrency(rate_limits: dict[str, Any]) -> int | None:
    value = _number(_first_present(rate_limits.get("max_concurrency"), rate_limits.get("concurrency")))
    if value is None or value <= 0:
        return None
    return int(value)


class RateLimitPacer:
    """Thread-safe request pacer for provider-level request rate limits."""

    def __init__(
        self,
        rate_limits: dict[str, Any],
        *,
        sleep_fn: Callable[[float], None] = time.sleep,
        monotonic_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self.interval_seconds = request_interval_seconds(rate_limits)
        self._sleep = sleep_fn
        self._monotonic = monotonic_fn
        self._lock = Lock()
        self._next_allowed_at = 0.0

    def wait(self) -> float:
        if self.interval_seconds is None:
            return 0.0
        with self._lock:
            now = self._monotonic()
            wait_seconds = max(self._next_allowed_at - now, 0.0)
            scheduled_at = max(now, self._next_allowed_at)
            self._next_allowed_at = scheduled_at + self.interval_seconds
        if wait_seconds > 0:
            self._sleep(wait_seconds)
        return round(wait_seconds * 1000, 3)


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_present(*values):
    for value in values:
        if value is not None:
            return value
    return None
