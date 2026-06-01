from __future__ import annotations

from agentblaster.rate_limits import RateLimitPacer, rate_limit_max_concurrency, request_interval_seconds


def test_request_interval_seconds_uses_most_restrictive_rate() -> None:
    assert request_interval_seconds({"requests_per_second": 2}) == 0.5
    assert request_interval_seconds({"requests_per_minute": 60}) == 1.0
    assert request_interval_seconds({"requests_per_second": 10, "requests_per_minute": 60}) == 1.0
    assert request_interval_seconds({}) is None


def test_rate_limit_max_concurrency_reads_common_keys() -> None:
    assert rate_limit_max_concurrency({"max_concurrency": 2}) == 2
    assert rate_limit_max_concurrency({"concurrency": 4}) == 4
    assert rate_limit_max_concurrency({}) is None


def test_rate_limit_pacer_returns_wait_time_without_real_sleep() -> None:
    clock = {"now": 0.0}
    sleeps: list[float] = []

    def monotonic() -> float:
        return clock["now"]

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock["now"] += seconds

    pacer = RateLimitPacer({"requests_per_minute": 60}, sleep_fn=sleep, monotonic_fn=monotonic)

    assert pacer.wait() == 0.0
    assert pacer.wait() == 1000.0
    assert sleeps == [1.0]
