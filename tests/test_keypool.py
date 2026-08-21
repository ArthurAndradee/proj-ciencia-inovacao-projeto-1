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
    assert "no key left to serve it" in str(excinfo.value)


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
        "rejected": False,
        "exhausted": ["flash"],
    }
    assert usage["key2"]["calls"] == 2
    assert usage["key2"]["exhausted"] == []


def test_an_empty_pool_is_rejected_early() -> None:
    with pytest.raises(ValueError, match="no API keys"):
        PooledClient([])


def test_a_rejected_key_is_dropped_instead_of_killing_the_run() -> None:
    """A 401 belongs to one key; the run must survive it.

    Regression: a single unauthenticated key propagated out of the pool and
    took all seven workers down with it, finishing zero tasks.
    """
    bad = FakeKeyClient("bad", raises=PermanentAPIError("401 UNAUTHENTICATED"))
    good = FakeKeyClient("good")
    pool = PooledClient([bad, good])

    assert generate(pool) == "answer from good"
    assert pool.usage()[0]["rejected"] is True


def test_a_rejected_key_is_never_tried_again_for_any_model() -> None:
    bad = FakeKeyClient("bad", raises=PermanentAPIError("403 PERMISSION_DENIED"))
    good = FakeKeyClient("good")
    pool = PooledClient([bad, good])

    for _ in range(4):
        generate(pool, model="flash")
    generate(pool, model="pro")

    assert len(bad.calls) == 1  # one wasted call, then out for good
    assert len(good.calls) == 5


def test_a_malformed_request_still_aborts() -> None:
    """A 400 fails the same on every key; dropping them one by one is wrong."""
    first = FakeKeyClient("first", raises=PermanentAPIError("400 INVALID_ARGUMENT"))
    second = FakeKeyClient("second")
    pool = PooledClient([first, second])

    with pytest.raises(PermanentAPIError):
        generate(pool)
    assert second.calls == []
    assert pool.usage()[0]["rejected"] is False


def test_every_key_rejected_gives_a_clear_error() -> None:
    pool = PooledClient(
        [
            FakeKeyClient("a", raises=PermanentAPIError("401 UNAUTHENTICATED")),
            FakeKeyClient("b", raises=PermanentAPIError("401 UNAUTHENTICATED")),
        ]
    )
    with pytest.raises(QuotaExhausted) as excinfo:
        generate(pool)
    assert "rejected" in str(excinfo.value)
