"""The two agents: the code-writing generator and the oracle critic."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import guards, prompts
from .executor import extract_code
from .llm import Budget, Completion, LLMClient, Message

GENERATOR_ROLE = "generator"
CRITIC_ROLE = "critic"

_RULE_SECTION = re.compile(
    rf"{re.escape(prompts.RULE_HEADER)}\s*(.*?)(?={re.escape(prompts.CODE_HEADER)}|$)",
    re.DOTALL | re.IGNORECASE,
)


@dataclass(frozen=True)
class Proposal:
    """One generator answer: the stated rule plus the candidate program."""

    rule: str
    code: str | None
    raw: str
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    truncated: bool = False


def parse_proposal(text: str) -> tuple[str, str | None]:
    """Split a generator answer into (rule, code); either part may be missing."""
    match = _RULE_SECTION.search(text)
    if match:
        rule: str = match.group(1).strip()
    else:  # no header: keep the prose that precedes the first code fence
        rule = text.split("```", 1)[0].strip()
    return rule, extract_code(text)


@dataclass
class Generator:
    """Writes the rule and the program. Never sees the test output.

    `temperature` overrides the client default, which is how the two conditions
    differ in diversity: sampling needs distinct candidates, revision does not.
    """

    client: LLMClient
    model: str
    budget: Budget
    temperature: float | None = None
    history: list[Message] = field(default_factory=list)

    def propose(self, user_message: str) -> Proposal:
        self.budget.spend(GENERATOR_ROLE)
        self.history.append(Message(role="user", text=user_message))
        completion: Completion = self.client.generate(
            model=self.model,
            system=prompts.GENERATOR_SYSTEM,
            messages=self.history,
            temperature=self.temperature,
        )
        self.history.append(Message(role="model", text=completion.text))
        rule, code = parse_proposal(completion.text)
        return Proposal(
            rule=rule,
            code=code,
            raw=completion.text,
            input_tokens=completion.input_tokens,
            output_tokens=completion.output_tokens,
            thinking_tokens=completion.thinking_tokens,
            truncated=completion.truncated,
        )


@dataclass(frozen=True)
class Critique:
    """Sanitized critic feedback plus the leak-guard audit trail."""

    feedback: str
    raw: str
    violations: list[str]
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0

    @property
    def leaked(self) -> bool:
        return bool(self.violations)


@dataclass
class Critic:
    """Sees the ground truth, returns contradictions only. Stateless across calls.

    Each critique is an independent judgement of the current rule: no memory of
    previous rounds, so it cannot drift into co-authoring the solution.
    """

    client: LLMClient
    model: str
    budget: Budget
    system: str = prompts.CRITIC_SYSTEM

    def review(self, user_message: str) -> Critique:
        self.budget.spend(CRITIC_ROLE)
        completion: Completion = self.client.generate(
            model=self.model,
            system=self.system,
            messages=[Message(role="user", text=user_message)],
        )
        sanitized: guards.Sanitized = guards.sanitize(completion.text)
        return Critique(
            feedback=sanitized.text,
            raw=completion.text,
            violations=sanitized.violations,
            input_tokens=completion.input_tokens,
            output_tokens=completion.output_tokens,
            thinking_tokens=completion.thinking_tokens,
        )
