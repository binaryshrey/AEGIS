import random

# Default ship configuration matching real API
DEFAULT_SHIP_CLASSES = [
    ("CARRIER",    5),
    ("BATTLESHIP", 4),
    ("CRUISER",    3),
    ("SUBMARINE",  3),
    ("DESTROYER",  2),
]

# Minimum gap (cells) between ships — reduces collateral from adjacent hunting
_MIN_GAP = 1


class Placement:
    def __init__(self, board_size: int, ship_classes: list[tuple] = None,
                 allow_adjacency: bool = True):
        self.size = board_size
        self.ship_classes = ship_classes or DEFAULT_SHIP_CLASSES
        # If the competition rules forbid adjacent ships, we never relax the
        # 1-cell buffer — Phase 2 is skipped to avoid ATTEMPT_DISQUALIFIED.
        self.allow_adjacency = allow_adjacency

    def place(self, avoid: set[tuple] = None, shot_frequency=None,
              num_candidates: int = 50) -> list[dict]:
        """
        Returns list of placement dicts:
          {shipClass, orientation, startRow, startCol}
        Avoids cells in the `avoid` set (dangerous squares from opponent firing history).
        Uses edge-biased placement and ship spacing for survival.

        If *shot_frequency* is provided (a 2D indexable grid, e.g. numpy array,
        of opponent shot frequencies per cell), generates *num_candidates* random
        valid placements and selects the one whose ship cells have the lowest
        total frequency score — placing ships where the opponent shoots least.
        """
        if shot_frequency is not None and num_candidates > 1:
            best_placements = None
            best_score = float("inf")
            for _ in range(num_candidates):
                candidate = self._generate_one_placement(avoid)
                score = self._score_placement(candidate, shot_frequency)
                if score < best_score:
                    best_score = score
                    best_placements = candidate
            return best_placements
        return self._generate_one_placement(avoid)

    def _generate_one_placement(self, avoid: set[tuple] = None) -> list[dict]:
        """Generate a single valid random placement."""
        avoid    = avoid or set()
        occupied: set[tuple] = set()
        buffer:   set[tuple] = set()   # 1-cell gap around placed ships
        placements = []

        for ship_class, size in self.ship_classes:
            orientation, start_row, start_col = self._place_one(
                size, occupied, buffer, avoid,
            )
            cells = self._cells(orientation, start_row, start_col, size)
            occupied.update(cells)
            # Add buffer zone around this ship (neighbors not occupied by ships)
            for r, c in cells:
                for dr in range(-_MIN_GAP, _MIN_GAP + 1):
                    for dc in range(-_MIN_GAP, _MIN_GAP + 1):
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < self.size and 0 <= nc < self.size:
                            buffer.add((nr, nc))
            buffer -= occupied  # don't block own cells
            placements.append({
                "shipClass":   ship_class,
                "orientation": orientation,
                "startRow":    start_row,
                "startCol":    start_col,
            })

        return placements

    def _score_placement(self, placements: list[dict], shot_frequency) -> float:
        """Sum shot_frequency values for all cells occupied by ships."""
        total = 0.0
        for p in placements:
            size = dict(self.ship_classes)[p["shipClass"]]
            cells = self._cells(p["orientation"], p["startRow"], p["startCol"], size)
            for r, c in cells:
                total += shot_frequency[r][c]
        return total

    def _cells(self, orientation: str, start_row: int, start_col: int, size: int) -> list[tuple]:
        if orientation == "HORIZONTAL":
            return [(start_row, start_col + i) for i in range(size)]
        else:
            return [(start_row + i, start_col) for i in range(size)]

    def _place_one(self, size: int, occupied: set, buffer: set, avoid: set,
                   attempts: int = 500) -> tuple[str, int, int]:
        # Phase 1: respect avoid + buffer (spaced apart, away from danger)
        for _ in range(attempts):
            orientation, start_row, start_col = self._random_position(size)
            cells = set(self._cells(orientation, start_row, start_col, size))
            if not cells & occupied and not cells & buffer and not cells & avoid:
                return orientation, start_row, start_col

        # Phase 2: relax buffer (allow adjacent ships, still avoid danger).
        # Skipped when the competition rules forbid adjacency — entering Phase 2
        # there would produce an illegal placement and trigger disqualification.
        if self.allow_adjacency:
            for _ in range(attempts):
                orientation, start_row, start_col = self._random_position(size)
                cells = set(self._cells(orientation, start_row, start_col, size))
                if not cells & occupied and not cells & avoid:
                    return orientation, start_row, start_col

        # Phase 3: relax avoid (not enough room respecting dangerous squares)
        # When adjacency is forbidden, still enforce buffer to avoid DQ.
        if avoid:
            for _ in range(attempts):
                orientation, start_row, start_col = self._random_position(size)
                cells = set(self._cells(orientation, start_row, start_col, size))
                if not cells & occupied:
                    if not self.allow_adjacency and (cells & buffer):
                        continue  # adjacency forbidden — keep buffer
                    return orientation, start_row, start_col

        raise RuntimeError(f"Cannot place ship of size {size} — board may be full")

    def _random_position(self, size: int) -> tuple[str, int, int]:
        """
        Edge-biased random position.  Ships touching board edges are harder
        for random opponents to find (fewer approach angles) and can't be
        hunted from one side.
        """
        if random.choice([True, False]):
            return (
                "HORIZONTAL",
                self._edge_biased_coord(self.size),
                random.randint(0, self.size - size),
            )
        else:
            return (
                "VERTICAL",
                random.randint(0, self.size - size),
                self._edge_biased_coord(self.size),
            )

    @staticmethod
    def _edge_biased_coord(board_size: int) -> int:
        """
        Returns a coordinate biased toward edges (rows 0, 1, board_size-2, board_size-1).
        ~60% edge, ~40% interior — enough randomness to stay unpredictable.
        """
        if random.random() < 0.6:
            return random.choice([0, 1, board_size - 2, board_size - 1])
        return random.randint(0, board_size - 1)
