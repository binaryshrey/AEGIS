import json
import os
import pytest
from engine.models.opponent import OpponentModel, Memory

# Realistic 17-cell placement (all 5 ships) for fixed-placement tests
_FULL_PLACEMENT = [
    [0, 0], [0, 1], [0, 2], [0, 3], [0, 4],  # CARRIER (5)
    [2, 0], [2, 1], [2, 2], [2, 3],            # BATTLESHIP (4)
    [4, 0], [4, 1], [4, 2],                     # CRUISER (3)
    [6, 0], [6, 1], [6, 2],                     # SUBMARINE (3)
    [8, 0], [8, 1],                              # DESTROYER (2)
]


def _make_model(placements=None, firings=None):
    m = OpponentModel("bot-test")
    for i, (p, f) in enumerate(zip(placements or [], firings or [])):
        m.record_game(f, p, we_won=True)
    return m


def test_not_deterministic_with_one_game():
    m = _make_model(
        placements=[_FULL_PLACEMENT],
        firings=[[[1, 1], [2, 2]]],
    )
    assert not m.is_fixed_placement()
    assert not m.is_fixed_firing()


def test_fixed_placement_detected():
    m = _make_model(
        placements=[_FULL_PLACEMENT, _FULL_PLACEMENT, _FULL_PLACEMENT],
        firings=[[[1, 1]], [[2, 2]], [[3, 3]]],
    )
    assert m.is_fixed_placement()
    assert not m.is_fixed_firing()


def test_fixed_firing_detected():
    firing = [[1, 1], [2, 2], [3, 3]]
    m = _make_model(
        placements=[[[0, 0]], [[1, 1]], [[2, 2]]],
        firings=[firing, firing, firing],
    )
    assert not m.is_fixed_placement()
    assert m.is_fixed_firing()


def test_both_fixed():
    firing = [[5, 5], [6, 6]]
    m = _make_model(
        placements=[_FULL_PLACEMENT, _FULL_PLACEMENT, _FULL_PLACEMENT],
        firings=[firing, firing, firing],
    )
    assert m.is_fixed_placement()
    assert m.is_fixed_firing()


def test_known_targets_returns_none_without_enough_games():
    m = _make_model(
        placements=[_FULL_PLACEMENT],
        firings=[[[1, 1]]],
    )
    assert m.known_targets() is None


def test_known_targets_returns_cells_when_fixed():
    m = _make_model(
        placements=[_FULL_PLACEMENT, _FULL_PLACEMENT, _FULL_PLACEMENT],
        firings=[[[1, 1]], [[1, 1]], [[1, 1]]],
    )
    targets = m.known_targets()
    assert targets is not None
    assert (0, 0) in targets
    assert len(targets) == 17


def test_partial_placement_not_detected_as_fixed():
    """Partial data (< 9 cells) should NOT trigger is_fixed_placement."""
    partial = [[0, 0], [0, 1], [0, 2]]
    m = _make_model(
        placements=[partial, partial, partial],
        firings=[[[1, 1]], [[2, 2]], [[3, 3]]],
    )
    assert not m.is_fixed_placement()


def test_dangerous_squares_high_frequency():
    m = OpponentModel("bot-test")
    for _ in range(5):
        m.record_game([[1, 1], [2, 2], [3, 3]], [[9, 9]], True)
    dangerous = m.dangerous_squares()
    assert (1, 1) in dangerous


def test_dangerous_squares_low_frequency_not_included():
    m = OpponentModel("bot-test")
    for i in range(5):
        # (1,1) only appears in 1 of 5 games
        shots = [[i, i], [2, 2]] if i != 2 else [[1, 1], [2, 2]]
        m.record_game(shots, [[9, 9]], True)
    dangerous = m.dangerous_squares()
    assert (1, 1) not in dangerous


def test_memory_persists_to_disk(tmp_path):
    path = str(tmp_path / "memory.json")
    mem = Memory(path=path)
    model = mem.get("bot-01")
    model.record_game([[1, 1]], [[0, 0]], True)
    mem.save()

    mem2 = Memory(path=path)
    loaded = mem2.get("bot-01")
    assert loaded.games_played == 1
    assert loaded.wins == 1


def test_last_moves_returns_most_recent():
    m = OpponentModel("bot-test")
    m.record_moves(87)
    m.record_moves(46)
    m.record_moves(17)
    assert m.last_moves() == 17


def test_last_moves_returns_none_with_no_history():
    assert OpponentModel("bot-test").last_moves() is None


def test_last_moves_persists_across_save_load(tmp_path):
    path = str(tmp_path / "memory.json")
    mem = Memory(path=path)
    mem.get("bot-01").record_moves(42)
    mem.save()

    mem2 = Memory(path=path)
    assert mem2.get("bot-01").last_moves() == 42


def test_memory_compounds_across_loads(tmp_path):
    path = str(tmp_path / "memory.json")

    # First run
    mem = Memory(path=path)
    mem.get("bot-01").record_game([[1, 1]], _FULL_PLACEMENT, True)
    mem.save()

    # Second run — loads previous data
    mem2 = Memory(path=path)
    mem2.get("bot-01").record_game([[1, 1]], _FULL_PLACEMENT, True)
    mem2.save()

    # Third run — adds a third game
    mem3 = Memory(path=path)
    mem3.get("bot-01").record_game([[1, 1]], _FULL_PLACEMENT, True)
    mem3.save()

    # Fourth run — should now detect fixed placement (3 games)
    mem4 = Memory(path=path)
    assert mem4.get("bot-01").is_fixed_placement()
