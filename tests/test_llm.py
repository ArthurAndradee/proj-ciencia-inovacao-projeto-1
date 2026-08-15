from typing import Any

import pytest

from arc_experiment.llm import (
    Budget,
    BudgetExceeded,
    Completion,
    GeminiClient,
    Message,
    ScriptedClient,
)
from arc_experiment.ratelimit import PermanentAPIError, QuotaExhausted


def test_budget_tracks_usage_per_role() -> None:
    budget = Budget(limit=4)
    budget.spend("generator")
    budget.spend("critic")
    budget.spend("generator")
    assert budget.used == 3
    assert budget.remaining == 1
    assert budget.by_role == {"generator": 2, "critic": 1}


def test_budget_blocks_calls_beyond_the_limit() -> None:
    budget = Budget(limit=1)
    budget.spend("generator")
    assert not budget.can_afford()
    with pytest.raises(BudgetExceeded):
        budget.spend("critic")
    assert budget.used == 1


def test_budget_can_afford_multiple_calls() -> None:
    budget = Budget(limit=2)
    assert budget.can_afford(2)
    assert not budget.can_afford(3)


def test_scripted_client_returns_responses_in_order() -> None:
    client = ScriptedClient(responses=["first", "second"], default="fallback")
    messages: list[Message] = [Message(role="user", text="hi")]
    assert client.generate("m", "sys", messages).text == "first"
    assert client.generate("m", "sys", messages).text == "second"
    assert client.generate("m", "sys", messages).text == "fallback"
    assert len(client.calls) == 3


def test_completion_defaults_to_zero_tokens() -> None:
    completion = Completion(text="x")
    assert completion.input_tokens == 0 and completion.output_tokens == 0


class FakeResponse:
    def __init__(self, text: str, prompt_tokens: int = 11, output_tokens: int = 7) -> None:
        self.text: str = text
        self.usage_metadata: Any = type(
            "Usage",
            (),
            {"prompt_token_count": prompt_tokens, "candidates_token_count": output_tokens},
        )()


class FakeModels:
    """Replays a scripted sequence of responses and API errors."""

    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes: list[Any] = outcomes
        self.attempts: int = 0

    def generate_content(self, model: str, contents: Any, config: Any) -> Any:
        self.attempts += 1
        outcome: Any = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


PER_MINUTE_429: str = (
    "429 RESOURCE_EXHAUSTED. Quota exceeded for GenerateRequestsPerMinutePerProjectPerModel. "
    "[{'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '38s'}]"
)
PER_DAY_429: str = (
    "429 RESOURCE_EXHAUSTED. Quota exceeded for GenerateRequestsPerDayPerProjectPerModel"
)


def gemini_with(outcomes: list[Any], max_retries: int = 3) -> tuple[GeminiClient, list[float]]:
    """A GeminiClient whose transport is faked and whose sleeps are recorded."""
    slept: list[float] = []
    client = GeminiClient(
        api_key="fake-key", max_retries=max_retries, sleep=slept.append, rpm=0
    )
    client._client = type("FakeClient", (), {"models": FakeModels(outcomes)})()
    return client, slept


def ask(client: GeminiClient) -> Completion:
    return client.generate("gemini-2.5-flash", "sys", [Message(role="user", text="hi")])


def test_missing_api_key_is_rejected_early() -> None:
    with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
        GeminiClient(api_key="")


def test_successful_call_returns_text_and_token_usage() -> None:
    client, slept = gemini_with([FakeResponse("answer")])
    completion: Completion = ask(client)
    assert completion.text == "answer"
    assert (completion.input_tokens, completion.output_tokens) == (11, 7)
    assert slept == []


def test_per_minute_429_is_retried_using_the_server_delay() -> None:
    client, slept = gemini_with([Exception(PER_MINUTE_429), FakeResponse("answer")])
    assert ask(client).text == "answer"
    assert slept == [38.0]


def test_transient_5xx_uses_exponential_backoff() -> None:
    client, slept = gemini_with(
        [Exception("503 service unavailable"), Exception("503 again"), FakeResponse("ok")]
    )
    assert ask(client).text == "ok"
    assert slept == [4.0, 8.0]


def test_daily_quota_aborts_without_retrying() -> None:
    client, slept = gemini_with([Exception(PER_DAY_429), FakeResponse("never reached")])
    with pytest.raises(QuotaExhausted, match="daily quota"):
        ask(client)
    assert slept == []


def test_depleted_credits_abort_without_retrying() -> None:
    credits_429: str = (
        "429 RESOURCE_EXHAUSTED. Your prepayment credits are depleted. "
        "Please go to AI Studio to manage your project and billing."
    )
    client, slept = gemini_with([Exception(credits_429), FakeResponse("never reached")])
    with pytest.raises(QuotaExhausted, match="credits are depleted"):
        ask(client)
    assert slept == []


def test_permanent_error_aborts_without_retrying() -> None:
    client, slept = gemini_with(
        [Exception("400 INVALID_ARGUMENT: API key not valid"), FakeResponse("never reached")]
    )
    with pytest.raises(PermanentAPIError):
        ask(client)
    assert slept == []


def test_giving_up_after_max_retries() -> None:
    client, slept = gemini_with([Exception("503 down")] * 3, max_retries=3)
    with pytest.raises(RuntimeError, match="after 3 attempts"):
        ask(client)
    assert slept == [4.0, 8.0]
