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


def test_critic_condition_alternates_generator_and_critic() -> None:
    outcome = _solve(Condition.CRITIC, [WRONG, CRITIQUE, CORRECT])
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


def test_critic_condition_buys_fewer_iterations_with_the_same_budget() -> None:
    sampling = _solve(Condition.SAMPLING, [WRONG] * 6, budget=6)
    critic = _solve(Condition.CRITIC, [WRONG, CRITIQUE] * 3, budget=6)
    assert sampling.calls_used == 6 and len(sampling.iterations) == 6
    assert critic.calls_used <= 6 and len(critic.iterations) == 3


def test_critic_condition_does_not_end_on_an_unusable_critique() -> None:
    outcome = _solve(Condition.CRITIC, [WRONG, CRITIQUE, WRONG], budget=3)
    # The third call would be a critique with no revision left to pay for.
    assert outcome.calls_used == 3
    assert outcome.calls_by_role == {"generator": 2, "critic": 1}


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


def test_leaking_critique_is_sanitized_and_counted() -> None:
    leaky: str = "## CONTRADICTIONS\nthe answer is\n2 4 6\n8 10 12"
    outcome = _solve(Condition.CRITIC, [WRONG, leaky, CORRECT])
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


# --- injection arms -------------------------------------------------------
#
# The doubling task fails both training pairs under WRONG, so a counterexample
# block always has something to disclose. `client.calls[2]` is the revision
# call: 0 is the first generation, 1 is the critique.


def _revision_message(client: ScriptedClient) -> str:
    """The user text the generator received on its second turn."""
    return client.calls[2].messages[-1].text


def test_plain_critic_discloses_no_grid() -> None:
    _, client = _run(Condition.CRITIC, [WRONG, CRITIQUE, CORRECT])
    message: str = _revision_message(client)
    assert "EXPECTED OUTPUT" not in message
    assert "TEST OUTPUT" not in message


def test_counterexample_discloses_the_missed_training_targets() -> None:
    _, client = _run(Condition.COUNTEREXAMPLE, [WRONG, CRITIQUE, CORRECT])
    message: str = _revision_message(client)
    assert "TRAINING EXAMPLE 1 — EXPECTED OUTPUT" in message
    assert "TRAINING EXAMPLE 2 — EXPECTED OUTPUT" in message
    # The targets themselves, as rendered grids: 1x2 "2 4" and 1x1 "6".
    assert "1x2\n2 4" in message
    assert "1x1\n6" in message


def test_counterexample_withholds_the_test_target() -> None:
    _, client = _run(Condition.COUNTEREXAMPLE, [WRONG, CRITIQUE, CORRECT])
    message: str = _revision_message(client)
    assert "TEST OUTPUT" not in message
    assert "10" not in message


def test_oracle_discloses_the_test_target() -> None:
    _, client = _run(Condition.ORACLE, [WRONG, CRITIQUE, CORRECT])
    message: str = _revision_message(client)
    assert "TEST OUTPUT" in message
    assert "1x1\n10" in message
    # The ceiling arm is the counterexample arm plus the test pair, not instead.
    assert "TRAINING EXAMPLE 1 — EXPECTED OUTPUT" in message


def test_correct_training_pairs_are_not_restated() -> None:
    """Only the misses are disclosed: the hits are already in the history."""
    partial: str = (
        "## RULE\nDouble single-cell grids only.\n## CODE\n```python\ndef transform(grid):\n"
        "    return [[c * 2 for c in row] for row in grid] if len(grid[0]) == 1 else grid\n```"
    )
    outcome, client = _run(Condition.COUNTEREXAMPLE, [partial, CRITIQUE, CORRECT])
    message: str = _revision_message(client)
    assert "TRAINING EXAMPLE 1 — EXPECTED OUTPUT" in message
    assert "TRAINING EXAMPLE 2 — EXPECTED OUTPUT" not in message
    assert outcome.iterations[0].injected_train == 1


def test_injection_is_recorded_per_iteration() -> None:
    counterexample = _solve(Condition.COUNTEREXAMPLE, [WRONG, CRITIQUE, CORRECT])
    oracle = _solve(Condition.ORACLE, [WRONG, CRITIQUE, CORRECT])
    critic = _solve(Condition.CRITIC, [WRONG, CRITIQUE, CORRECT])

    assert counterexample.iterations[0].injected_train == 2
    assert counterexample.iterations[0].injected_test is False
    assert oracle.iterations[0].injected_test is True
    assert critic.iterations[0].injected_train == 0
    assert critic.iterations[0].injected_test is False


def test_injection_does_not_count_as_a_leak() -> None:
    """`leak_events` stays the critic's own doing; disclosure is booked apart."""
    outcome = _solve(Condition.ORACLE, [WRONG, CRITIQUE, CORRECT])
    assert outcome.leak_events == 0


def test_injection_arms_cost_the_same_as_the_critic() -> None:
    critic = _solve(Condition.CRITIC, [WRONG, CRITIQUE] * 3, budget=6)
    oracle = _solve(Condition.ORACLE, [WRONG, CRITIQUE] * 3, budget=6)
    assert oracle.calls_by_role == critic.calls_by_role
    assert len(oracle.iterations) == len(critic.iterations)


def test_injection_arms_carry_the_conversation_forward() -> None:
    """Like the critic arm and unlike sampling: history accumulates."""
    _, client = _run(Condition.ORACLE, [WRONG, CRITIQUE, CORRECT])
    assert len(client.calls[2].messages) > len(client.calls[0].messages)
