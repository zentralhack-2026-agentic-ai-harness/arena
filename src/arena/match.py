import traceback

from arena.core import Entrant, Game, MatchResult, Strategy


def play_match(
    game_cls: type[Game], entrants: list[Entrant | type[Strategy]], seed: int
) -> MatchResult:
    """Play one match. Seat index = player_id.

    Entrants may be given as bare strategy classes; their class name is then the id.
    If a strategy raises, it forfeits and the match stops. Errors raised by the
    game itself are not caught: those are bugs in the game.
    """
    entrants = [Entrant.of(e) for e in entrants]
    game = game_cls(seed)
    strategies = [e.strategy(player_id) for player_id, e in enumerate(entrants)]
    result = MatchResult(
        players=[e.id for e in entrants],
        seed=seed,
        scores=[],
        turns=0,
    )

    while not game.is_over():
        actions = []
        for player_id, strategy in enumerate(strategies):
            obs = game.observe(player_id)
            try:
                actions.append(strategy.act(obs))
            except Exception:
                result.forfeit = player_id
                result.forfeit_reason = "exception"
                result.error = traceback.format_exc()
                result.scores = game.scores()
                return result
        game.step(actions)
        result.turns += 1

    result.scores = game.scores()
    return result
