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
    def __init__(
        self,
        text: str,
        prompt_tokens: int = 11,
        output_tokens: int = 7,
        thinking_tokens: int = 0,
        finish_reason: str = "STOP",
    ) -> None:
        self.text: str = text
        self.usage_metadata: Any = type(
            "Usage",
            (),
            {
                "prompt_token_count": prompt_tokens,
                "candidates_token_count": output_tokens,
                "thoughts_token_count": thinking_tokens,
            },
        )()
        self.candidates: list[Any] = [type("Candidate", (), {"finish_reason": finish_reason})()]


class FakeModels:
    """Replays a scripted sequence of responses and API errors."""

    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes: list[Any] = outcomes
        self.attempts: int = 0
        self.configs: list[Any] = []

    def generate_content(self, model: str, contents: Any, config: Any) -> Any:
        self.attempts += 1
        self.configs.append(config)
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


def test_thinking_tokens_are_recorded_apart_from_the_answer() -> None:
    client, _ = gemini_with([FakeResponse("answer", output_tokens=366, thinking_tokens=5905)])
    completion: Completion = ask(client)
    # Reporting only candidates_token_count would understate the cost 16-fold.
    assert (completion.output_tokens, completion.thinking_tokens) == (366, 5905)
    assert not completion.truncated


def test_an_answer_cut_off_by_the_token_limit_is_flagged() -> None:
    client, _ = gemini_with([FakeResponse("half a pro", finish_reason="MAX_TOKENS")])
    # Otherwise a truncated answer just looks like a model that wrote no code.
    assert ask(client).truncated


def test_temperature_defaults_to_the_client_setting_and_can_be_overridden() -> None:
    client, _ = gemini_with([FakeResponse("a"), FakeResponse("b")])
    messages: list[Message] = [Message(role="user", text="hi")]
    client.generate("m", "sys", messages)
    client.generate("m", "sys", messages, temperature=0.8)
    assert [config.temperature for config in client._client.models.configs] == [0.2, 0.8]


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


def test_a_daily_quota_429_is_retried_first() -> None:
    # Observed transient in practice, despite the wording.
    client, slept = gemini_with([Exception(PER_DAY_429), FakeResponse("answer")])
    assert ask(client).text == "answer"
    assert slept == [4.0]


def test_persistent_daily_quota_stops_the_run() -> None:
    client, _ = gemini_with([Exception(PER_DAY_429)] * 3, max_retries=3)
    with pytest.raises(QuotaExhausted, match="daily quota"):
        ask(client)


CREDITS_429: str = (
    "429 RESOURCE_EXHAUSTED. Your prepayment credits are depleted. "
    "Please go to AI Studio to manage your project and billing."
)


def test_a_credits_429_is_retried_and_can_recover() -> None:
    client, slept = gemini_with([Exception(CREDITS_429), FakeResponse("answer")])
    # It reads as fatal but is often transient; aborting on sight killed a run.
    assert ask(client).text == "answer"
    assert slept == [4.0]


def test_persistent_credits_429_stops_the_run_with_the_billing_diagnosis() -> None:
    client, _ = gemini_with([Exception(CREDITS_429)] * 3, max_retries=3)
    with pytest.raises(QuotaExhausted, match="billing"):
        ask(client)


def test_permanent_error_aborts_without_retrying() -> None:
    client, slept = gemini_with(
        [Exception("400 INVALID_ARGUMENT: API key not valid"), FakeResponse("never reached")]
    )
    with pytest.raises(PermanentAPIError):
        ask(client)
    assert slept == []


def test_backoff_is_capped_however_long_the_server_asks() -> None:
    hour_long: str = (
        "429 RESOURCE_EXHAUSTED. [{'@type': 'type.googleapis.com/google.rpc.RetryInfo', "
        "'retryDelay': '3600s'}]"
    )
    client, slept = gemini_with([Exception(hour_long), FakeResponse("answer")])
    # A server free to name its own delay could otherwise park the run for an hour.
    assert ask(client).text == "answer"
    assert slept == [GeminiClient.MAX_BACKOFF_S]


def test_backoff_cap_also_bounds_the_exponential() -> None:
    client, slept = gemini_with([Exception("503 down")] * 12, max_retries=12)
    with pytest.raises(RuntimeError):
        ask(client)
    assert max(slept) == GeminiClient.MAX_BACKOFF_S


def test_giving_up_after_max_retries() -> None:
    # A non-429 failure keeps the generic error: the run continues to the next
    # task instead of stopping, since nothing suggests the key is capped.
    client, slept = gemini_with([Exception("503 down")] * 3, max_retries=3)
    with pytest.raises(RuntimeError, match="after 3 attempts"):
        ask(client)
    assert slept == [4.0, 8.0]
