"""LLM client (Google AI Studio / Gemini) and API-call budget accounting."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from . import ratelimit


class BudgetExceeded(Exception):
    """Raised when a call would exceed the task's fixed API-call budget."""


@dataclass
class Budget:
    """API-call budget shared by every agent within a SINGLE task.

    Both conditions receive the same `limit`, which is what makes the comparison
    fair: the critic condition pays for the critic out of the generator's allowance.
    """

    limit: int
    used: int = 0
    by_role: dict[str, int] = field(default_factory=dict)

    @property
    def remaining(self) -> int:
        return self.limit - self.used

    def can_afford(self, calls: int = 1) -> bool:
        return self.remaining >= calls

    def spend(self, role: str, calls: int = 1) -> None:
        if not self.can_afford(calls):
            raise BudgetExceeded(f"budget exhausted ({self.used}/{self.limit})")
        self.used += calls
        self.by_role[role] = self.by_role.get(role, 0) + calls


@dataclass(frozen=True)
class Message:
    role: str  # "user" or "model"
    text: str


@dataclass(frozen=True)
class Completion:
    """One model answer, with the accounting the technical note reports.

    `thinking_tokens` is billed and counts against the output limit, but the
    API reports it apart from `output_tokens` — ignoring it would understate
    the cost of a reasoning model by an order of magnitude. `truncated` says
    the answer hit that limit, which otherwise looks like a model that simply
    failed to write code.
    """

    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    truncated: bool = False


class LLMClient(Protocol):
    """Minimal interface the agents depend on.

    `temperature` overrides the client default for a single call: the sampling
    condition needs a high one to produce diverse candidates while the critic
    condition stays low, and both run against the same client.
    """

    def generate(
        self,
        model: str,
        system: str,
        messages: list[Message],
        temperature: float | None = None,
    ) -> Completion: ...


class GeminiClient:
    """Google AI Studio client, tuned for free-tier quotas.

    Calls are spaced out to respect the per-minute cap, transient failures back
    off exponentially (or by the delay the server asks for), permanent failures
    raise immediately, and a spent daily quota aborts the run instead of burning
    retries task after task.
    """

    def __init__(
        self,
        api_key: str,
        temperature: float = 0.2,
        max_output_tokens: int = 8192,
        max_retries: int = 5,
        base_delay: float = 4.0,
        rpm: int = 0,
        timeout_s: float = 180.0,
        limiter: ratelimit.RateLimiter | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key:
            raise ValueError(
                "GOOGLE_API_KEY is missing. Copy .env.example to .env and fill in the key."
            )
        from google import genai  # imported lazily so tests stay offline

        # The SDK warns on every call that Chat.send_message would be better for
        # automatic function calling. We use no tools, so the advice is noise
        # that would repeat once per API call across a multi-day run.
        logging.getLogger("google_genai.models").setLevel(logging.ERROR)

        self._genai: Any = genai
        # Without an explicit timeout a dead connection blocks the socket read
        # forever: one stalled call froze a run for an hour with the process
        # alive and idle. A timeout turns that into a retryable failure.
        self._client: Any = genai.Client(
            api_key=api_key,
            http_options=genai.types.HttpOptions(timeout=int(timeout_s * 1000)),
        )
        self.temperature: float = temperature
        self.max_output_tokens: int = max_output_tokens
        self.max_retries: int = max_retries
        self.base_delay: float = base_delay
        self._sleep: Callable[[float], None] = sleep
        self._limiter: ratelimit.RateLimiter = limiter or ratelimit.RateLimiter(rpm, sleep=sleep)

    def generate(
        self,
        model: str,
        system: str,
        messages: list[Message],
        temperature: float | None = None,
    ) -> Completion:
        types: Any = self._genai.types
        contents: list[Any] = [
            types.Content(role=message.role, parts=[types.Part(text=message.text)])
            for message in messages
        ]
        config: Any = types.GenerateContentConfig(
            system_instruction=system,
            temperature=self.temperature if temperature is None else temperature,
            max_output_tokens=self.max_output_tokens,
        )

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            self._limiter.acquire()
            try:
                response: Any = self._client.models.generate_content(
                    model=model, contents=contents, config=config
                )
                usage: Any = getattr(response, "usage_metadata", None)
                candidates: Any = getattr(response, "candidates", None) or [None]
                finish: Any = getattr(candidates[0], "finish_reason", None)
                return Completion(
                    text=response.text or "",
                    input_tokens=int(getattr(usage, "prompt_token_count", 0) or 0),
                    output_tokens=int(getattr(usage, "candidates_token_count", 0) or 0),
                    thinking_tokens=int(getattr(usage, "thoughts_token_count", 0) or 0),
                    truncated=str(getattr(finish, "name", finish)) == "MAX_TOKENS",
                )
            except Exception as exc:
                if not ratelimit.is_retryable(exc):
                    raise ratelimit.PermanentAPIError(str(exc)) from exc
                last_error = exc
                if attempt == self.max_retries - 1:
                    break
                self._sleep(self._backoff(attempt, exc))

        if last_error is not None:
            reason: str | None = ratelimit.quota_exhaustion_reason(last_error)
            if reason is not None:
                raise ratelimit.QuotaExhausted(f"{model}: {reason}") from last_error
        raise RuntimeError(f"API call failed after {self.max_retries} attempts: {last_error}")

    MAX_BACKOFF_S: float = 300.0

    def _backoff(self, attempt: int, exc: BaseException) -> float:
        """Server-requested delay when offered, exponential backoff otherwise.

        Capped either way: a server free to name its own delay can park the run
        for an hour, and an unbounded exponential reaches the same place on its
        own. Past a few minutes, failing and resuming beats waiting.
        """
        requested: float | None = ratelimit.retry_delay(exc)
        exponential: float = self.base_delay * (2**attempt)
        chosen: float = max(requested, 1.0) if requested is not None else exponential
        return min(chosen, self.MAX_BACKOFF_S)


@dataclass(frozen=True)
class ScriptedCall:
    """One recorded request, so tests can assert on what the agents sent."""

    model: str
    system: str
    messages: list[Message]
    temperature: float | None


class ScriptedClient:
    """Fake client for tests and dry runs; performs no network requests."""

    def __init__(self, responses: list[str] | None = None, default: str = "") -> None:
        self.responses: list[str] = list(responses or [])
        self.default: str = default
        self.calls: list[ScriptedCall] = []

    def generate(
        self,
        model: str,
        system: str,
        messages: list[Message],
        temperature: float | None = None,
    ) -> Completion:
        self.calls.append(ScriptedCall(model, system, list(messages), temperature))
        text: str = self.responses.pop(0) if self.responses else self.default
        return Completion(text=text)
