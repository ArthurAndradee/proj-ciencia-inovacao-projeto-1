"""Pool of free-tier API keys: parallel capacity, with failover when one dries up.

A free-tier key caps out at a daily quota per model, and that cap — not latency —
is what ends a long run. Keys from separate projects carry separate quotas, so
several of them multiply the capacity of a run, provided two things hold: calls
are spread across the keys instead of draining one, and a key that reports its
quota gone steps aside rather than aborting the run.

The pool is an `LLMClient` like any other, so the agents and the orchestrator
never learn that more than one key exists.
"""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from . import ratelimit
from .llm import Completion, GeminiClient, LLMClient, Message


# A refused call is usually the service shedding load, not a spent allowance:
# measured on the free tier, ~4% of calls are refused under any load, and the
# same key answers again shortly after. So a key steps aside for a while and
# comes back, and only a key that keeps failing across several such pauses is
# written off for the run.
COOLDOWN_BASE_S: float = 30.0
COOLDOWN_MAX_S: float = 300.0
MAX_STRIKES: int = 6


@dataclass
class KeyState:
    """One key's share of the run: what it answered and what it can still serve."""

    label: str
    client: LLMClient
    attempts: int = 0
    failures: int = 0
    dead: bool = False
    exhausted_models: set[str] = field(default_factory=set)
    # Per model: when the key may be tried again, and how many pauses in a row
    # it has taken without an answer in between.
    cooldown_until: dict[str, float] = field(default_factory=dict)
    strikes: dict[str, int] = field(default_factory=dict)

    def retired(self, model: str) -> bool:
        """Written off for this model — no amount of waiting brings it back."""
        return self.dead or model in self.exhausted_models

    def resting(self, model: str, now: float) -> bool:
        return self.cooldown_until.get(model, 0.0) > now

    def serves(self, model: str, now: float = float("inf")) -> bool:
        return not self.retired(model) and not self.resting(model, now)

    def cooldown_for(self, model: str) -> float:
        """Back off further each time, so a truly dead key is not hammered."""
        strikes: int = self.strikes.get(model, 0)
        grown: float = COOLDOWN_BASE_S * float(2 ** max(strikes - 1, 0))
        return min(grown, COOLDOWN_MAX_S)


class PooledClient:
    """Spreads calls over several keys and routes around the exhausted ones.

    Quota is per model, not per key: a key whose flash-lite allowance is gone
    keeps answering for another model. Exhaustion is therefore recorded per
    (key, model) pair, and a key is never written off wholesale.
    """

    def __init__(
        self,
        clients: Sequence[LLMClient],
        labels: Sequence[str] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not clients:
            raise ValueError(
                "no API keys. Set GOOGLE_API_KEYS (comma-separated) or GOOGLE_API_KEY in .env."
            )
        names: Sequence[str] = labels or [f"key{i}" for i in range(1, len(clients) + 1)]
        self._keys: list[KeyState] = [
            KeyState(label=label, client=client) for label, client in zip(names, clients)
        ]
        self._lock = threading.Lock()
        self._sleep: Callable[[float], None] = sleep
        self._clock: Callable[[], float] = clock

    @classmethod
    def from_keys(
        cls,
        api_keys: Sequence[str],
        temperature: float = 0.2,
        max_output_tokens: int = 8192,
        max_retries: int = 3,
        rpm: int = 0,
        rpm_total: int = 0,
        timeout_s: float = 180.0,
    ) -> PooledClient:
        """One `GeminiClient` per key, sharing a pool-wide limiter when asked.

        A per-key limiter was the original design, on the reasoning that
        separate projects carry separate quotas. Measurement did not bear it
        out: one key sustains 30 rpm cleanly, but the refusal rate tracks the
        rate of the pool as a whole, not of any key. Since `rpm` is per key,
        N keys silently authorise N times the traffic — twelve keys at 30 rpm
        each asked for 360 rpm and the run collapsed in forty seconds.

        So `rpm_total` caps the pool as one, which is the number the service
        appears to watch. When it is set it is the only limiter in force, and
        the per-key `rpm` is not applied on top: at any realistic pool size the
        aggregate cap binds first anyway, and two limiters would only make the
        effective rate hard to read off the configuration.
        """
        shared: ratelimit.RateLimiter | None = (
            ratelimit.RateLimiter(rpm_total) if rpm_total > 0 else None
        )
        clients: list[LLMClient] = [
            GeminiClient(
                api_key=key,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                max_retries=max_retries,
                rpm=0 if shared is not None else rpm,
                limiter=shared,
                timeout_s=timeout_s,
            )
            for key in api_keys
        ]
        return cls(clients)

    def generate(
        self,
        model: str,
        system: str,
        messages: list[Message],
        temperature: float | None = None,
    ) -> Completion:
        while True:
            key: KeyState | None = self._claim(model)
            if key is None:
                # Every key is either written off or resting. Resting is not the
                # end of the run: waiting for the earliest one to come back is
                # the whole point of the pause.
                wait: float | None = self._next_available_in(model)
                if wait is None:
                    raise ratelimit.QuotaExhausted(
                        f"{model}: no key left to serve it ({self._summary(model)})"
                    )
                self._sleep(wait)
                continue
            try:
                completion: Completion = key.client.generate(
                    model, system, messages, temperature
                )
            except ratelimit.PermanentAPIError as exc:
                # A rejected credential is this key's problem alone; a bad
                # request would fail the same way on every key, so it aborts.
                if not ratelimit.is_key_fault(exc):
                    raise
                self._condemn(key, exc)
            except ratelimit.QuotaExhausted as exc:
                # Only a 429 that named a per-day quota or a billing problem is
                # beyond waiting out. A bare one is the service shedding load.
                if getattr(exc, "permanent", True):
                    self._retire(key, model)
                else:
                    self._quarantine(key, model)
            except RuntimeError:
                # Retries inside the client are spent and the failure was still
                # retryable — evidence about this minute, not about the day.
                self._quarantine(key, model)
            else:
                self._clear_strikes(key, model)
                return completion

    def _claim(self, model: str) -> KeyState | None:
        """Reserve the least-used key that still serves this model.

        The reservation counts the call before it is made, so that concurrent
        workers see each other's choices and fan out instead of all picking the
        same idle key.
        """
        now: float = self._clock()
        with self._lock:
            candidates: list[KeyState] = [k for k in self._keys if k.serves(model, now)]
            if not candidates:
                return None
            chosen: KeyState = min(candidates, key=lambda k: k.attempts)
            chosen.attempts += 1
            return chosen

    def _retire(self, key: KeyState, model: str) -> None:
        with self._lock:
            key.exhausted_models.add(model)
            key.failures += 1

    def _quarantine(self, key: KeyState, model: str) -> None:
        """Stand the key down for a while; retire it only if it keeps failing."""
        with self._lock:
            key.failures += 1
            strikes: int = key.strikes.get(model, 0) + 1
            key.strikes[model] = strikes
            if strikes >= MAX_STRIKES:
                key.exhausted_models.add(model)
                key.cooldown_until.pop(model, None)
            else:
                key.cooldown_until[model] = self._clock() + key.cooldown_for(model)

    def _clear_strikes(self, key: KeyState, model: str) -> None:
        """An answer proves the key is healthy; the streak starts over."""
        with self._lock:
            key.strikes.pop(model, None)
            key.cooldown_until.pop(model, None)

    def _next_available_in(self, model: str) -> float | None:
        """Seconds until the earliest resting key returns, or None if none will."""
        now: float = self._clock()
        with self._lock:
            waits: list[float] = [
                k.cooldown_until[model] - now
                for k in self._keys
                if not k.retired(model) and k.resting(model, now)
            ]
        # A hair past the deadline, so the key is genuinely eligible on the
        # next pass instead of missing it by a rounding error and looping.
        return min(waits) + 0.01 if waits else None

    def _condemn(self, key: KeyState, exc: BaseException) -> None:
        """Drop a key the API refuses to authenticate, for every model."""
        with self._lock:
            already: bool = key.dead
            key.dead = True
            key.failures += 1
        if not already:
            # Said once, loudly: a run silently short one key is a run whose
            # capacity no longer matches what the operator thinks it is.
            print(
                f"warning: {key.label} rejected by the API and dropped from the "
                f"pool ({str(exc)[:120]})",
                file=sys.stderr,
                flush=True,
            )

    def _summary(self, model: str) -> str:
        with self._lock:
            return ", ".join(
                f"{k.label}: {k.attempts - k.failures} call(s)"
                + (", rejected" if k.dead else ", spent" if k.retired(model) else "")
                for k in self._keys
            )

    def usage(self) -> list[dict[str, Any]]:
        """Per-key accounting for the end-of-run summary."""
        with self._lock:
            return [
                {
                    "key": k.label,
                    # Attempts are counted on reservation, so a failed call is
                    # an attempt that never became an answer. Report both.
                    "calls": k.attempts - k.failures,
                    "failures": k.failures,
                    "rejected": k.dead,
                    "exhausted": sorted(k.exhausted_models),
                    # Pauses taken and returned from: the number that says a run
                    # was slowed by transient refusals rather than stopped.
                    "quarantines": sum(k.strikes.values()),
                }
                for k in self._keys
            ]
