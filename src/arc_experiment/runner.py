"""The two experimental conditions and the per-task solving loop.

Both spend the same fixed budget of API calls; what differs is how:

* SAMPLING — N independent candidates, no feedback, no history (diversify);
* CRITIC   — generator revised by an oracle critic, which spends from the
  SAME budget, so each revision round costs two calls (iterate).

The stopping criterion is identical in both: a candidate is accepted when it
reproduces every training pair. The test-pair ground truth is visible to the
critic only, and never selects the answer.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from . import prompts
from .agents import Critic, Critique, Generator, Proposal
from .dataset import Task
from .executor import RunResult, run_code
from .llm import Budget, BudgetExceeded, LLMClient

NO_CODE_FEEDBACK = (
    "Your previous answer contained no usable Python block. Answer again with "
    f"both sections ({prompts.RULE_HEADER} and {prompts.CODE_HEADER})."
)


class Condition(str, Enum):
    SAMPLING = "sampling"
    CRITIC = "critic"
    CRITIC_NO_ORACLE = "critic_no_oracle"
    CRITIC_CEGIS = "critic_cegis"


@dataclass(frozen=True)
class CriticSpec:
    """Everything that varies between critic conditions; the loop stays generic."""

    system_prompt: str
    request_builder: Callable[[Task, str, str, RunResult], str]
    prefer_latest: bool = True


CRITIC_SPECS: dict[Condition, CriticSpec] = {
    Condition.CRITIC: CriticSpec(prompts.CRITIC_SYSTEM, prompts.critic_request),
    Condition.CRITIC_NO_ORACLE: CriticSpec(
        prompts.CRITIC_NO_ORACLE_SYSTEM, prompts.critic_request_no_oracle
    ),
    Condition.CRITIC_CEGIS: CriticSpec(
        prompts.CRITIC_CEGIS_SYSTEM, prompts.critic_request_cegis
    ),
}


class StopReason(str, Enum):
    TRAIN_CONSISTENT = "train_consistent"
    BUDGET_EXHAUSTED = "budget_exhausted"
    API_ERROR = "api_error"


@dataclass
class IterationRecord:
    index: int
    rule: str
    code: str | None
    executed: bool
    exec_error: str | None
    train_correct: int
    train_total: int
    critic_feedback: str | None = None
    critic_raw: str | None = None
    leak_violations: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    truncated: bool = False


@dataclass
class TaskOutcome:
    """Everything needed to audit one task under one condition."""

    task_id: str
    condition: str
    solved: bool
    train_consistent: bool
    calls_used: int
    calls_by_role: dict[str, int]
    iterations: list[IterationRecord]
    final_code: str | None
    final_rule: str | None
    stop_reason: str
    leak_events: int
    input_tokens: int
    output_tokens: int
    thinking_tokens: int = 0
    truncated_answers: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class _Candidate:
    """Best program so far, chosen without ever looking at the test output."""

    code: str
    rule: str
    train_correct: int
    iteration: int


def _better(new: _Candidate, current: _Candidate | None, prefer_latest: bool) -> bool:
    """Pick by training-pair consistency; `prefer_latest` decides the ties.

    Under guided revision later iterations incorporate feedback, so they win
    ties. Under independent sampling there is no progression — the seventh
    sample is not a priori better than the first — so the first one keeps the
    slot, and drawing more candidates never shifts the choice on its own.
    """
    if current is None:
        return True
    if prefer_latest:
        return new.train_correct >= current.train_correct
    return new.train_correct > current.train_correct


def solve_task(
    task: Task,
    condition: Condition,
    client: LLMClient,
    generator_model: str,
    critic_model: str,
    budget_calls: int,
    exec_timeout_s: float = 10.0,
    exec_memory_mb: int = 1024,
    temperature: float | None = None,
) -> TaskOutcome:
    """Run one task under one condition within a fixed API-call budget."""
    budget = Budget(limit=budget_calls)
    sampling: bool = condition is Condition.SAMPLING
    spec: CriticSpec | None = CRITIC_SPECS.get(condition)
    generator = Generator(
        client=client, model=generator_model, budget=budget, temperature=temperature
    )
    critic = Critic(
        client=client,
        model=critic_model,
        budget=budget,
        system=spec.system_prompt if spec is not None else prompts.CRITIC_SYSTEM,
    )

    iterations: list[IterationRecord] = []
    best: _Candidate | None = None
    message: str = prompts.generator_initial(task)
    stop_reason: StopReason = StopReason.BUDGET_EXHAUSTED
    error: str | None = None

    try:
        while budget.can_afford(1):
            if sampling:
                # Every sample is a fresh conversation: no history, same prompt.
                # Only the budget is shared, so the strategy spends exactly what
                # the other one does.
                generator = Generator(
                    client=client,
                    model=generator_model,
                    budget=budget,
                    temperature=temperature,
                )
            proposal: Proposal = generator.propose(message)
            record = IterationRecord(
                index=len(iterations) + 1,
                rule=proposal.rule,
                code=proposal.code,
                executed=False,
                exec_error=None,
                train_correct=0,
                train_total=len(task.train),
                input_tokens=proposal.input_tokens,
                output_tokens=proposal.output_tokens,
                thinking_tokens=proposal.thinking_tokens,
                truncated=proposal.truncated,
            )

            if proposal.code is None:
                record.exec_error = "no code block in the answer"
                iterations.append(record)
                if not sampling:
                    message = NO_CODE_FEEDBACK
                continue

            result: RunResult = run_code(
                proposal.code, task.train, timeout_s=exec_timeout_s, memory_mb=exec_memory_mb
            )
            record.executed = result.ok
            record.exec_error = result.error
            record.train_correct = result.n_correct
            iterations.append(record)

            candidate = _Candidate(
                code=proposal.code,
                rule=proposal.rule,
                train_correct=result.n_correct,
                iteration=record.index,
            )
            prefer_latest: bool = spec.prefer_latest if spec is not None else False
            if _better(candidate, best, prefer_latest=prefer_latest):
                best = candidate

            if result.all_correct:
                stop_reason = StopReason.TRAIN_CONSISTENT
                break

            if sampling:
                # No feedback channel: the next sample sees the same prompt.
                continue

            # Only critique when a revision round can still be paid for;
            # otherwise the budget would end on feedback nobody can use.
            if not budget.can_afford(2):
                break
            assert spec is not None  # only critic conditions reach this branch
            critique: Critique = critic.review(
                spec.request_builder(task, proposal.rule, proposal.code, result)
            )
            record.critic_feedback = critique.feedback
            record.critic_raw = critique.raw
            record.leak_violations = critique.violations
            record.input_tokens += critique.input_tokens
            record.output_tokens += critique.output_tokens
            record.thinking_tokens += critique.thinking_tokens
            message = prompts.generator_revision(critique.feedback, result)
    except BudgetExceeded:
        stop_reason = StopReason.BUDGET_EXHAUSTED
    except RuntimeError as exc:  # API failure after retries: keep the run alive
        stop_reason = StopReason.API_ERROR
        error = str(exc)

    solved: bool = False
    if best is not None:
        test_run: RunResult = run_code(
            best.code, [task.test_pair], timeout_s=exec_timeout_s, memory_mb=exec_memory_mb
        )
        solved = test_run.all_correct

    return TaskOutcome(
        task_id=task.task_id,
        condition=condition.value,
        solved=solved,
        train_consistent=stop_reason is StopReason.TRAIN_CONSISTENT,
        calls_used=budget.used,
        calls_by_role=dict(budget.by_role),
        iterations=iterations,
        final_code=best.code if best else None,
        final_rule=best.rule if best else None,
        stop_reason=stop_reason.value,
        leak_events=sum(len(record.leak_violations) for record in iterations),
        input_tokens=sum(record.input_tokens for record in iterations),
        output_tokens=sum(record.output_tokens for record in iterations),
        thinking_tokens=sum(record.thinking_tokens for record in iterations),
        truncated_answers=sum(1 for record in iterations if record.truncated),
        error=error,
    )
