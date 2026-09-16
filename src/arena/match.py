import traceback

from arena.core import Game, MatchResult, Strategy


def play_match(
    game_cls: type[Game], strategy_classes: list[type[Strategy]], seed: int
) -> MatchResult:
    """Play one match. Seat index = player_id.

    If a strategy raises, it forfeits and the match stops. Errors raised by the
    game itself are not caught: those are bugs in the game.
    """
    game = game_cls(seed)
    strategies = [cls(player_id) for player_id, cls in enumerate(strategy_classes)]
    result = MatchResult(
        players=[cls.__name__ for cls in strategy_classes],
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
                result.error = traceback.format_exc()
                result.scores = game.scores()
                return result
        game.step(actions)
        result.turns += 1

    result.scores = game.scores()
    return result
