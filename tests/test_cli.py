import json
from pathlib import Path

import pytest

from arena.cli import main

HERE = Path(__file__).resolve().parent
STRATEGIES = HERE / "bad_strategies.py"


def test_run_with_game_package(capsys):
    main(
        [
            "run",
            "--game",
            "tests.dummy_game",
            "--strategies",
            "tests.dummy_game:High",
            "tests.dummy_game:Low",
            "--seeds",
            "2",
            "--in-process",
        ]
    )
    assert "High" in capsys.readouterr().out


def test_run_with_panel(capsys):
    main(
        [
            "run",
            "--game",
            "tests.dummy_game:DummyGame",
            "--strategies",
            "a=tests.dummy_game:High",
            "--panel",
            "tests.dummy_game:Low",
            "--seeds",
            "1",
        ]
    )
    rows = capsys.readouterr().out.splitlines()[1:]
    assert sorted(row.split()[0] for row in rows) == ["Low", "a"]


def test_check_passes_and_fails(tmp_path, capsys):
    report = tmp_path / "report.json"
    assert (
        main(
            ["check", "tests.dummy_game:High", "--game", "tests.dummy_game", "--json", str(report)]
        )
        == 0
    )
    data = json.loads(report.read_text())
    assert data["passed"] and len(data["matches"]) == 2  # both seats

    assert main(["check", f"{STRATEGIES}:Exiter", "--game", "tests.dummy_game"]) == 1
    out = capsys.readouterr().out
    assert "FORFEIT (crash)" in out and "FAILED" in out


def test_make_task(tmp_path):
    prices = tmp_path / "prices.json"
    prices.write_text(
        json.dumps(
            {
                "gpt-5-nano": {"input": 0.05, "output": 0.4},
                "gpt-5-mini": {"input": 0.25, "output": 2.0},
                "other": {"input": 9, "output": 9},
            }
        )
    )
    main(
        [
            "make-task",
            "--prices",
            str(prices),
            "--game",
            "tests.dummy_game",
            "--out",
            str(tmp_path / "task"),
            "--budget-usd",
            "1.5",
            "--model",
            "gpt-5-nano",
            "--model",
            "gpt-5-mini",
        ]
    )
    assert (tmp_path / "task" / "spec.md").read_text() == (HERE / "dummy_spec.md").read_text()
    task = json.loads((tmp_path / "task" / "task.json").read_text())
    assert task["game_name"] == "dummy_game"
    assert task["budget_usd"] == 1.5
    assert task["allowed_models"] == ["gpt-5-nano", "gpt-5-mini"]
    assert task["strategy_file"] == "strategy.py"
    assert set(task["prices"]) == {"gpt-5-nano", "gpt-5-mini"}  # the allowed ones only
    assert task["contract_version"] == "0.2"


def test_tournament_job(tmp_path, capsys):
    (tmp_path / "bots").mkdir()
    (tmp_path / "bots" / "nine.py").write_text(
        "class Strategy:\n"
        "    def __init__(self, player_id):\n"
        "        pass\n"
        "    def act(self, obs):\n"
        "        return {'n': 9}\n"
    )
    job = {
        "game": "tests.dummy_game",
        "entrants": [{"id": "team_a", "strategy": "bots/nine.py:Strategy"}],  # relative to job
        "panel": [{"id": "low", "strategy": "tests.dummy_game:Low"}],
        "seeds": [0, 1],
        "limits": {"turn_timeout": 2.0},
        "workers": 2,
    }
    (tmp_path / "job.json").write_text(json.dumps(job))
    out = tmp_path / "matches.jsonl"
    main(["tournament", str(tmp_path / "job.json"), "--out", str(out)])
    lines = [json.loads(line) for line in out.read_text().splitlines()]
    assert len(lines) == 1 * 1 * 2 * 2
    assert all(m["forfeit"] is None for m in lines)
    assert {m["players"][m["winner"]] for m in lines} == {"team_a"}
    assert all(isinstance(m["t"], float) for m in lines)
    assert [m["t"] for m in lines] == sorted(m["t"] for m in lines)


def test_tournament_job_with_explicit_tables(tmp_path):
    job = {
        "game": "tests.dummy_game",
        "entrants": [
            {"id": i, "strategy": "tests.dummy_game:Low", "trusted": True}
            for i in ("a1", "a2", "b1")
        ],
        "tables": [["a1", "b1"], ["a2", "b1"]],  # a1 and a2 (one team) never meet
        "seeds": [0, 1],
        "isolate": False,
    }
    (tmp_path / "job.json").write_text(json.dumps(job))
    out = tmp_path / "matches.jsonl"
    main(["tournament", str(tmp_path / "job.json"), "--out", str(out)])
    seatings = [tuple(json.loads(line)["players"]) for line in out.read_text().splitlines()]
    assert len(seatings) == 2 * 2 * 2
    assert set(seatings) == {("a1", "b1"), ("b1", "a1"), ("a2", "b1"), ("b1", "a2")}


def test_tournament_job_rejects_unknown_table_ids(tmp_path):
    job = {
        "game": "tests.dummy_game",
        "entrants": [{"id": "a", "strategy": "tests.dummy_game:Low"}],
        "tables": [["a", "nobody"]],
        "seeds": [0],
    }
    (tmp_path / "job.json").write_text(json.dumps(job))
    with pytest.raises(SystemExit, match="unknown ids"):
        main(["tournament", str(tmp_path / "job.json"), "--out", str(tmp_path / "m.jsonl")])


def test_check_plays_every_seat_of_a_three_seat_game(tmp_path):
    report = tmp_path / "report.json"
    game = "tests.dummy_game:ThreeWayGame"
    assert main(["check", "tests.dummy_game:High", "--game", game, "--json", str(report)]) == 0
    matches = json.loads(report.read_text())["matches"]
    assert [m["players"].index("candidate") for m in matches] == [0, 1, 2]
    assert all(m["players"].count("idle") == 2 for m in matches)


def test_run_three_seat_game(capsys):
    game = "tests.dummy_game:ThreeWayGame"
    strategies = ["tests.dummy_game:High", "tests.dummy_game:Mid"]
    with pytest.raises(SystemExit, match="3 seats"):
        main(["run", "--game", game, "--strategies", *strategies, "--in-process"])
    main(["run", "--game", game, "--strategies", *strategies, "tests.dummy_game:Low",
          "--seeds", "1", "--in-process"])  # fmt: skip
    rows = capsys.readouterr().out.splitlines()[1:]
    assert sorted(row.split()[:2] for row in rows) == [["High", "3"], ["Low", "3"], ["Mid", "3"]]
    assert rows[0].startswith("High")  # the only one that ever scores
