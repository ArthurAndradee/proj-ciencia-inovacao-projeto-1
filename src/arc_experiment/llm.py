"""LLM client (Google AI Studio / Gemini) and API-call budget accounting."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol


class BudgetExceeded(Exception):
    """Raised when a call would exceed the task's fixed API-call budget."""


@dataclass
class Budget:
    """API-call budget shared by every agent within a SINGLE task.

    Both conditions receive the same `limit`, which is what makes the comparison
    fair: the intervention pays for the critic out of the generator's allowance.
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
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


class LLMClient(Protocol):
    """Minimal interface the agents depend on."""

    def generate(self, model: str, system: str, messages: list[Message]) -> Completion: ...


class GeminiClient:
    """Google AI Studio client with exponential backoff on transient failures."""

    def __init__(
        self,
        api_key: str,
        temperature: float = 0.2,
        max_output_tokens: int = 8192,
        max_retries: int = 4,
        base_delay: float = 4.0,
    ) -> None:
        if not api_key:
            raise ValueError(
                "GOOGLE_API_KEY is missing. Copy .env.example to .env and fill in the key."
            )
        from google import genai  # imported lazily so tests stay offline

        self._genai: Any = genai
        self._client: Any = genai.Client(api_key=api_key)
        self.temperature: float = temperature
        self.max_output_tokens: int = max_output_tokens
        self.max_retries: int = max_retries
        self.base_delay: float = base_delay

    def generate(self, model: str, system: str, messages: list[Message]) -> Completion:
        types: Any = self._genai.types
        contents: list[Any] = [
            types.Content(role=message.role, parts=[types.Part(text=message.text)])
            for message in messages
        ]
        config: Any = types.GenerateContentConfig(
            system_instruction=system,
            temperature=self.temperature,
            max_output_tokens=self.max_output_tokens,
        )

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                response: Any = self._client.models.generate_content(
                    model=model, contents=contents, config=config
                )
                usage: Any = getattr(response, "usage_metadata", None)
                return Completion(
                    text=response.text or "",
                    input_tokens=int(getattr(usage, "prompt_token_count", 0) or 0),
                    output_tokens=int(getattr(usage, "candidates_token_count", 0) or 0),
                )
            except Exception as exc:  # network, 429, 5xx
                last_error = exc
                if attempt == self.max_retries - 1:
                    break
                time.sleep(self.base_delay * (2**attempt))
        raise RuntimeError(f"API call failed after {self.max_retries} attempts: {last_error}")


class ScriptedClient:
    """Fake client for tests and dry runs; performs no network requests."""

    def __init__(self, responses: list[str] | None = None, default: str = "") -> None:
        self.responses: list[str] = list(responses or [])
        self.default: str = default
        self.calls: list[tuple[str, str, list[Message]]] = []

    def generate(self, model: str, system: str, messages: list[Message]) -> Completion:
        self.calls.append((model, system, list(messages)))
        text: str = self.responses.pop(0) if self.responses else self.default
        return Completion(text=text)
