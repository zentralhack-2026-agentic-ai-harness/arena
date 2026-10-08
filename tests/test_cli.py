import json
from pathlib import Path

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
