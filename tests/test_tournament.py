from collections import Counter
from itertools import combinations, permutations

import pytest

from arena import Entrant, round_robin, summarize
from arena.tournament import schedule, tables
from tests.dummy_game import Crash, DummyGame, High, Low, Mid, ThreeWayGame


def test_every_ordered_pair_every_seed():
    strategies = [High, Low, Crash]
    results = round_robin(DummyGame, strategies, seeds=[0, 1])
    assert len(results) == 3 * 2 * 2
    seatings = {tuple(r.players) for r in results}
    assert ("High", "Low") in seatings and ("Low", "High") in seatings


def test_summary_counts():
    results = round_robin(DummyGame, [High, Low], seeds=[0, 1, 2])
    table = summarize(results)
    rows = {line.split()[0]: line.split()[1:] for line in table.splitlines()[1:]}
    assert rows["High"] == ["6", "18.00", "3.00", "100.0%", "0"]  # matches revenue mean share F
    assert rows["Low"] == ["6", "0.00", "0.00", "0.0%", "0"]
    assert table.splitlines()[1].startswith("High")  # sorted by revenue


def test_same_class_under_different_ids():
    results = round_robin(DummyGame, [Entrant("a", High), Entrant("b", High)], seeds=[0])
    assert sorted(tuple(r.players) for r in results) == [("a", "b"), ("b", "a")]


def test_duplicate_ids_rejected():
    with pytest.raises(ValueError, match="unique"):
        round_robin(DummyGame, [High, Entrant("High", Low)], seeds=[0])


def test_two_seat_tables_are_all_ordered_pairs():
    a, b, c = (Entrant(i, Low) for i in "abc")
    assert sorted(tables([a, b, c], 2), key=str) == sorted(permutations([a, b, c], 2), key=str)


def test_panel_pairings():
    a, b, p, q = (Entrant(i, Low) for i in "abpq")
    pairs = tables([a, b], 2, [p, q])
    assert len(pairs) == 2 * 2 * 2
    assert (a, p) in pairs and (p, a) in pairs
    assert (a, b) not in pairs and (p, q) not in pairs


def test_three_seat_tables():
    field = [Entrant(i, Low) for i in "abcd"]
    seatings = tables(field, 3)
    assert len(seatings) == 4 * 3  # C(4, 3) tables, 3 rotations each
    assert all(len(set(s)) == 3 for s in seatings)  # nobody sits twice at a table
    for e in field:  # every entrant: in 3 tables, every seat once per table
        assert Counter(s.index(e) for s in seatings if e in s) == {0: 3, 1: 3, 2: 3}
    for pair in combinations(field, 2):  # every two entrants meet equally often
        assert sum(set(pair) <= set(s) for s in seatings) == 2 * 3


def test_three_seat_tables_with_panel():
    a, b, p, q, r = (Entrant(i, Low) for i in "abpqr")
    seatings = tables([a, b], 3, [p, q, r])
    assert len(seatings) == 2 * 3 * 3  # entrants x C(3, 2) panel pairs x rotations
    assert all(len({a, b} & set(s)) == 1 for s in seatings)  # exactly one entrant per table
    assert (a, p, q) in seatings and (p, q, a) in seatings and (q, a, p) in seatings


def test_too_few_entrants_for_a_table():
    a, b, p = (Entrant(i, Low) for i in "abp")
    with pytest.raises(ValueError, match="at least 3 entrants"):
        tables([a, b], 3)
    with pytest.raises(ValueError, match="panel of at least 2"):
        tables([a, b], 3, [p])


def test_three_seat_round_robin():
    results = round_robin(ThreeWayGame, [High, Mid, Low, Crash], seeds=[0, 1])
    assert len(results) == 4 * 3 * 2  # tables x rotations x seeds
    assert all(len(r.players) == len(r.scores) == 3 for r in results)
    high = [r for r in results if "High" in r.players and "Crash" not in r.players]
    assert all(r.winner == r.players.index("High") for r in high)


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
    assert [r.winner for r in results] == [0, 1, 0, 1]  # rounds: both seats of seed 0 first


def test_schedule_plays_rounds():
    field = [Entrant(i, Low) for i in "abcd"]
    seatings = tables(field, 2)
    jobs = schedule(seatings, [5, 6, 7])
    assert len(jobs) == len(seatings) * 3
    assert [seed for _, seed in jobs] == [5] * 12 + [6] * 12 + [7] * 12
    for k in range(0, len(jobs), 2):  # both seats of a pairing next to each other
        (x, _), (y, _) = jobs[k], jobs[k + 1]
        assert x == y[::-1]
    for seed in (5, 6, 7):  # every round plays every seating once
        assert sorted(map(str, (s for s, t in jobs if t == seed))) == sorted(map(str, seatings))
    rounds = [[s for s, t in jobs if t == seed][::2] for seed in (5, 6, 7)]
    assert len({tuple(map(str, r)) for r in rounds}) > 1  # pairing order shuffled per round
    assert schedule(seatings, [5, 6, 7]) == jobs  # deterministic
