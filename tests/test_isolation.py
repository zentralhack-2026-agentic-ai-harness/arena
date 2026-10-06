from pathlib import Path

import pytest

from arena import Entrant, Limits, play_match
from arena.isolation import IsolatedPlayer
from tests import bad_strategies as bad
from tests.dummy_game import DummyGame, High, Low

ROOT = str(Path(__file__).resolve().parents[1])
FAST = Limits(turn_timeout=0.5, init_timeout=2.0, memory_mb=1024)


def isolated(strategy, limits=FAST):
    """High (seat 0) against `strategy` (seat 1), isolated."""
    return play_match(DummyGame, [High, strategy], seed=0, isolate=True, limits=limits)


def test_same_result_as_in_process():
    a = play_match(DummyGame, [High, Low], seed=7)
    b = play_match(DummyGame, [High, Low], seed=7, isolate=True)
    assert a.to_dict() == b.to_dict()


def test_file_target():
    r = isolated(Entrant("bot", "tests/bad_strategies.py:Echo"))
    assert r.forfeit == 1 and r.forfeit_reason == "exception"  # obs has no "reply" key
    assert "KeyError" in r.error


@pytest.mark.parametrize(
    ("strategy", "reason"),
    [
        (bad.Sleeper, "timeout"),
        (bad.SlowInit, "timeout"),
        (bad.InitCrash, "exception"),
        (bad.Exiter, "crash"),
        (bad.HardExiter, "crash"),
        (bad.HugeReply, "protocol"),
        ("tests.bad_strategies:DoesNotExist", "exception"),
    ],
)
def test_failures_forfeit(strategy, reason):
    r = isolated(strategy)
    assert (r.forfeit, r.forfeit_reason) == (1, reason)
    assert r.winner == 0


def test_memory_limit():
    r = isolated(bad.MemoryHog)
    assert r.forfeit == 1
    assert "MemoryError" in r.error


def test_printing_does_not_break_protocol():
    r = isolated(bad.Chatty)
    assert r.forfeit is None
    assert r.scores == [0.0, 0.0]  # both pick 9 every turn


def test_cheater_only_wins_in_process():
    in_process = play_match(DummyGame, [High, bad.Cheater], seed=0)
    assert in_process.winner == 1  # why untrusted code must be isolated
    r = isolated(bad.Cheater)
    assert r.scores == [3.0, 0.0]


def test_local_class_needs_a_target():
    class Local(Low):
        pass

    with pytest.raises(ValueError, match="target string"):
        isolated(Local)


@pytest.fixture
def echo():
    player = IsolatedPlayer("tests.bad_strategies:Echo", 0, FAST, sys_path=[ROOT])
    player.start()
    yield player
    player.close()


@pytest.mark.parametrize(
    "reply",
    [
        [(0, 1, 5), (1, 6, 5)],
        [[0, 1, 5]],
        [(True, 1, 2)],
        {"nested": {"t": (1.5, None, "s\nt")}},
        None,
    ],
)
def test_types_survive_the_round_trip(echo, reply):
    echo.send({"reply": reply})
    got = echo.receive()
    assert got == reply
    assert repr(got) == repr(reply)  # tuple vs list, bool vs int


def test_non_literal_reply_becomes_none(echo):
    echo.send({"fake": True})
    assert echo.receive() is None


def test_non_literal_observation_is_a_game_error(echo):
    with pytest.raises(ValueError, match="not a Python literal"):
        echo.send({"x": object()})
