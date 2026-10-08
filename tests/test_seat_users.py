"""Workers under uids of their own (Limits.uid_base). Switching uids needs root, so these
tests are skipped otherwise; to run them, see "Isolation" in the README.
"""

import os
from pathlib import Path

import pytest

from arena import Entrant, Limits, play_match, round_robin
from tests import bad_strategies as bad
from tests.dummy_game import DummyGame, High

pytestmark = pytest.mark.skipif(os.geteuid() != 0, reason="switching uids needs root")

BASE = 1001
LIMITS = Limits(turn_timeout=0.5, init_timeout=2.0, uid_base=BASE)


def play(*seats):
    return play_match(DummyGame, list(seats), seed=0, isolate=True, limits=LIMITS)


def users_of(uid: int) -> list[int]:
    """Pids of the live processes running as `uid`."""
    pids = []
    for entry in Path("/proc").iterdir():
        try:
            status = (entry / "status").read_text()
        except (OSError, ValueError):
            continue
        uids = next(line for line in status.splitlines() if line.startswith("Uid:"))
        if str(uid) in uids.split()[1:]:
            pids.append(int(entry.name))
    return pids


@pytest.mark.parametrize("seat", [0, 1])
def test_each_seat_has_its_own_user(seat):
    seats = [High, High]
    seats[seat] = bad.WhoAmI
    r = play(*seats)
    assert r.forfeit == seat
    uid = BASE + seat
    assert f"uid={uid} gid={uid} groups=[]" in r.error


def test_trusted_entrant_keeps_the_referee_user():
    r = play(High, Entrant("me", "tests.bad_strategies:WhoAmI", trusted=True))
    assert f"uid={os.getuid()} " in r.error


def test_cannot_kill_the_referee_or_the_opponent():
    r = play(High, bad.Intruder)
    assert r.forfeit is None
    assert r.scores == [0.0, 0.0]  # both pick 9 every turn


def test_leftover_processes_are_killed():
    r = play(High, bad.Lingerer)
    assert r.forfeit is None
    assert users_of(BASE + 1) == []


def test_cannot_write_its_working_directory():
    r = play(High, bad.Scribbler)
    assert (r.forfeit, r.forfeit_reason) == (1, "exception")
    assert "PermissionError" in r.error


def test_strategy_file_need_not_be_readable_by_its_worker(tmp_path):
    path = tmp_path / "strategy.py"
    path.write_text(
        "class Strategy:\n"
        "    def __init__(self, player_id):\n"
        "        try:\n"
        "            open(__file__).close()\n"
        "        except PermissionError:\n"
        "            pass\n"
        "        else:\n"
        "            raise RuntimeError('could read its own file')\n"
        "\n"
        "    def act(self, obs):\n"
        "        return {'n': 9}\n"
    )
    path.chmod(0o600)
    r = play(High, Entrant("file", f"{path}:Strategy"))
    assert r.forfeit is None, r.error


def test_parallel_matches_use_separate_users():
    results = round_robin(
        DummyGame,
        [High],
        seeds=list(range(4)),
        panel=[bad.WhoAmI],
        isolate=True,
        limits=LIMITS,
        workers=2,
    )
    for r in results:
        uid = int(r.error.split("RuntimeError: uid=")[1].split()[0])
        assert BASE <= uid < BASE + 4
        assert (uid - BASE) % 2 == r.forfeit  # the seat
