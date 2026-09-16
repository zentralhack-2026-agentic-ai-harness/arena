"""Alpha: the drone-fleet game from the task slides.

STUB: the rules are not implemented yet. See spec.md for the contract.

Suggested dict shapes (change them freely, but keep spec.md in sync):

observation:
    {
        "turn": int,
        "max_turns": int,
        "player_id": int,
        "nodes": [{"id": int, "demand": float}, ...],
        "edges": [[int, int], ...],
        "bases": [int, int],               # base node per player
        "drones": [{int: int}, {int: int}], # node id -> drone count, per player
        "scores": [float, float],
    }

action:
    {"moves": [{"from": int, "to": int, "count": int}, ...]}

Payout candidate from the slides (still to be confirmed against slide 8):
    capacity_i = drones_i * drone_capacity
    served_i   = capacity_i * demand / max(total_capacity, demand)
"""

from arena.core import Game


class AlphaGame(Game):
    def __init__(self, seed: int) -> None:
        super().__init__(seed)
        # TODO: build the map, place drones at the bases, reset scores.

    def observe(self, player_id: int) -> dict:
        raise NotImplementedError

    def step(self, actions: list[dict]) -> None:
        # TODO: validate each player's moves (illegal = no-op), move drones,
        # pay out demand, advance the turn.
        raise NotImplementedError

    def is_over(self) -> bool:
        raise NotImplementedError

    def scores(self) -> list[float]:
        raise NotImplementedError
