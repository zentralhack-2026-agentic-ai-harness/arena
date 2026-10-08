import json

from arena import Entrant, play_match
from tests.dummy_game import Crash, DummyGame, High, Low


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


def test_forfeit_freezes_the_score_and_the_others_play_on():
    r = play_match(DummyGame, [CrashAtTurn2, Low], seed=0)
    assert (r.forfeit, r.forfeit_turns) == (0, [2, None])
    assert r.turns == 3
    assert r.scores == [2.0, 1.0]  # 2 earned before failing; Low wins turn 2 against a no-op
    assert r.winner == 1


def test_match_stops_when_every_seat_has_failed():
    r = play_match(DummyGame, [Crash, CrashAtTurn2], seed=0)
    assert r.forfeit == 0  # the first to fail
    assert r.forfeit_turns == [0, 2]
    assert r.turns == 3  # turn 2 is still played (by no one), then the match stops
    assert r.scores == [0.0, 2.0]


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
