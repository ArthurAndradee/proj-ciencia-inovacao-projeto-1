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

import threading
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from . import ratelimit
from .llm import Completion, GeminiClient, LLMClient, Message


@dataclass
class KeyState:
    """One key's share of the run: what it answered and what it can still serve."""

    label: str
    client: LLMClient
    attempts: int = 0
    failures: int = 0
    exhausted_models: set[str] = field(default_factory=set)

    def serves(self, model: str) -> bool:
        return model not in self.exhausted_models


class PooledClient:
    """Spreads calls over several keys and routes around the exhausted ones.

    Quota is per model, not per key: a key whose flash-lite allowance is gone
    keeps answering for another model. Exhaustion is therefore recorded per
    (key, model) pair, and a key is never written off wholesale.
    """

    def __init__(self, clients: Sequence[LLMClient], labels: Sequence[str] | None = None) -> None:
        if not clients:
            raise ValueError(
                "no API keys. Set GOOGLE_API_KEYS (comma-separated) or GOOGLE_API_KEY in .env."
            )
        names: Sequence[str] = labels or [f"key{i}" for i in range(1, len(clients) + 1)]
        self._keys: list[KeyState] = [
            KeyState(label=label, client=client) for label, client in zip(names, clients)
        ]
        self._lock = threading.Lock()

    @classmethod
    def from_keys(
        cls,
        api_keys: Sequence[str],
        temperature: float = 0.2,
        max_output_tokens: int = 8192,
        max_retries: int = 3,
        rpm: int = 0,
        timeout_s: float = 180.0,
    ) -> PooledClient:
        """One `GeminiClient` per key, each with its own rate limiter.

        The limiter must not be shared. Quotas are per project, so a shared one
        would hold the whole pool to a single key's requests-per-minute and give
        back exactly the throughput the extra keys were meant to buy.
        """
        clients: list[LLMClient] = [
            GeminiClient(
                api_key=key,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                max_retries=max_retries,
                rpm=rpm,
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
                raise ratelimit.QuotaExhausted(
                    f"{model}: every key is out of quota ({self._summary(model)})"
                )
            try:
                return key.client.generate(model, system, messages, temperature)
            except ratelimit.QuotaExhausted:
                # This key's daily allowance for this model is gone. Waiting
                # cannot fix it, but another key is a different quota entirely.
                self._retire(key, model)
            except RuntimeError:
                # Retries inside the client are spent and the failure was still
                # retryable. Treat the key as spent for this model rather than
                # keep paying its backoff; a healthy key answers immediately.
                self._retire(key, model)

    def _claim(self, model: str) -> KeyState | None:
        """Reserve the least-used key that still serves this model.

        The reservation counts the call before it is made, so that concurrent
        workers see each other's choices and fan out instead of all picking the
        same idle key.
        """
        with self._lock:
            candidates: list[KeyState] = [k for k in self._keys if k.serves(model)]
            if not candidates:
                return None
            chosen: KeyState = min(candidates, key=lambda k: k.attempts)
            chosen.attempts += 1
            return chosen

    def _retire(self, key: KeyState, model: str) -> None:
        with self._lock:
            key.exhausted_models.add(model)
            key.failures += 1

    def _summary(self, model: str) -> str:
        with self._lock:
            return ", ".join(
                f"{k.label}: {k.attempts - k.failures} call(s)"
                + ("" if k.serves(model) else ", spent")
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
                    "exhausted": sorted(k.exhausted_models),
                }
                for k in self._keys
            ]
