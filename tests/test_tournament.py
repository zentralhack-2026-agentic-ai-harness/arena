import pytest

from arena import Entrant, round_robin, summarize
from arena.tournament import pairings
from tests.dummy_game import Crash, DummyGame, High, Low


def test_every_ordered_pair_every_seed():
    strategies = [High, Low, Crash]
    results = round_robin(DummyGame, strategies, seeds=[0, 1])
    assert len(results) == 3 * 2 * 2
    pairings = {tuple(r.players) for r in results}
    assert ("High", "Low") in pairings and ("Low", "High") in pairings


def test_summary_counts():
    results = round_robin(DummyGame, [High, Low], seeds=[0, 1, 2])
    table = summarize(results)
    rows = {line.split()[0]: line.split()[1:] for line in table.splitlines()[1:]}
    assert rows["High"][:4] == ["6", "0", "0", "0"]  # W D L F
    assert rows["Low"][:4] == ["0", "0", "6", "0"]


def test_same_class_under_different_ids():
    results = round_robin(DummyGame, [Entrant("a", High), Entrant("b", High)], seeds=[0])
    assert sorted(tuple(r.players) for r in results) == [("a", "b"), ("b", "a")]


def test_duplicate_ids_rejected():
    with pytest.raises(ValueError, match="unique"):
        round_robin(DummyGame, [High, Entrant("High", Low)], seeds=[0])


def test_panel_pairings():
    a, b, p, q = (Entrant(i, Low) for i in "abpq")
    pairs = pairings([a, b], [p, q])
    assert len(pairs) == 2 * 2 * 2
    assert (a, p) in pairs and (p, a) in pairs
    assert (a, b) not in pairs and (p, q) not in pairs


def test_panel_round_robin():
    results = round_robin(DummyGame, [High], seeds=[0, 1], panel=[Low, Crash])
    assert len(results) == 1 * 2 * 2 * 2
    assert all("High" in r.players for r in results)


def test_duplicate_ids_across_panel_rejected():
    with pytest.raises(ValueError, match="unique"):
        round_robin(DummyGame, [High], seeds=[0], panel=[High])


def test_parallel_matches_same_results_in_same_order():
    serial = round_robin(DummyGame, [High, Low, Crash], seeds=[0, 1])
    parallel = round_robin(DummyGame, [High, Low, Crash], seeds=[0, 1], workers=3)
    assert [r.to_dict() for r in serial] == [r.to_dict() for r in parallel]


def test_parallel_isolated():
    results = round_robin(DummyGame, [High, Low], seeds=[0, 1], isolate=True, workers=2)
    assert [r.winner for r in results] == [0, 0, 1, 1]
