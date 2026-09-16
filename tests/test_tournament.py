from arena import round_robin, summarize
from tests.dummy_game import Crash, DummyGame, High, Low


def test_every_ordered_pair_every_seed():
    strategies = [High, Low, Crash]
    results = round_robin(DummyGame, strategies, seeds=[0, 1])
    assert len(results) == 3 * 2 * 2
    pairings = {tuple(r.players) for r in results}
    assert ("High", "Low") in pairings and ("Low", "High") in pairings


def test_summary_counts():
    results = round_robin(DummyGame, [High, Low], seeds=[0, 1, 2])
    table = summarize(results)
    rows = {line.split()[0]: line.split()[1:] for line in table.splitlines()[1:]}
    assert rows["High"][:4] == ["6", "0", "0", "0"]  # W D L F
    assert rows["Low"][:4] == ["0", "0", "6", "0"]
