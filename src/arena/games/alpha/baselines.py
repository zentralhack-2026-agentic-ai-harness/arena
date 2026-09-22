"""Reference strategies for Alpha."""

import random
from collections import Counter

from arena.core import Strategy
from arena.games.alpha.game import AlphaGame

NEIGHBOURS = [
    [b for a, b in AlphaGame.EDGES if a == n] + [a for a, b in AlphaGame.EDGES if b == n]
    for n in range(AlphaGame.N_NODES)
]


def _hop_distances() -> list[list[int]]:
    """All-pairs shortest path lengths (in edges), by BFS from every node."""
    dist = []
    for source in range(AlphaGame.N_NODES):
        row = [-1] * AlphaGame.N_NODES
        row[source] = 0
        frontier = [source]
        while frontier:
            nxt = []
            for u in frontier:
                for v in NEIGHBOURS[u]:
                    if row[v] == -1:
                        row[v] = row[u] + 1
                        nxt.append(v)
            frontier = nxt
        dist.append(row)
    return dist


DISTANCES = _hop_distances()


class DoNothing(Strategy):
    """Never moves. The lowest bar a strategy should clear."""

    def act(self, obs: dict) -> list[tuple[int, int, int]]:
        return []


class RandomStrategy(Strategy):
    """Scatters drones randomly over each occupied node and its neighbours.

    For every node holding drones, draws random weights over the node itself
    and its neighbours, then assigns each drone a destination by those weights.
    Moves are computed from the start-of-turn snapshot, so every move is legal.
    The RNG is seeded from player_id so matches stay reproducible.
    """

    def __init__(self, player_id: int) -> None:
        super().__init__(player_id)
        self.rng = random.Random(player_id)

    def act(self, obs: dict) -> list[tuple[int, int, int]]:
        moves = []
        for node, count in enumerate(obs["player_drones"]):
            if count <= 0:
                continue
            options = [node, *NEIGHBOURS[node]]
            weights = [self.rng.random() for _ in options]
            destinations = Counter(self.rng.choices(options, weights=weights, k=count))
            for to_node, n in destinations.items():
                if to_node != node:
                    moves.append((node, to_node, n))
        return moves


class ProportionalSpread(Strategy):
    """Spreads all drones over the map in proportion to node demand, then holds.

    The target allocation splits the fleet by demand (largest remainder, so it
    sums exactly to the fleet size). Each turn, surplus drones are greedily
    paired with the nearest deficit nodes and moved one hop along a shortest
    path. Once the target is reached the strategy only returns no-ops.
    """

    def __init__(self, player_id: int) -> None:
        super().__init__(player_id)
        self.target = self._target_allocation(AlphaGame.DRONES_PER_PLAYER)
        self.done = False

    @staticmethod
    def _target_allocation(n_drones: int) -> list[int]:
        demands = AlphaGame.NODE_DEMANDS
        total = sum(demands)
        exact = [n_drones * d / total for d in demands]
        target = [int(x) for x in exact]
        by_remainder = sorted(range(len(demands)), key=lambda n: target[n] - exact[n])
        for node in by_remainder[: n_drones - sum(target)]:
            target[node] += 1
        return target

    def act(self, obs: dict) -> list[tuple[int, int, int]]:
        drones = obs["player_drones"]
        if self.done or drones == self.target:
            self.done = True
            return []

        surplus = {n: drones[n] - t for n, t in enumerate(self.target) if drones[n] > t}
        deficit = {n: t - drones[n] for n, t in enumerate(self.target) if drones[n] < t}

        moves: Counter[tuple[int, int]] = Counter()
        pairs = sorted((DISTANCES[s][d], s, d) for s in surplus for d in deficit)
        for _, src, dst in pairs:
            k = min(surplus[src], deficit[dst])
            if k == 0:
                continue
            surplus[src] -= k
            deficit[dst] -= k
            hop = min(v for v in NEIGHBOURS[src] if DISTANCES[v][dst] == DISTANCES[src][dst] - 1)
            moves[(src, hop)] += k

        return [(src, hop, k) for (src, hop), k in moves.items()]
