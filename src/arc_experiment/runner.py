"""The two experimental conditions and the per-task solving loop.

Both conditions share everything except the feedback channel:

* BASELINE      — generator + execution feedback on the training pairs (self-debugging);
* INTERVENTION  — generator + oracle critic, which spends from the SAME budget.

The stopping criterion is identical in both: a candidate is accepted when it
reproduces every training pair. The test-pair ground truth is visible to the
critic only, and never selects the answer.
"""

from __future__ import annotations

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
    BASELINE = "baseline"
    INTERVENTION = "intervention"


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


def _better(new: _Candidate, current: _Candidate | None) -> bool:
    """Later iterations win ties: the generator is expected to improve."""
    if current is None:
        return True
    return new.train_correct >= current.train_correct


def solve_task(
    task: Task,
    condition: Condition,
    client: LLMClient,
    generator_model: str,
    critic_model: str,
    budget_calls: int,
    exec_timeout_s: float = 10.0,
    exec_memory_mb: int = 1024,
) -> TaskOutcome:
    """Run one task under one condition within a fixed API-call budget."""
    budget = Budget(limit=budget_calls)
    generator = Generator(client=client, model=generator_model, budget=budget)
    critic = Critic(client=client, model=critic_model, budget=budget)

    iterations: list[IterationRecord] = []
    best: _Candidate | None = None
    message: str = prompts.generator_initial(task)
    stop_reason: StopReason = StopReason.BUDGET_EXHAUSTED
    error: str | None = None

    try:
        while budget.can_afford(1):
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
            )

            if proposal.code is None:
                record.exec_error = "no code block in the answer"
                iterations.append(record)
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
            if _better(candidate, best):
                best = candidate

            if result.all_correct:
                stop_reason = StopReason.TRAIN_CONSISTENT
                break

            if condition is Condition.INTERVENTION:
                # Only critique when a revision round can still be paid for;
                # otherwise the budget would end on feedback nobody can use.
                if not budget.can_afford(2):
                    break
                critique: Critique = critic.review(
                    prompts.critic_request(task, proposal.rule, result)
                )
                record.critic_feedback = critique.feedback
                record.critic_raw = critique.raw
                record.leak_violations = critique.violations
                record.input_tokens += critique.input_tokens
                record.output_tokens += critique.output_tokens
                message = prompts.generator_revision(critique.feedback, result)
            else:
                message = prompts.generator_self_debug(result)
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
        error=error,
    )
