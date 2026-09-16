from arena import play_match
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
    assert r.turns == 0
    assert "boom" in r.error


def test_seed_reaches_game():
    seen = []

    class Spy(Low):
        def act(self, obs):
            seen.append(obs["seed"])
            return super().act(obs)

    play_match(DummyGame, [Spy, Low], seed=42)
    assert set(seen) == {42}
