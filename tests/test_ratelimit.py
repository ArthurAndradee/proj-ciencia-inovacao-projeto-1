from typing import Any

from arc_experiment.ratelimit import (
    RateLimiter,
    is_retryable,
    quota_exhaustion_reason,
    retry_delay,
    status_code,
)


class FakeAPIError(Exception):
    """Stands in for google.genai errors, which carry a code and a JSON message."""

    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code: int = code


PER_MINUTE_429: str = (
    "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'Quota exceeded for "
    "GenerateRequestsPerMinutePerProjectPerModel', 'details': [{'@type': "
    "'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '38s'}]}}"
)
PER_DAY_429: str = (
    "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'Quota exceeded for "
    "GenerateRequestsPerDayPerProjectPerModel'}}"
)
CREDITS_429: str = (
    "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'Your prepayment "
    "credits are depleted. Please go to AI Studio to manage your project and billing.'}}"
)


def test_status_code_from_attribute() -> None:
    assert status_code(FakeAPIError("boom", code=503)) == 503


def test_status_code_from_message() -> None:
    assert status_code(FakeAPIError(PER_MINUTE_429)) == 429


def test_status_code_when_unknown() -> None:
    assert status_code(ConnectionResetError("connection reset by peer")) is None


def test_retry_delay_is_read_from_retry_info() -> None:
    assert retry_delay(FakeAPIError(PER_MINUTE_429)) == 38.0


def test_retry_delay_absent() -> None:
    assert retry_delay(FakeAPIError("500 internal error")) is None


def test_the_429_wording_only_names_a_failure_that_already_persisted() -> None:
    daily = quota_exhaustion_reason(FakeAPIError(PER_DAY_429))
    assert daily is not None and "daily quota" in daily
    minute = quota_exhaustion_reason(FakeAPIError(PER_MINUTE_429))
    assert minute is not None and "rate limited" in minute


def test_a_credits_429_is_diagnosed_as_billing() -> None:
    reason = quota_exhaustion_reason(FakeAPIError(CREDITS_429))
    assert reason is not None and "billing" in reason


def test_non_429_is_never_a_quota_exhaustion() -> None:
    assert quota_exhaustion_reason(FakeAPIError("503 service unavailable")) is None


def test_retryable_classification() -> None:
    assert is_retryable(FakeAPIError(PER_MINUTE_429))
    assert is_retryable(FakeAPIError("503 service unavailable"))
    assert is_retryable(ConnectionError("transport failed"))  # unclassified: retry
    assert not is_retryable(FakeAPIError("400 INVALID_ARGUMENT: API key not valid"))
    assert not is_retryable(FakeAPIError("permission denied", code=403))


class Clock:
    """Monotonic clock whose only advance is the sleeping the limiter does."""

    def __init__(self) -> None:
        self.now: float = 0.0
        self.slept: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def make_limiter(rpm: int) -> tuple[RateLimiter, Clock]:
    clock = Clock()
    return RateLimiter(rpm, sleep=clock.sleep, clock=clock.time), clock


def test_limiter_spaces_calls_by_the_minimum_interval() -> None:
    limiter, clock = make_limiter(rpm=10)
    assert limiter.min_interval == 6.0

    assert limiter.acquire() == 0.0  # first call goes straight through
    assert limiter.acquire() == 6.0
    assert clock.slept == [6.0]


def test_limiter_does_not_wait_when_the_caller_was_already_slow() -> None:
    limiter, clock = make_limiter(rpm=10)
    limiter.acquire()
    clock.now += 30.0  # the request itself took longer than the interval
    assert limiter.acquire() == 0.0
    assert clock.slept == []


def test_limiter_disabled_when_rpm_is_zero() -> None:
    limiter, clock = make_limiter(rpm=0)
    assert limiter.min_interval == 0.0
    assert all(limiter.acquire() == 0.0 for _ in range(5))
    assert clock.slept == []


def test_ten_calls_at_ten_rpm_take_about_a_minute() -> None:
    limiter, clock = make_limiter(rpm=10)
    for _ in range(10):
        limiter.acquire()
    assert clock.now == 54.0  # nine gaps of six seconds


def test_fake_error_shape_matches_what_the_helpers_expect() -> None:
    error: Any = FakeAPIError(PER_MINUTE_429, code=429)
    assert status_code(error) == 429 and retry_delay(error) == 38.0


def test_limiter_spaces_concurrent_workers_against_each_other() -> None:
    """The cap belongs to the run, not to each thread."""
    import threading

    limiter = RateLimiter(rpm=60, sleep=lambda _: None, clock=lambda: 0.0)
    waits: list[float] = []
    lock = threading.Lock()

    def call() -> None:
        waited = limiter.acquire()
        with lock:
            waits.append(waited)

    threads = [threading.Thread(target=call) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # With a frozen clock each worker must queue behind the previous slot,
    # so the waits are 0s, 1s, 2s, 3s, 4s rather than five zeros.
    assert sorted(waits) == [0.0, 1.0, 2.0, 3.0, 4.0]
