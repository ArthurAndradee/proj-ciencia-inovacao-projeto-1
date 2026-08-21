"""Rate-limit handling for free-tier API keys.

Free tiers cap requests per minute and per day. The per-minute cap is handled by
throttling proactively — cheaper than discovering it through 429s — and by
honouring the server's own retry delay when one arrives anyway. The per-day cap
cannot be waited out within a run, so it raises `QuotaExhausted` and the run
stops cleanly, to be resumed once the quota resets.
"""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable
from typing import Any

RETRYABLE_STATUS: frozenset[int] = frozenset({408, 429, 500, 502, 503, 504})

_STATUS_IN_TEXT = re.compile(r"\b(4\d{2}|5\d{2})\b")
_RETRY_DELAY = re.compile(
    r"retry[_-]?delay['\"]?\s*[:{]\s*['\"]?(?:seconds:\s*)?(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_DAILY_QUOTA = re.compile(r"per\s*day|perday|daily\s+(?:limit|quota)", re.IGNORECASE)
_BILLING = re.compile(r"credits?\s+(?:are\s+)?depleted|prepayment|billing", re.IGNORECASE)


class QuotaExhausted(Exception):
    """The daily quota is gone; waiting inside this run would be pointless."""


class PermanentAPIError(Exception):
    """Bad key, bad request, or anything else a retry cannot fix."""


def status_code(exc: BaseException) -> int | None:
    """Best-effort HTTP status of an SDK exception, from attributes or message."""
    for attribute in ("code", "status_code", "status"):
        value: Any = getattr(exc, attribute, None)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    match = _STATUS_IN_TEXT.search(str(exc))
    return int(match.group(1)) if match else None


def retry_delay(exc: BaseException) -> float | None:
    """Delay requested by the server (RetryInfo), in seconds, when present."""
    match = _RETRY_DELAY.search(str(exc))
    return float(match.group(1)) if match else None


def quota_exhaustion_reason(exc: BaseException) -> str | None:
    """Why a 429 stopped the run, once retrying has already failed.

    None of these messages is the verdict it sounds like. The same key that
    answers "prepaid credits are depleted", or even "quota exceeded per day",
    has been observed answering normally seconds later — so every 429 is
    retried, and this only names what went wrong after the retries are gone.
    Trusting the wording on sight aborted two runs over transient refusals.
    """
    if status_code(exc) != 429:
        return None
    message: str = str(exc)
    if _BILLING.search(message):
        return (
            "the API kept refusing with 429, blaming the prepaid balance. A project "
            "with billing enabled has no free tier: add credits, or use a key from a "
            "project without billing"
        )
    if _DAILY_QUOTA.search(message):
        return "the API kept refusing with 429: daily quota exhausted"
    return "the API kept refusing with 429 (rate limited)"


_KEY_FAULT = re.compile(
    r"API_KEY_INVALID|API key not valid|UNAUTHENTICATED|PERMISSION_DENIED"
    r"|ACCESS_TOKEN_TYPE_UNSUPPORTED|invalid authentication credentials",
    re.IGNORECASE,
)


def is_key_fault(exc: BaseException) -> bool:
    """True when the credential is the problem, not the request.

    The distinction decides who dies. A malformed prompt fails identically on
    every key, so it must abort the run; a rejected credential is one key's
    problem and the others are unaffected. Conflating them cost a run: one bad
    key answered 401, the error propagated, and all seven workers died together
    without finishing a single task.
    """
    if status_code(exc) in (401, 403):
        return True
    return bool(_KEY_FAULT.search(str(exc)))


def is_retryable(exc: BaseException) -> bool:
    code: int | None = status_code(exc)
    if code is None:
        return True  # unclassified failures are usually transport-level
    return code in RETRYABLE_STATUS


class RateLimiter:
    """Spaces calls out to stay under a requests-per-minute cap.

    Keeping consecutive calls `60 / rpm` seconds apart is enough; no window
    bookkeeping is required. Shared by every worker, so the cap applies to the
    run as a whole — the reservation is made under a lock and the sleep happens
    outside it, or concurrent workers would serialise on each other's waits.
    """

    def __init__(
        self,
        rpm: int,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.rpm: int = rpm
        self._sleep: Callable[[float], None] = sleep
        self._clock: Callable[[], float] = clock
        self._next_free: float | None = None
        self._lock = threading.Lock()

    @property
    def min_interval(self) -> float:
        return 60.0 / self.rpm if self.rpm > 0 else 0.0

    def acquire(self) -> float:
        """Block until the next call is allowed; return how long it waited."""
        interval: float = self.min_interval
        if interval <= 0:
            return 0.0
        with self._lock:
            now: float = self._clock()
            start_at: float = now if self._next_free is None else max(now, self._next_free)
            self._next_free = start_at + interval
        waited: float = start_at - now
        if waited > 0:
            self._sleep(waited)
        return max(waited, 0.0)
