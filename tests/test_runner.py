from arc_experiment.dataset import Pair, Task
from arc_experiment.llm import ScriptedClient
from arc_experiment.runner import Condition, StopReason, TaskOutcome, solve_task

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


def _solve(condition: Condition, responses: list[str], budget: int = 6) -> TaskOutcome:
    client = ScriptedClient(responses=responses, default=WRONG)
    return solve_task(
        task=TASK,
        condition=condition,
        client=client,
        generator_model="gen",
        critic_model="crit",
        budget_calls=budget,
    )


def test_baseline_stops_when_training_pairs_are_reproduced() -> None:
    outcome = _solve(Condition.BASELINE, [CORRECT])
    assert outcome.solved and outcome.train_consistent
    assert outcome.stop_reason == StopReason.TRAIN_CONSISTENT.value
    assert outcome.calls_used == 1
    assert outcome.calls_by_role == {"generator": 1}


def test_baseline_self_debugs_until_it_succeeds() -> None:
    outcome = _solve(Condition.BASELINE, [WRONG, WRONG, CORRECT])
    assert outcome.solved
    assert outcome.calls_used == 3 and len(outcome.iterations) == 3
    assert outcome.iterations[0].train_correct == 0


def test_baseline_never_spends_on_the_critic() -> None:
    outcome = _solve(Condition.BASELINE, [WRONG, WRONG, WRONG], budget=3)
    assert outcome.calls_by_role == {"generator": 3}
    assert all(record.critic_feedback is None for record in outcome.iterations)


def test_intervention_alternates_generator_and_critic() -> None:
    outcome = _solve(Condition.INTERVENTION, [WRONG, CRITIQUE, CORRECT])
    assert outcome.solved
    assert outcome.calls_by_role == {"generator": 2, "critic": 1}
    assert outcome.iterations[0].critic_feedback is not None
    assert outcome.iterations[1].critic_feedback is None


def test_intervention_gets_fewer_iterations_under_the_same_budget() -> None:
    baseline = _solve(Condition.BASELINE, [WRONG] * 6, budget=6)
    intervention = _solve(Condition.INTERVENTION, [WRONG, CRITIQUE] * 3, budget=6)
    assert baseline.calls_used == 6 and len(baseline.iterations) == 6
    assert intervention.calls_used <= 6 and len(intervention.iterations) == 3


def test_intervention_does_not_end_on_an_unusable_critique() -> None:
    outcome = _solve(Condition.INTERVENTION, [WRONG, CRITIQUE, WRONG], budget=3)
    # The third call would be a critique with no revision left to pay for.
    assert outcome.calls_used == 3
    assert outcome.calls_by_role == {"generator": 2, "critic": 1}


def test_budget_exhaustion_is_reported() -> None:
    outcome = _solve(Condition.BASELINE, [WRONG, WRONG], budget=2)
    assert not outcome.solved
    assert outcome.stop_reason == StopReason.BUDGET_EXHAUSTED.value
    assert outcome.final_code is not None  # best-so-far is still evaluated


def test_answers_without_code_are_retried_not_crashed() -> None:
    outcome = _solve(Condition.BASELINE, [NO_CODE, CORRECT])
    assert outcome.solved
    assert outcome.iterations[0].code is None
    assert outcome.iterations[0].exec_error == "no code block in the answer"


def test_leaking_critique_is_sanitized_and_counted() -> None:
    leaky: str = "## CONTRADICTIONS\nthe answer is\n2 4 6\n8 10 12"
    outcome = _solve(Condition.INTERVENTION, [WRONG, leaky, CORRECT])
    assert outcome.leak_events == 2
    feedback = outcome.iterations[0].critic_feedback
    assert feedback is not None and "2 4 6" not in feedback


def test_final_candidate_is_the_best_on_training_pairs() -> None:
    partial: str = (
        "## RULE\nDouble only single-cell grids.\n## CODE\n```python\ndef transform(grid):\n"
        "    return [[c * 2 for c in row] for row in grid] if len(grid[0]) == 1 else grid\n```"
    )
    outcome = _solve(Condition.BASELINE, [WRONG, partial], budget=2)
    assert outcome.final_code is not None and "len(grid[0]) == 1" in outcome.final_code
    assert outcome.solved  # the partial rule happens to fit the 1x1 test input
