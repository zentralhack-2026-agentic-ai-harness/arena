from datetime import datetime
from pathlib import Path

import pytest

from arena.games.alpha import AlphaGame
from arena.games.alpha.baselines import ProportionalSpread, RandomStrategy

OUTPUTS_DIR = Path(__file__).resolve().parents[1] / "outputs"


def test_random_vs_proportional_spread():
    pytest.importorskip("matplotlib")

    out_dir = OUTPUTS_DIR / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_dir.mkdir(parents=True)

    game = AlphaGame()
    players = [RandomStrategy(0), ProportionalSpread(1)]

    def save_frame() -> None:
        fig = game.render()
        fig.savefig(out_dir / f"turn_{game.turn:03d}.png")

    save_frame()
    while not game.is_over():
        game.step([player.act(game.observe(player.player_id)) for player in players])
        assert game.n_invalid_actions_last_turn == [0, 0]
        assert game.action_format_correct_last_turn == [True, True]
        assert [sum(drones) for drones in game.drone_allocation] == [20, 20]
        save_frame()

    assert game.turn == AlphaGame.MAX_TURNS
    assert len(list(out_dir.glob("*.png"))) == AlphaGame.MAX_TURNS + 1
