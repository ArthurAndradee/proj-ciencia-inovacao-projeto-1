import pytest

from arc_experiment.llm import Budget, BudgetExceeded, Completion, Message, ScriptedClient


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
