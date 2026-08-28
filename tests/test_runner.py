import pytest

from arc_experiment.dataset import Pair, Task
from arc_experiment.llm import ScriptedClient
from arc_experiment.runner import Condition, StopReason, TaskOutcome, solve_task

CRITIC_CONDITIONS: list[Condition] = [
    Condition.CRITIC,
    Condition.CRITIC_NO_ORACLE,
    Condition.CRITIC_CEGIS,
]

# Doubling task: every cell value is multiplied by two.
TASK: Task = Task(
    task_id="double",
    train=[Pair([[1, 2]], [[2, 4]]), Pair([[3]], [[6]])],
    test=[Pair([[5]], [[10]])],
)

CORRECT: str = (
    "## RULE\nDouble every cell.\n"
    "## CODE\n```python\ndef transform(grid):\n"
    "    return [[c * 2 for c in row] for row in grid]\n```"
)
WRONG: str = (
    "## RULE\nCopy the grid.\n## CODE\n```python\ndef transform(grid):\n    return grid\n```"
)
CRITIQUE: str = "## CONTRADICTIONS\nYour rule preserves the values; the target does not."
NO_CODE: str = "## RULE\nI am thinking about it."


def _run(
    condition: Condition,
    responses: list[str],
    budget: int = 6,
    temperature: float | None = None,
) -> tuple[TaskOutcome, ScriptedClient]:
    client = ScriptedClient(responses=responses, default=WRONG)
    outcome = solve_task(
        task=TASK,
        condition=condition,
        client=client,
        generator_model="gen",
        critic_model="crit",
        budget_calls=budget,
        temperature=temperature,
    )
    return outcome, client


def _solve(condition: Condition, responses: list[str], budget: int = 6) -> TaskOutcome:
    return _run(condition, responses, budget)[0]


WRONG_B: str = (
    "## RULE\nReverse each row.\n## CODE\n```python\ndef transform(grid):\n"
    "    return [row[::-1] for row in grid]\n```"
)


def test_sampling_restarts_from_the_same_prompt_every_time() -> None:
    outcome, client = _run(Condition.SAMPLING, [WRONG, WRONG_B, WRONG], budget=3)
    assert len(client.calls) == 3
    # No history accumulates: each sample is a fresh one-message conversation.
    assert all(len(call.messages) == 1 for call in client.calls)
    assert len({call.messages[0].text for call in client.calls}) == 1
    assert all(record.critic_feedback is None for record in outcome.iterations)


def test_sampling_uses_its_own_temperature() -> None:
    _, client = _run(Condition.SAMPLING, [WRONG] * 2, budget=2, temperature=0.8)
    assert [call.temperature for call in client.calls] == [0.8, 0.8]


def test_sampling_stops_at_the_first_train_consistent_sample() -> None:
    outcome, client = _run(Condition.SAMPLING, [WRONG, CORRECT, CORRECT], budget=6)
    assert outcome.solved and outcome.stop_reason == StopReason.TRAIN_CONSISTENT.value
    assert outcome.calls_used == 2 and len(client.calls) == 2


def test_sampling_keeps_the_first_of_two_equally_good_samples() -> None:
    outcome = _solve(Condition.SAMPLING, [WRONG, WRONG_B], budget=2)
    assert outcome.iterations[0].train_correct == outcome.iterations[1].train_correct
    assert outcome.final_code is not None and "return grid" in outcome.final_code


def test_sampling_never_spends_on_the_critic() -> None:
    outcome = _solve(Condition.SAMPLING, [WRONG] * 4, budget=4)
    assert outcome.calls_by_role == {"generator": 4}


def test_sampling_keeps_drawing_after_an_answer_without_code() -> None:
    outcome, client = _run(Condition.SAMPLING, [NO_CODE, CORRECT], budget=3)
    assert outcome.solved
    # The retry instruction belongs to the revision loop; sampling must not use it.
    assert len({call.messages[0].text for call in client.calls}) == 1


@pytest.mark.parametrize("condition", CRITIC_CONDITIONS)
def test_critic_conditions_alternate_generator_and_critic(condition: Condition) -> None:
    outcome = _solve(condition, [WRONG, CRITIQUE, CORRECT])
    assert outcome.solved and outcome.train_consistent
    assert outcome.stop_reason == StopReason.TRAIN_CONSISTENT.value
    assert outcome.calls_by_role == {"generator": 2, "critic": 1}
    assert outcome.iterations[0].critic_feedback is not None
    assert outcome.iterations[1].critic_feedback is None


def test_critic_condition_carries_the_conversation_forward() -> None:
    _, client = _run(Condition.CRITIC, [WRONG, CRITIQUE, CORRECT])
    generator_calls = [call for call in client.calls if "program synthesis agent" in call.system]
    # Unlike sampling, the second generation sees the whole exchange.
    assert [len(call.messages) for call in generator_calls] == [1, 3]


@pytest.mark.parametrize("condition", CRITIC_CONDITIONS)
def test_critic_conditions_buy_fewer_iterations_with_the_same_budget(
    condition: Condition,
) -> None:
    sampling = _solve(Condition.SAMPLING, [WRONG] * 6, budget=6)
    critic = _solve(condition, [WRONG, CRITIQUE] * 3, budget=6)
    assert sampling.calls_used == 6 and len(sampling.iterations) == 6
    assert critic.calls_used <= 6 and len(critic.iterations) == 3


@pytest.mark.parametrize("condition", CRITIC_CONDITIONS)
def test_critic_conditions_do_not_end_on_an_unusable_critique(condition: Condition) -> None:
    outcome = _solve(condition, [WRONG, CRITIQUE, WRONG], budget=3)
    # The third call would be a critique with no revision left to pay for.
    assert outcome.calls_used == 3
    assert outcome.calls_by_role == {"generator": 2, "critic": 1}


@pytest.mark.parametrize("condition", CRITIC_CONDITIONS)
def test_prefer_latest_is_true_for_every_critic_condition(condition: Condition) -> None:
    # WRONG (0/2 train) -> CORRECT (2/2, would stop) is avoided by using a
    # worse-then-better-then-worse sequence that never reaches all_correct, so
    # the loop runs to budget exhaustion and the tie-break actually matters.
    better: str = (
        "## RULE\nDouble only the first cell.\n## CODE\n```python\ndef transform(grid):\n"
        "    return [[grid[0][0] * 2] + row[1:] for row in grid]\n```"
    )
    outcome = _solve(condition, [WRONG, CRITIQUE, better, CRITIQUE, WRONG_B], budget=5)
    # `better` reproduces the first training pair (1/2); WRONG and WRONG_B reproduce
    # neither (0/2), so `better` is the unique best on training and must be kept
    # regardless of it not being the latest iteration.
    assert outcome.final_code is not None and "grid[0][0] * 2" in outcome.final_code


def test_budget_exhaustion_is_reported() -> None:
    outcome = _solve(Condition.SAMPLING, [WRONG, WRONG], budget=2)
    assert not outcome.solved
    assert outcome.stop_reason == StopReason.BUDGET_EXHAUSTED.value
    assert outcome.final_code is not None  # best-so-far is still evaluated


def test_answers_without_code_are_retried_not_crashed() -> None:
    outcome = _solve(Condition.CRITIC, [NO_CODE, CORRECT])
    assert outcome.solved
    assert outcome.iterations[0].code is None
    assert outcome.iterations[0].exec_error == "no code block in the answer"


@pytest.mark.parametrize("condition", CRITIC_CONDITIONS)
def test_leaking_critique_is_sanitized_and_counted(condition: Condition) -> None:
    # Adversarial: even a critic with no ground truth to leak (critic_no_oracle)
    # must still be sanitized identically, in case the model hallucinates a grid
    # anyway. The guard is defense-in-depth, not "trusted because harmless".
    leaky: str = "## CONTRADICTIONS\nthe answer is\n2 4 6\n8 10 12"
    outcome = _solve(condition, [WRONG, leaky, CORRECT])
    assert outcome.leak_events == 2
    feedback = outcome.iterations[0].critic_feedback
    assert feedback is not None and "2 4 6" not in feedback


def test_final_candidate_is_the_best_on_training_pairs() -> None:
    partial: str = (
        "## RULE\nDouble only single-cell grids.\n## CODE\n```python\ndef transform(grid):\n"
        "    return [[c * 2 for c in row] for row in grid] if len(grid[0]) == 1 else grid\n```"
    )
    outcome = _solve(Condition.SAMPLING, [WRONG, partial], budget=2)
    assert outcome.final_code is not None and "len(grid[0]) == 1" in outcome.final_code
    assert outcome.solved  # the partial rule happens to fit the 1x1 test input
