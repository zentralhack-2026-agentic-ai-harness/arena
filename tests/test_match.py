import json

import pytest

from arena import Entrant, play_match
from tests.dummy_game import Crash, DummyGame, High, Low, Mid, ThreeWayGame


def test_normal_match():
    r = play_match(DummyGame, [High, Low], seed=7)
    assert r.players == ["High", "Low"]
    assert r.scores == [3.0, 0.0]
    assert r.turns == 3
    assert r.winner == 0
    assert r.forfeit is None


def test_draw():
    r = play_match(DummyGame, [Low, Low], seed=0)
    assert r.winner is None


def test_forfeit_on_exception():
    r = play_match(DummyGame, [High, Crash], seed=0)
    assert r.forfeit == 1
    assert r.winner == 0
    assert r.forfeit_turns == [None, 0]
    assert r.turns == 3  # the other seat plays to the end
    assert r.scores == [3.0, 0.0]
    assert "boom" in r.error


class CrashAtTurn2(High):
    def act(self, obs):
        if obs["turn"] == 2:
            raise RuntimeError("late boom")
        return super().act(obs)


def test_forfeit_plays_none_and_the_others_play_on():
    r = play_match(DummyGame, [CrashAtTurn2, Low], seed=0)
    assert (r.forfeit, r.forfeit_turns) == (0, [2, None])
    assert r.turns == 3
    assert r.scores == [2.0, 1.0]  # 2 earned before failing; Low wins turn 2 against a no-op
    assert r.winner == 1


class IncomeGame(DummyGame):
    """DummyGame in which every seat also earns 1 point per turn, whatever it plays."""

    turns = 5

    def step(self, actions: list[dict]) -> None:
        super().step(actions)
        self._scores = [s + 1 for s in self._scores]


def test_a_failed_seat_keeps_scoring():
    r = play_match(IncomeGame, [CrashAtTurn2, Low], seed=0)
    assert r.forfeit_turns == [2, None]
    # seat 0: wins turns 0-1, then plays None and loses turns 2-4, plus 1 per turn throughout
    assert r.scores == [7.0, 8.0]


def test_match_plays_to_the_end_when_every_seat_has_failed():
    r = play_match(IncomeGame, [Crash, CrashAtTurn2], seed=0)
    assert r.forfeit == 0  # the first to fail
    assert r.forfeit_turns == [0, 2]
    assert r.turns == 5  # turns 2-4 are played by no one
    assert r.scores == [5.0, 7.0]


def test_seed_reaches_game():
    seen = []

    class Spy(Low):
        def act(self, obs):
            seen.append(obs["seed"])
            return super().act(obs)

    play_match(DummyGame, [Spy, Low], seed=42)
    assert set(seen) == {42}


def test_entrant_ids_are_reported():
    r = play_match(DummyGame, [Entrant("a", High), Entrant("b", High)], seed=0)
    assert r.players == ["a", "b"]


def test_forfeit_reason_and_to_dict():
    d = play_match(DummyGame, [High, Crash], seed=0).to_dict()
    assert d["forfeit"] == 1
    assert d["forfeit_reason"] == "exception"
    assert d["winner"] == 0
    assert json.loads(json.dumps(d)) == d


def test_one_entrant_per_seat():
    with pytest.raises(ValueError, match="3 seats, got 2 entrants"):
        play_match(ThreeWayGame, [High, Low], seed=0)
    with pytest.raises(ValueError, match="2 seats, got 3 entrants"):
        play_match(DummyGame, [High, Low, Low], seed=0)


def test_three_seat_match():
    r = play_match(ThreeWayGame, [Low, High, Mid], seed=0)
    assert r.scores == [0.0, 3.0, 0.0]
    assert r.winner == 1


def test_three_seat_tie_at_the_top_has_no_winner():
    r = play_match(ThreeWayGame, [High, High, Low], seed=0)
    assert r.scores == [0.0, 0.0, 0.0]
    assert r.winner is None


def test_three_seat_forfeit_the_others_play_on():
    r = play_match(ThreeWayGame, [CrashAtTurn2, Mid, Low], seed=0)
    assert r.forfeit_turns == [2, None, None]
    assert r.turns == 3
    assert r.scores == [2.0, 1.0, 0.0]  # Mid wins turn 2 once High's seat is a no-op
    assert r.winner == 1  # the forfeited seat cannot win, whatever its score


def test_no_winner_when_every_seat_forfeits():
    r = play_match(DummyGame, [Crash, CrashAtTurn2], seed=0)
    assert r.winner is None
