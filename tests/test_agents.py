from arc_experiment import prompts
from arc_experiment.agents import Critic, Generator, Proposal, parse_proposal
from arc_experiment.dataset import Pair, Task
from arc_experiment.executor import RunResult
from arc_experiment.llm import Budget, ScriptedClient

ANSWER: str = (
    "## RULE\nTile the grid three times.\n\n"
    "## CODE\n```python\ndef transform(grid):\n    return grid\n```\n"
)

TASK: Task = Task(
    task_id="t1",
    train=[Pair([[1]], [[2]])],
    test=[Pair([[3]], [[4]])],
)


def test_parse_proposal_splits_sections() -> None:
    rule, code = parse_proposal(ANSWER)
    assert rule == "Tile the grid three times."
    assert code is not None and "def transform" in code


def test_parse_proposal_without_headers() -> None:
    rule, code = parse_proposal("just do it\n```python\ndef transform(g):\n    return g\n```")
    assert rule == "just do it"
    assert code is not None


def test_parse_proposal_without_code() -> None:
    rule, code = parse_proposal("## RULE\nno program this time")
    assert rule == "no program this time"
    assert code is None


def test_generator_spends_budget_and_keeps_history() -> None:
    budget = Budget(limit=3)
    generator = Generator(client=ScriptedClient([ANSWER, ANSWER]), model="m", budget=budget)
    first: Proposal = generator.propose("solve it")
    generator.propose("try again")
    assert budget.used == 2 and budget.by_role == {"generator": 2}
    assert first.code is not None
    assert [message.role for message in generator.history] == [
        "user",
        "model",
        "user",
        "model",
    ]


def test_generator_passes_its_temperature_to_the_client() -> None:
    client = ScriptedClient([ANSWER, ANSWER])
    Generator(client=client, model="m", budget=Budget(limit=1), temperature=0.8).propose("go")
    Generator(client=client, model="m", budget=Budget(limit=1)).propose("go")
    assert [call.temperature for call in client.calls] == [0.8, None]


def test_critic_is_stateless_and_sanitizes_feedback() -> None:
    budget = Budget(limit=2)
    client = ScriptedClient(["## CONTRADICTIONS\nthe target is\n0 7 7\n7 7 7"])
    critic = Critic(client=client, model="m", budget=budget)

    critique = critic.review("review this")
    assert critique.leaked and "0 7 7" not in critique.feedback
    assert "0 7 7" in critique.raw  # the raw answer is kept for the audit trail

    critic.review("review again")
    assert all(len(call.messages) == 1 for call in client.calls)
    assert budget.by_role == {"critic": 2}


def test_critic_prompt_contains_the_ground_truth_but_generator_prompt_does_not() -> None:
    empty_run = RunResult(ok=True, error=None, cases=[])
    critic_message: str = prompts.critic_request(TASK, "some rule", empty_run)
    generator_message: str = prompts.generator_initial(TASK)
    target: str = "TEST OUTPUT"
    assert target in critic_message
    assert target not in generator_message
    assert "3" in generator_message  # the test input is shown
