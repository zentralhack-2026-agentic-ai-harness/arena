"""Reference strategies for Alpha."""

from arena.core import Strategy


class DoNothing(Strategy):
    """Never moves. The lowest bar a strategy should clear."""

    def act(self, obs: dict) -> dict:
        return {"moves": []}


class RandomStrategy(Strategy):
    """Moves drones to random neighbouring nodes.

    STUB: implement once the observation format is settled. Seed any RNG
    from the observation or player_id so matches stay reproducible.
    """

    def act(self, obs: dict) -> dict:
        raise NotImplementedError
