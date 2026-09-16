"""A tiny game used only to test the simulator.

Each turn both players pick a number 0-9; the higher number scores 1 point.
Anything that isn't an int in 0-9 counts as 0 (illegal action = no-op).
"""

from arena.core import Game, Strategy


class DummyGame(Game):
    turns = 3

    def __init__(self, seed: int) -> None:
        super().__init__(seed)
        self.turn = 0
        self._scores = [0.0, 0.0]

    def observe(self, player_id: int) -> dict:
        return {"turn": self.turn, "seed": self.seed, "scores": list(self._scores)}

    def step(self, actions: list[dict]) -> None:
        picks = [self._pick(a) for a in actions]
        if picks[0] > picks[1]:
            self._scores[0] += 1
        elif picks[1] > picks[0]:
            self._scores[1] += 1
        self.turn += 1

    def is_over(self) -> bool:
        return self.turn >= self.turns

    def scores(self) -> list[float]:
        return list(self._scores)

    @staticmethod
    def _pick(action: dict) -> int:
        n = action.get("n")
        return n if isinstance(n, int) and 0 <= n <= 9 else 0


class High(Strategy):
    def act(self, obs: dict) -> dict:
        return {"n": 9}


class Low(Strategy):
    def act(self, obs: dict) -> dict:
        return {"n": 1}


class Crash(Strategy):
    def act(self, obs: dict) -> dict:
        raise RuntimeError("boom")
