"""Rate-limit handling for free-tier API keys.

Free tiers cap requests per minute and per day. The per-minute cap is handled by
throttling proactively — cheaper than discovering it through 429s — and by
honouring the server's own retry delay when one arrives anyway. The per-day cap
cannot be waited out within a run, so it raises `QuotaExhausted` and the run
stops cleanly, to be resumed once the quota resets.
"""

from __future__ import annotations

import re
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
    """Why a 429 cannot be waited out within this run, or None if it can.

    A per-minute 429 is worth retrying; a spent daily quota or an empty prepaid
    balance is not — those need a new day or a human, so the run should stop
    instead of spending its retries on every remaining task.
    """
    if status_code(exc) != 429:
        return None
    message: str = str(exc)
    if _BILLING.search(message):
        return (
            "prepaid credits are depleted — a project with billing enabled has no "
            "free tier; add credits or use a key from a project without billing"
        )
    if _DAILY_QUOTA.search(message):
        return "daily quota exhausted"
    return None


def is_retryable(exc: BaseException) -> bool:
    code: int | None = status_code(exc)
    if code is None:
        return True  # unclassified failures are usually transport-level
    return code in RETRYABLE_STATUS


class RateLimiter:
    """Spaces calls out to stay under a requests-per-minute cap.

    A single serial worker only needs to keep consecutive calls at least
    `60 / rpm` seconds apart; no window bookkeeping is required.
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
        self._last_call: float | None = None

    @property
    def min_interval(self) -> float:
        return 60.0 / self.rpm if self.rpm > 0 else 0.0

    def acquire(self) -> float:
        """Block until the next call is allowed; return how long it waited."""
        interval: float = self.min_interval
        if interval <= 0:
            return 0.0
        now: float = self._clock()
        waited: float = 0.0
        if self._last_call is not None:
            remaining: float = interval - (now - self._last_call)
            if remaining > 0:
                self._sleep(remaining)
                waited = remaining
        self._last_call = self._clock()
        return waited
