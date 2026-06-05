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
        self.allow_adjacency = allow_adjacency

    def place(self, avoid: set[tuple] = None, shot_frequency=None,
              num_candidates: int = 50) -> list[dict]:
        """
        Generate num_candidates random valid placements and pick the one
        with the lowest score (avoids opponent hot zones, maximizes spread).

        If shot_frequency is None, returns a single random placement.
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
            for r, c in cells:
                for dr in range(-_MIN_GAP, _MIN_GAP + 1):
                    for dc in range(-_MIN_GAP, _MIN_GAP + 1):
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < self.size and 0 <= nc < self.size:
                            buffer.add((nr, nc))
            buffer -= occupied
            placements.append({
                "shipClass":   ship_class,
                "orientation": orientation,
                "startRow":    start_row,
                "startCol":    start_col,
            })

        return placements

    # Ships with highest sinking penalty should be placed in safest cells.
    # Weights proportional to real API sink bonuses + class loss penalties.
    _SHIP_PRIORITY = {
        "CARRIER": 2.0, "BATTLESHIP": 1.6, "CRUISER": 1.4,
        "SUBMARINE": 1.2, "DESTROYER": 1.0,
    }

    def _score_placement(self, placements: list[dict], shot_frequency) -> float:
        """
        Score = frequency exposure - spread bonus.
        Lower is better.

        Frequency exposure: sum of opponent shot frequency at each ship cell,
        weighted by ship priority (carrier 2x — highest penalty when sunk).

        Spread bonus: pairwise distance between ship centroids.
        Ships far apart are found independently; clustered ships get chain-hunted.
        """
        freq_score = 0.0
        centroids = []
        for p in placements:
            size = dict(self.ship_classes)[p["shipClass"]]
            weight = self._SHIP_PRIORITY.get(p["shipClass"], 1.0)
            cells = self._cells(p["orientation"], p["startRow"], p["startCol"], size)
            cr = sum(r for r, c in cells) / len(cells)
            cc = sum(c for r, c in cells) / len(cells)
            centroids.append((cr, cc))
            for r, c in cells:
                freq_score += shot_frequency[r][c] * weight

        # Spread bonus: sum of pairwise Euclidean distances between centroids.
        # Max possible ~63 on 10x10. Weight at 0.15 so it meaningfully competes
        # with frequency score (~17 cells * ~0.5 avg freq = ~8.5).
        spread = 0.0
        for i in range(len(centroids)):
            for j in range(i + 1, len(centroids)):
                dr = centroids[i][0] - centroids[j][0]
                dc = centroids[i][1] - centroids[j][1]
                spread += (dr * dr + dc * dc) ** 0.5
        spread_bonus = spread * 0.15

        return freq_score - spread_bonus

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
        if self.allow_adjacency:
            for _ in range(attempts):
                orientation, start_row, start_col = self._random_position(size)
                cells = set(self._cells(orientation, start_row, start_col, size))
                if not cells & occupied and not cells & avoid:
                    return orientation, start_row, start_col

        # Phase 3: relax avoid (not enough room respecting dangerous squares)
        if avoid:
            for _ in range(attempts):
                orientation, start_row, start_col = self._random_position(size)
                cells = set(self._cells(orientation, start_row, start_col, size))
                if not cells & occupied:
                    if not self.allow_adjacency and (cells & buffer):
                        continue
                    return orientation, start_row, start_col

        raise RuntimeError(f"Cannot place ship of size {size} — board may be full")

    def _random_position(self, size: int) -> tuple[str, int, int]:
        """
        Fully uniform random position. No edge bias — edge bias is exploitable
        by smart opponents who know agents tend to hide on edges.
        Unpredictability is the best defense against adaptive opponents.
        """
        if random.choice([True, False]):
            return (
                "HORIZONTAL",
                random.randint(0, self.size - 1),
                random.randint(0, self.size - size),
            )
        else:
            return (
                "VERTICAL",
                random.randint(0, self.size - size),
                random.randint(0, self.size - 1),
            )
