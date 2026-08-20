"""The pool must turn N keys into N quotas, and survive losing any of them."""

from __future__ import annotations

import threading

import pytest

from arc_experiment.keypool import PooledClient
from arc_experiment.llm import Completion, Message
from arc_experiment.ratelimit import PermanentAPIError, QuotaExhausted

PROMPT: list[Message] = [Message(role="user", text="solve")]


class FakeKeyClient:
    """A key that answers, or fails in one of the ways a real key fails.

    `exhausted_for` names the models whose daily quota is gone; every other
    model keeps working, which is how the real per-model quota behaves.
    """

    def __init__(
        self,
        name: str,
        exhausted_for: set[str] | None = None,
        raises: Exception | None = None,
    ) -> None:
        self.name: str = name
        self.exhausted_for: set[str] = exhausted_for or set()
        self.raises: Exception | None = raises
        self.calls: list[str] = []

    def generate(
        self,
        model: str,
        system: str,
        messages: list[Message],
        temperature: float | None = None,
    ) -> Completion:
        self.calls.append(model)
        if self.raises is not None:
            raise self.raises
        if model in self.exhausted_for:
            raise QuotaExhausted(f"{model}: daily quota exhausted")
        return Completion(text=f"answer from {self.name}")


def generate(pool: PooledClient, model: str = "flash") -> str:
    return pool.generate(model=model, system="sys", messages=PROMPT).text


def test_a_spent_key_hands_the_call_to_the_next_one() -> None:
    spent = FakeKeyClient("spent", exhausted_for={"flash"})
    healthy = FakeKeyClient("healthy")
    pool = PooledClient([spent, healthy])

    assert generate(pool) == "answer from healthy"


def test_a_spent_key_is_not_tried_again() -> None:
    """Retrying a dead quota would cost a failed call on every single request."""
    spent = FakeKeyClient("spent", exhausted_for={"flash"})
    healthy = FakeKeyClient("healthy")
    pool = PooledClient([spent, healthy])

    for _ in range(5):
        generate(pool)

    assert len(spent.calls) == 1
    assert len(healthy.calls) == 5


def test_quota_is_per_model_so_the_key_still_serves_the_other_one() -> None:
    partial = FakeKeyClient("partial", exhausted_for={"flash"})
    pool = PooledClient([partial])

    with pytest.raises(QuotaExhausted):
        generate(pool, model="flash")
    assert generate(pool, model="pro") == "answer from partial"


def test_every_key_spent_raises_quota_exhausted() -> None:
    pool = PooledClient(
        [
            FakeKeyClient("a", exhausted_for={"flash"}),
            FakeKeyClient("b", exhausted_for={"flash"}),
        ]
    )

    with pytest.raises(QuotaExhausted) as excinfo:
        generate(pool)
    assert "every key is out of quota" in str(excinfo.value)


def test_a_bad_request_propagates_instead_of_burning_every_key() -> None:
    """A malformed prompt fails identically on all keys; trying them all wastes quota."""
    first = FakeKeyClient("first", raises=PermanentAPIError("400 invalid argument"))
    second = FakeKeyClient("second")
    pool = PooledClient([first, second])

    with pytest.raises(PermanentAPIError):
        generate(pool)
    assert second.calls == []


def test_exhausted_retries_move_on_to_the_next_key() -> None:
    """A key whose own retries are spent is worth less than an untouched key."""
    stubborn = FakeKeyClient("stubborn", raises=RuntimeError("API call failed after 3"))
    healthy = FakeKeyClient("healthy")
    pool = PooledClient([stubborn, healthy])

    assert generate(pool) == "answer from healthy"


def test_calls_are_spread_evenly_over_the_keys() -> None:
    clients = [FakeKeyClient(f"key{i}") for i in range(3)]
    pool = PooledClient(clients)

    for _ in range(9):
        generate(pool)

    assert [len(client.calls) for client in clients] == [3, 3, 3]


def test_concurrent_workers_do_not_pile_onto_one_key() -> None:
    """Reservation happens under the lock, so threads see each other's choices."""
    clients = [FakeKeyClient(f"key{i}") for i in range(4)]
    pool = PooledClient(clients)

    threads = [threading.Thread(target=lambda: generate(pool)) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    counts = [len(client.calls) for client in clients]
    assert sum(counts) == 20
    assert counts == [5, 5, 5, 5]


def test_usage_reports_calls_apart_from_failures() -> None:
    spent = FakeKeyClient("spent", exhausted_for={"flash"})
    healthy = FakeKeyClient("healthy")
    pool = PooledClient([spent, healthy])

    generate(pool)
    generate(pool)

    usage = {entry["key"]: entry for entry in pool.usage()}
    assert usage["key1"] == {
        "key": "key1",
        "calls": 0,
        "failures": 1,
        "exhausted": ["flash"],
    }
    assert usage["key2"]["calls"] == 2
    assert usage["key2"]["exhausted"] == []


def test_an_empty_pool_is_rejected_early() -> None:
    with pytest.raises(ValueError, match="no API keys"):
        PooledClient([])
