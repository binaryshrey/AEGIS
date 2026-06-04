import pytest
from engine.strategies.placement import Placement, DEFAULT_SHIP_CLASSES

BOARD_SIZE = 10
TOTAL_CELLS = sum(size for _, size in DEFAULT_SHIP_CLASSES)  # 17


def _all_cells(placements: list[dict]) -> list[tuple]:
    """Expand placement dicts to (row, col) cell tuples."""
    cells = []
    for p in placements:
        size = {"CARRIER": 5, "BATTLESHIP": 4, "CRUISER": 3, "SUBMARINE": 3, "DESTROYER": 2}[p["shipClass"]]
        if p["orientation"] == "HORIZONTAL":
            cells += [(p["startRow"], p["startCol"] + i) for i in range(size)]
        else:
            cells += [(p["startRow"] + i, p["startCol"]) for i in range(size)]
    return cells


def test_no_ship_overlap():
    p = Placement(board_size=BOARD_SIZE)
    cells = _all_cells(p.place())
    assert len(cells) == len(set(cells)), "Ships overlap"


def test_all_cells_within_board():
    p = Placement(board_size=BOARD_SIZE)
    for _ in range(20):
        for row, col in _all_cells(p.place()):
            assert 0 <= row < BOARD_SIZE
            assert 0 <= col < BOARD_SIZE


def test_correct_total_cells():
    p = Placement(board_size=BOARD_SIZE)
    assert len(_all_cells(p.place())) == TOTAL_CELLS


def test_returns_five_ships_with_correct_classes():
    p = Placement(board_size=BOARD_SIZE)
    placements = p.place()
    assert len(placements) == 5
    classes = {pl["shipClass"] for pl in placements}
    assert classes == {"CARRIER", "BATTLESHIP", "CRUISER", "SUBMARINE", "DESTROYER"}


def test_placement_format():
    """Each placement must have the required real-API fields."""
    p = Placement(board_size=BOARD_SIZE)
    for pl in p.place():
        assert "shipClass"   in pl
        assert "orientation" in pl
        assert "startRow"    in pl
        assert "startCol"    in pl
        assert pl["orientation"] in ("HORIZONTAL", "VERTICAL")


def test_adaptive_avoids_dangerous_squares():
    """Ships should not be placed on squares in the avoid set."""
    # avoid entire top 5 rows — ships must land in rows 5-9
    avoid = {(row, col) for row in range(5) for col in range(BOARD_SIZE)}
    p = Placement(board_size=BOARD_SIZE)
    for _ in range(30):
        for row, col in _all_cells(p.place(avoid=avoid)):
            assert (row, col) not in avoid, f"Placed on avoided square ({row},{col})"


def test_placement_randomness():
    """Two placements should not always be identical."""
    p = Placement(board_size=BOARD_SIZE)
    results = [tuple(sorted((pl["shipClass"], pl["startRow"], pl["startCol"]) for pl in p.place())) for _ in range(10)]
    assert len(set(results)) > 1, "Placement is not random"


def _orthogonal_adjacent(cells: list[tuple]) -> bool:
    """Return True if any two cells share an orthogonal edge."""
    cell_set = set(cells)
    for r, c in cells:
        for dr, dc in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nb = (r + dr, c + dc)
            if nb in cell_set and nb != (r, c):
                # Neighbour must belong to a different ship (not the same ship cell)
                # We need to check that (r,c) and nb aren't on the same ship.
                # We can't easily do that here — instead check in the caller.
                return True
    return False


def test_no_adjacency_flag_prevents_adjacent_ships():
    """With allow_adjacency=False, no two ships should share an orthogonal edge."""
    for _ in range(30):
        p = Placement(board_size=BOARD_SIZE, allow_adjacency=False)
        placements = p.place()
        # Build per-ship cell sets
        ship_cells_list = []
        for pl in placements:
            size = {"CARRIER": 5, "BATTLESHIP": 4, "CRUISER": 3,
                    "SUBMARINE": 3, "DESTROYER": 2}[pl["shipClass"]]
            if pl["orientation"] == "HORIZONTAL":
                cells = {(pl["startRow"], pl["startCol"] + i) for i in range(size)}
            else:
                cells = {(pl["startRow"] + i, pl["startCol"]) for i in range(size)}
            ship_cells_list.append(cells)
        # For each pair of ships, no cell of one should be orthogonally adjacent to
        # a cell of the other.
        for i in range(len(ship_cells_list)):
            for j in range(i + 1, len(ship_cells_list)):
                for r, c in ship_cells_list[i]:
                    for dr, dc in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                        assert (r + dr, c + dc) not in ship_cells_list[j], (
                            f"Ships {i} and {j} are orthogonally adjacent"
                        )
