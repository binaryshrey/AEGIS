import time
import pytest
from engine.strategies.targeting import Targeting


@pytest.fixture
def t():
    return Targeting(board_size=10)


def test_miss_zeroes_probability(t):
    t.update(3, 4, "miss")
    assert t.prob[3][4] == 0
    assert (3, 4) in t.misses


def test_hit_boosts_neighbors(t):
    before = t.prob[2][4]
    t.update(3, 4, "hit")
    assert t.prob[2][4] > before
    assert t.prob[3][5] > before
    assert t.prob[4][4] > before


def test_hit_adds_to_hunt_stack(t):
    t.update(5, 5, "hit")
    assert len(t.hunt_stack) > 0
    neighbors = {(4, 5), (6, 5), (5, 4), (5, 6)}
    assert set(t.hunt_stack) & neighbors == set(t.hunt_stack)


def test_hunt_stack_takes_priority_over_prob_map(t):
    t.update(5, 5, "hit")  # pushes neighbors to hunt stack
    move = t.next_move()
    neighbors = {(4, 5), (6, 5), (5, 4), (5, 6)}
    assert move in neighbors


def test_known_targets_take_highest_priority(t):
    t.update(5, 5, "hit")  # would normally put neighbors in hunt stack
    t.inject_known_targets([(0, 0), (0, 1)])
    assert t.next_move() == (0, 0)
    assert t.next_move() == (0, 1)


def test_no_repeated_moves(t):
    moves = set()
    for _ in range(50):
        row, col = t.next_move()
        assert (row, col) not in moves
        moves.add((row, col))
        t.update(row, col, "miss")


def test_all_cells_reachable(t):
    moves = set()
    for _ in range(100):
        try:
            row, col = t.next_move()
            moves.add((row, col))
            t.update(row, col, "miss")
        except RuntimeError:
            break
    assert len(moves) == 100  # full 10x10 board


def test_decision_within_budget():
    """Decision must always complete well within turnTimeoutSeconds."""
    t = Targeting(board_size=10)
    budget = 0.1  # 100ms — far tighter than the real 10s
    for _ in range(100):
        t0 = time.perf_counter()
        try:
            row, col = t.next_move()
        except RuntimeError:
            break
        elapsed = time.perf_counter() - t0
        assert elapsed < budget, f"Move took {elapsed:.3f}s — exceeds {budget}s budget"
        t.update(row, col, "miss")


def test_sunk_clears_hunt_stack(t):
    t.update(3, 3, "hit")
    t.update(3, 4, "sunk")
    assert (3, 3) not in t.hunt_stack
    assert (3, 4) not in t.hunt_stack


def test_sunk_does_not_boost_neighbors(t):
    """Sinking a ship must not boost adjacent cells — they're empty sea."""
    t.update(3, 3, "hit")
    assert t.prob[3][5] == 1.0   # not adjacent to hit, so baseline

    t.update(3, 4, "sunk")
    assert t.prob[3][5] == 1.0   # must stay at baseline — no boost on sunk


def test_sunk_clears_stale_hunt_entries_from_prior_hits(t):
    """
    Sinking a ship must clear ALL hunt_stack entries adjacent to the entire ship,
    not just adjacent to the final sunk cell.
    """
    t.update(5, 3, "hit")
    t.update(5, 5, "hit")
    t.update(5, 4, "sunk")

    ship_adjacents = {(5,2), (4,3), (6,3), (5,6), (4,5), (6,5), (4,4), (6,4)}
    remaining = set(t.hunt_stack)
    assert remaining & ship_adjacents == set(), (
        f"Stale hunt entries: {remaining & ship_adjacents}"
    )


def test_connected_hits_finds_ship_cells(t):
    """_connected_hits BFS must return all contiguous hit cells."""
    t.update(2, 3, "hit")
    t.update(2, 4, "hit")
    t.update(2, 5, "hit")
    ship = t._connected_hits(2, 3)
    assert ship == {(2, 3), (2, 4), (2, 5)}


def test_probability_sweep_prefers_parity_cells(t):
    """Probability sweep must visit all (row+col)%2==0 cells before (row+col)%2==1 cells."""
    for _ in range(50):
        row, col = t.next_move()
        assert (row + col) % 2 == 0, f"Expected even-parity cell, got ({row},{col})"
        t.update(row, col, "miss")
    # After even-parity cells are exhausted, odd-parity cells are used
    row, col = t.next_move()
    assert (row + col) % 2 == 1


def test_enumeration_solver_tracks_remaining_ships():
    """_remaining_ships() correctly reflects sunk ships."""
    ship_classes = [("CARRIER", 5), ("BATTLESHIP", 4), ("CRUISER", 3),
                    ("SUBMARINE", 3), ("DESTROYER", 2)]
    t = Targeting(board_size=10, ship_classes=ship_classes)
    # Sink destroyer (2) and one cruiser (3)
    t.update(0, 0, "hit"); t.update(0, 1, "sunk", sunk_ship_size=2)
    t.update(2, 0, "hit"); t.update(2, 1, "hit"); t.update(2, 2, "sunk", sunk_ship_size=3)
    remaining = t._remaining_ships()
    assert sorted(remaining) == sorted([5, 4, 3])


def test_enumeration_solver_hunts_via_prob_map():
    """
    With ship_classes, a hit should make adjacent cells the highest-probability
    cells — the enumeration-based solver handles orientation inference without
    an explicit hunt stack.
    """
    ship_classes = [("CARRIER", 5), ("BATTLESHIP", 4), ("CRUISER", 3),
                    ("SUBMARINE", 3), ("DESTROYER", 2)]
    t = Targeting(board_size=10, ship_classes=ship_classes)
    t.update(5, 5, "hit")
    # Adjacent cells must be most probable (many ships can include them + the hit)
    played = t._played()
    candidates = [(r, c) for r in range(10) for c in range(10) if (r,c) not in played]
    best = max(candidates, key=lambda c: t.prob[c[0]][c[1]])
    assert best in {(5, 4), (5, 6), (4, 5), (6, 5)}


def test_enumeration_solver_infers_orientation():
    """
    Two aligned hits should concentrate probability in that axis — only
    placements covering both hits survive the hunt-mode filter.
    """
    ship_classes = [("CARRIER", 5), ("BATTLESHIP", 4), ("CRUISER", 3),
                    ("SUBMARINE", 3), ("DESTROYER", 2)]
    t = Targeting(board_size=10, ship_classes=ship_classes)
    t.update(5, 4, "hit")
    t.update(5, 5, "hit")
    # Only horizontal placements cover both (5,4) and (5,5)
    # → horizontal extensions should dominate
    played = t._played()
    candidates = [(r, c) for r in range(10) for c in range(10) if (r, c) not in played]
    best5 = sorted(candidates, key=lambda c: t.prob[c[0]][c[1]], reverse=True)[:5]
    rows = {r for r, _ in best5}
    # All top-5 candidates should be in the same row (5) — orientation inferred
    assert rows == {5}


def test_parity_does_not_affect_hunt_or_exploit(t):
    """Hunt stack and priority queue must bypass parity — only blind sweep respects it."""
    # Known target at odd-parity cell (1,0): (1+0)%2=1
    t.inject_known_targets([(1, 0)])
    row, col = t.next_move()
    assert (row, col) == (1, 0)  # priority queue ignores parity

    t.update(1, 0, "hit")    # hit pushes (0,0),(2,0),(1,1) to hunt_stack
    hunt_move = t.next_move()
    assert hunt_move in {(0, 0), (2, 0), (1, 1)}
