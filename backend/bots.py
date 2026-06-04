"""
25 bot opponents with varied behaviors for competition-grade stress testing.

Roster:
  5 fixed     — deterministic placement + firing (fully exploitable)
  5 rotating  — cycle through N layouts (breaks naive exploit)
  3 drifting  — ships shift slightly each game
  3 noisy     — 90% deterministic, 10% random (defeats exploiters)
  3 adaptive  — learn from player's shots, move ships away
  3 anti-heatmap — intentionally place in lowest-frequency regions
  3 probability — strong opponents using occupancy-based firing

Matches real API: mix of SCOUT (base 14) + WARSHIP (base 15).
"""
import random
from collections import Counter

BOARD_SIZE = 10

SHIP_CLASSES = [
    ("CARRIER",    5),
    ("BATTLESHIP", 4),
    ("CRUISER",    3),
    ("SUBMARINE",  3),
    ("DESTROYER",  2),
]

SINK_BONUSES = {
    "CARRIER":    10,
    "BATTLESHIP":  8,
    "CRUISER":     7,
    "SUBMARINE":   6,
    "DESTROYER":   4,
}


# ── Placement helpers ────────────────────────────────────────────────────────

def _random_placement(seed=None):
    """Returns list of (ship_class, cells) for all ships."""
    rng = random.Random(seed)
    occupied = set()
    result = []
    for ship_class, size in SHIP_CLASSES:
        for _ in range(1000):
            if rng.choice([True, False]):
                row = rng.randint(0, BOARD_SIZE - 1)
                col = rng.randint(0, BOARD_SIZE - size)
                cells = [(row, col + i) for i in range(size)]
            else:
                row = rng.randint(0, BOARD_SIZE - size)
                col = rng.randint(0, BOARD_SIZE - 1)
                cells = [(row + i, col) for i in range(size)]
            if not set(cells) & occupied:
                occupied.update(cells)
                result.append((ship_class, cells))
                break
    return result


def _seeded_layouts(seeds: list[int]) -> list[list]:
    """Pre-generate multiple layouts from different seeds."""
    return [_random_placement(s) for s in seeds]


def _drift_placement(base_layout: list, offset: int) -> list:
    """Shift each ship by `offset` columns (wrapping), keeping valid positions."""
    result = []
    occupied = set()
    for ship_class, cells in base_layout:
        shifted = []
        for r, c in cells:
            nc = (c + offset) % BOARD_SIZE
            shifted.append((r, nc))
        # Validate: all cells in-bounds, no overlaps, ship contiguous
        if set(shifted) & occupied:
            # Fallback: keep original
            shifted = list(cells)
        # Check contiguity (row or col must be constant)
        rows = {r for r, c in shifted}
        cols = {c for r, c in shifted}
        if len(rows) > 1 and len(cols) > 1:
            shifted = list(cells)
        if set(shifted) & occupied:
            shifted = list(cells)
        occupied.update(shifted)
        result.append((ship_class, shifted))
    return result


def _avoid_cells_placement(avoid: set[tuple], rng: random.Random) -> list:
    """Place ships avoiding the given cells as much as possible."""
    occupied = set()
    result = []
    for ship_class, size in SHIP_CLASSES:
        best_cells = None
        best_overlap = float('inf')
        for _ in range(200):
            if rng.choice([True, False]):
                row = rng.randint(0, BOARD_SIZE - 1)
                col = rng.randint(0, BOARD_SIZE - size)
                cells = [(row, col + i) for i in range(size)]
            else:
                row = rng.randint(0, BOARD_SIZE - size)
                col = rng.randint(0, BOARD_SIZE - 1)
                cells = [(row + i, col) for i in range(size)]
            if set(cells) & occupied:
                continue
            overlap = len(set(cells) & avoid)
            if overlap < best_overlap:
                best_overlap = overlap
                best_cells = cells
                if overlap == 0:
                    break
        if best_cells is None:
            best_cells = _random_placement(rng.randint(0, 99999))
            # Fallback: just return random
            return best_cells
        occupied.update(best_cells)
        result.append((ship_class, best_cells))
    return result


def _sparse_placement(rng: random.Random) -> list:
    """Maximize distance between ships — spread across board."""
    # Try to place ships in different quadrants
    quadrants = [(0, 0), (0, 5), (5, 0), (5, 5), (2, 2)]
    occupied = set()
    result = []
    for i, (ship_class, size) in enumerate(SHIP_CLASSES):
        qr, qc = quadrants[i % len(quadrants)]
        placed = False
        for _ in range(200):
            if rng.choice([True, False]):
                row = rng.randint(qr, min(qr + 4, BOARD_SIZE - 1))
                col = rng.randint(qc, min(qc + 4, BOARD_SIZE - size))
                cells = [(row, col + j) for j in range(size)]
            else:
                row = rng.randint(qr, min(qr + 4, BOARD_SIZE - size))
                col = rng.randint(qc, min(qc + 4, BOARD_SIZE - 1))
                cells = [(row + j, col) for j in range(size)]
            if not set(cells) & occupied and all(0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE for r, c in cells):
                occupied.update(cells)
                result.append((ship_class, cells))
                placed = True
                break
        if not placed:
            # Fallback to random
            for _ in range(1000):
                if rng.choice([True, False]):
                    row = rng.randint(0, BOARD_SIZE - 1)
                    col = rng.randint(0, BOARD_SIZE - size)
                    cells = [(row, col + j) for j in range(size)]
                else:
                    row = rng.randint(0, BOARD_SIZE - size)
                    col = rng.randint(0, BOARD_SIZE - 1)
                    cells = [(row + j, col) for j in range(size)]
                if not set(cells) & occupied:
                    occupied.update(cells)
                    result.append((ship_class, cells))
                    break
    return result


def _anti_parity_placement(rng: random.Random, target_parity: int = 1) -> list:
    """Place ships favoring cells where (row+col)%2 == target_parity."""
    occupied = set()
    result = []
    for ship_class, size in SHIP_CLASSES:
        best_cells = None
        best_score = -1
        for _ in range(300):
            if rng.choice([True, False]):
                row = rng.randint(0, BOARD_SIZE - 1)
                col = rng.randint(0, BOARD_SIZE - size)
                cells = [(row, col + i) for i in range(size)]
            else:
                row = rng.randint(0, BOARD_SIZE - size)
                col = rng.randint(0, BOARD_SIZE - 1)
                cells = [(row + i, col) for i in range(size)]
            if set(cells) & occupied:
                continue
            # Score = how many cells are on the target parity
            score = sum(1 for r, c in cells if (r + c) % 2 == target_parity)
            if score > best_score:
                best_score = score
                best_cells = cells
        if best_cells:
            occupied.update(best_cells)
            result.append((ship_class, best_cells))
    return result


# ── Firing helpers ───────────────────────────────────────────────────────────

def _checkerboard_shots():
    return [(row, col) for row in range(BOARD_SIZE) for col in range(BOARD_SIZE) if (row + col) % 2 == 0]

def _row_sweep_shots():
    return [(row, col) for row in range(BOARD_SIZE) for col in range(BOARD_SIZE)]

def _column_sweep_shots():
    return [(row, col) for col in range(BOARD_SIZE) for row in range(BOARD_SIZE)]

def _diagonal_shots():
    shots = []
    for d in range(2 * BOARD_SIZE - 1):
        for row in range(BOARD_SIZE):
            col = d - row
            if 0 <= col < BOARD_SIZE:
                shots.append((row, col))
    return shots

def _reverse_checkerboard_shots():
    return [(row, col) for row in range(BOARD_SIZE) for col in range(BOARD_SIZE) if (row + col) % 2 == 1]

def _spiral_shots():
    """Spiral inward from edges."""
    shots = []
    visited = set()
    r, c = 0, 0
    dr, dc = 0, 1
    for _ in range(BOARD_SIZE * BOARD_SIZE):
        if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and (r, c) not in visited:
            shots.append((r, c))
            visited.add((r, c))
        nr, nc = r + dr, c + dc
        if not (0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE) or (nr, nc) in visited:
            dr, dc = dc, -dr  # turn right
            nr, nc = r + dr, c + dc
        r, c = nr, nc
    # Fill any remaining
    for row in range(BOARD_SIZE):
        for col in range(BOARD_SIZE):
            if (row, col) not in visited:
                shots.append((row, col))
    return shots


def _probability_shot(rng: random.Random, played: set, hit_cells: set, sunk_cells: set) -> tuple:
    """
    Occupancy-based probability targeting — mimics a strong competitor.
    Counts how many legal ship placements cover each cell, picks highest.
    """
    unsunk_hits = hit_cells - sunk_cells

    # If we have unsunk hits, target adjacent cells first (hunt mode)
    if unsunk_hits:
        candidates = []
        for r, c in unsunk_hits:
            for dr, dc in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nr, nc = r + dr, c + dc
                if 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE and (nr, nc) not in played:
                    candidates.append((nr, nc))
        if candidates:
            return rng.choice(candidates)

    # Occupancy counting over remaining cells
    scores = {}
    misses = played - hit_cells
    for ship_class, size in SHIP_CLASSES:
        # Horizontal
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE - size + 1):
                cells = [(row, col + i) for i in range(size)]
                if any((r, c) in misses for r, c in cells):
                    continue
                if any((r, c) in sunk_cells for r, c in cells):
                    continue
                for r, c in cells:
                    if (r, c) not in played:
                        scores[(r, c)] = scores.get((r, c), 0) + 1
        # Vertical
        for row in range(BOARD_SIZE - size + 1):
            for col in range(BOARD_SIZE):
                cells = [(row + i, col) for i in range(size)]
                if any((r, c) in misses for r, c in cells):
                    continue
                if any((r, c) in sunk_cells for r, c in cells):
                    continue
                for r, c in cells:
                    if (r, c) not in played:
                        scores[(r, c)] = scores.get((r, c), 0) + 1

    if scores:
        max_score = max(scores.values())
        best = [cell for cell, s in scores.items() if s == max_score]
        return rng.choice(best)

    # Fallback
    available = [(r, c) for r in range(BOARD_SIZE) for c in range(BOARD_SIZE) if (r, c) not in played]
    return rng.choice(available) if available else (0, 0)


# ── Bot classes ──────────────────────────────────────────────────────────────

class Bot:
    """Base bot — fixed or random placement, fixed or random firing."""

    def __init__(self, bot_id: str, display_name: str, opponent_class: str,
                 base_score: int, placement_seed: int | None, firing_fn):
        self.id = bot_id
        self.display_name = display_name
        self.opponent_class = opponent_class
        self.base_score = base_score
        self.placement_seed = placement_seed
        self.firing_fn = firing_fn
        self._firing_sequence = None
        self.game_count = 0

    def get_ship_placement(self) -> list[tuple]:
        self.game_count += 1
        return _random_placement(self.placement_seed)

    def get_next_shot(self, turn: int, rng: random.Random, played: set) -> tuple:
        if self.firing_fn is not None:
            if self._firing_sequence is None:
                self._firing_sequence = self.firing_fn()
            for shot in self._firing_sequence[turn:]:
                if shot not in played:
                    return shot
        available = [
            (row, col)
            for row in range(BOARD_SIZE)
            for col in range(BOARD_SIZE)
            if (row, col) not in played
        ]
        return rng.choice(available) if available else (0, 0)

    def reset(self):
        self._firing_sequence = None

    def record_opponent_shots(self, shots: list[tuple]):
        """Called after each game with the opponent's shot coordinates."""
        pass


class RotatingBot(Bot):
    """Cycles through N pre-generated layouts. Breaks naive exploit detection."""

    def __init__(self, bot_id, display_name, opponent_class, base_score,
                 layout_seeds: list[int], firing_fn=None):
        super().__init__(bot_id, display_name, opponent_class, base_score, None, firing_fn)
        self._layouts = _seeded_layouts(layout_seeds)

    def get_ship_placement(self):
        layout = self._layouts[self.game_count % len(self._layouts)]
        self.game_count += 1
        return layout


class DriftingBot(Bot):
    """Ships shift slightly each game — not random, not fixed."""

    def __init__(self, bot_id, display_name, opponent_class, base_score,
                 base_seed: int, firing_fn=None):
        super().__init__(bot_id, display_name, opponent_class, base_score, None, firing_fn)
        self._base_layout = _random_placement(base_seed)

    def get_ship_placement(self):
        offset = self.game_count  # shift by game number
        self.game_count += 1
        return _drift_placement(self._base_layout, offset)


class NoisyBot(Bot):
    """90% deterministic, 10% random. Defeats pure exploiters."""

    def __init__(self, bot_id, display_name, opponent_class, base_score,
                 fixed_seed: int, noise_pct: float = 0.1, firing_fn=None):
        super().__init__(bot_id, display_name, opponent_class, base_score, None, firing_fn)
        self._fixed_seed = fixed_seed
        self._noise_pct = noise_pct
        self._rng = random.Random(bot_id)

    def get_ship_placement(self):
        self.game_count += 1
        if self._rng.random() < self._noise_pct:
            return _random_placement()  # truly random
        return _random_placement(self._fixed_seed)


class AdaptiveBot(Bot):
    """
    Learns from player's shots — moves ships away from frequently targeted cells.
    After game 1, your exploit strategy starts failing.
    """

    def __init__(self, bot_id, display_name, opponent_class, base_score,
                 initial_seed: int, firing_fn=None):
        super().__init__(bot_id, display_name, opponent_class, base_score, None, firing_fn)
        self._initial_seed = initial_seed
        self._opponent_shot_history: list[list[tuple]] = []
        self._rng = random.Random(bot_id)

    def get_ship_placement(self):
        self.game_count += 1
        if not self._opponent_shot_history:
            return _random_placement(self._initial_seed)

        # Build frequency map of opponent's first N shots (where they look first)
        freq = Counter()
        for game_shots in self._opponent_shot_history:
            # Weight early shots more — those reveal the opponent's targeting prior
            for i, shot in enumerate(game_shots[:30]):
                freq[shot] += max(1, 3 - i // 10)

        # Avoid the hottest cells
        hot_cells = {cell for cell, count in freq.items()
                     if count >= max(2, len(self._opponent_shot_history))}
        return _avoid_cells_placement(hot_cells, self._rng)

    def record_opponent_shots(self, shots: list[tuple]):
        self._opponent_shot_history.append(shots)


class AntiHeatmapBot(Bot):
    """
    Intentionally places ships in lowest-frequency regions.
    Games 1-5: bottom-right. Games 6-10: top-left. Games 11+: center.
    Heatmap learners start chasing ghosts.
    """

    def __init__(self, bot_id, display_name, opponent_class, base_score,
                 firing_fn=None):
        super().__init__(bot_id, display_name, opponent_class, base_score, None, firing_fn)
        self._rng = random.Random(bot_id)
        # Define region preferences that rotate
        self._regions = [
            # bottom-right
            lambda rng: self._region_placement(rng, row_range=(5, 9), col_range=(5, 9)),
            # top-left
            lambda rng: self._region_placement(rng, row_range=(0, 4), col_range=(0, 4)),
            # center
            lambda rng: self._region_placement(rng, row_range=(2, 7), col_range=(2, 7)),
            # top-right
            lambda rng: self._region_placement(rng, row_range=(0, 4), col_range=(5, 9)),
            # bottom-left
            lambda rng: self._region_placement(rng, row_range=(5, 9), col_range=(0, 4)),
        ]

    def _region_placement(self, rng, row_range, col_range):
        """Try to place ships within a region, fallback to random if impossible."""
        occupied = set()
        result = []
        r_lo, r_hi = row_range
        c_lo, c_hi = col_range
        for ship_class, size in SHIP_CLASSES:
            placed = False
            for _ in range(300):
                if rng.choice([True, False]):
                    row = rng.randint(r_lo, r_hi)
                    col = rng.randint(c_lo, max(c_lo, c_hi - size + 1))
                    if col + size - 1 > c_hi:
                        continue
                    cells = [(row, col + i) for i in range(size)]
                else:
                    row = rng.randint(r_lo, max(r_lo, r_hi - size + 1))
                    col = rng.randint(c_lo, c_hi)
                    if row + size - 1 > r_hi:
                        continue
                    cells = [(row + i, col) for i in range(size)]
                if all(0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE for r, c in cells):
                    if not set(cells) & occupied:
                        occupied.update(cells)
                        result.append((ship_class, cells))
                        placed = True
                        break
            if not placed:
                # Fallback: anywhere on board
                for _ in range(1000):
                    if rng.choice([True, False]):
                        row = rng.randint(0, BOARD_SIZE - 1)
                        col = rng.randint(0, BOARD_SIZE - size)
                        cells = [(row, col + i) for i in range(size)]
                    else:
                        row = rng.randint(0, BOARD_SIZE - size)
                        col = rng.randint(0, BOARD_SIZE - 1)
                        cells = [(row + i, col) for i in range(size)]
                    if not set(cells) & occupied:
                        occupied.update(cells)
                        result.append((ship_class, cells))
                        break
        return result

    def get_ship_placement(self):
        region_idx = (self.game_count // 5) % len(self._regions)
        self.game_count += 1
        return self._regions[region_idx](self._rng)


class ProbabilityBot(Bot):
    """
    Strong opponent using occupancy-based firing — mimics a real competitor.
    Tracks hits/sinks and uses probability density to target.
    """

    def __init__(self, bot_id, display_name, opponent_class, base_score,
                 placement_seed: int | None = None):
        super().__init__(bot_id, display_name, opponent_class, base_score, placement_seed, None)
        self._hit_cells: set[tuple] = set()
        self._sunk_cells: set[tuple] = set()
        self._rng = random.Random(bot_id)

    def get_next_shot(self, turn: int, rng: random.Random, played: set) -> tuple:
        return _probability_shot(self._rng, played, self._hit_cells, self._sunk_cells)

    def notify_shot_result(self, row: int, col: int, outcome: str):
        """Called by game engine after each bot shot resolves."""
        if outcome in ("HIT", "SINK"):
            self._hit_cells.add((row, col))
        if outcome == "SINK":
            # Mark all connected hits as sunk
            self._sunk_cells.add((row, col))

    def reset(self):
        super().reset()
        self._hit_cells.clear()
        self._sunk_cells.clear()


class AdaptiveFiringBot(Bot):
    """
    Changes firing pattern based on whether it won or lost last game.
    Game 1: center-first. Game 2 (if lost): edge-first. Game 3: checkerboard.
    Defeats firing-pattern learning.
    """

    def __init__(self, bot_id, display_name, opponent_class, base_score,
                 placement_seed: int | None = None):
        super().__init__(bot_id, display_name, opponent_class, base_score, placement_seed, None)
        self._patterns = [
            _checkerboard_shots,
            _reverse_checkerboard_shots,
            _spiral_shots,
            _row_sweep_shots,
            _diagonal_shots,
        ]
        self._pattern_idx = 0
        self._last_won = None

    def get_next_shot(self, turn: int, rng: random.Random, played: set) -> tuple:
        if self._firing_sequence is None:
            self._firing_sequence = self._patterns[self._pattern_idx % len(self._patterns)]()
        for shot in self._firing_sequence[turn:]:
            if shot not in played:
                return shot
        available = [(r, c) for r in range(BOARD_SIZE) for c in range(BOARD_SIZE) if (r, c) not in played]
        return rng.choice(available) if available else (0, 0)

    def reset(self):
        super().reset()
        # Rotate pattern each game
        self._pattern_idx += 1


class SparseBot(Bot):
    """Maximizes distance between ships — defeats clustering heuristics."""

    def __init__(self, bot_id, display_name, opponent_class, base_score,
                 firing_fn=None):
        super().__init__(bot_id, display_name, opponent_class, base_score, None, firing_fn)
        self._rng = random.Random(bot_id)

    def get_ship_placement(self):
        self.game_count += 1
        return _sparse_placement(self._rng)


class AntiParityBot(Bot):
    """Places ships on odd-parity cells to defeat checkerboard hunting."""

    def __init__(self, bot_id, display_name, opponent_class, base_score,
                 firing_fn=None):
        super().__init__(bot_id, display_name, opponent_class, base_score, None, firing_fn)
        self._rng = random.Random(bot_id)

    def get_ship_placement(self):
        self.game_count += 1
        return _anti_parity_placement(self._rng, target_parity=1)


# ── Bot roster ───────────────────────────────────────────────────────────────
# 25 bots: stress-tests every assumption the agent could make

BOT_POOL = [
    # 5 fixed — fully exploitable (current scout behavior)
    Bot("scout-01", "Scout Alpha",   "SCOUT", 14, 42, _checkerboard_shots),
    Bot("scout-02", "Scout Bravo",   "SCOUT", 14, 77, _row_sweep_shots),
    Bot("scout-03", "Scout Charlie", "SCOUT", 14, 13, _column_sweep_shots),
    Bot("scout-04", "Scout Delta",   "SCOUT", 14, 99, _diagonal_shots),
    Bot("scout-05", "Scout Echo",    "SCOUT", 14, 55, _checkerboard_shots),

    # 5 rotating — cycle through 3 layouts (exploit must detect rotation)
    RotatingBot("rotating-01", "Rotator Alpha",   "WARSHIP", 15, [42, 77, 13]),
    RotatingBot("rotating-02", "Rotator Bravo",   "WARSHIP", 15, [99, 55, 11]),
    RotatingBot("rotating-03", "Rotator Charlie",  "WARSHIP", 15, [22, 33, 44]),
    RotatingBot("rotating-04", "Rotator Delta",    "WARSHIP", 15, [66, 88, 12]),
    RotatingBot("rotating-05", "Rotator Echo",     "WARSHIP", 15, [10, 20, 30, 40]),

    # 3 drifting — ships shift each game
    DriftingBot("drift-01", "Drifter Alpha",   "WARSHIP", 15, 42),
    DriftingBot("drift-02", "Drifter Bravo",   "WARSHIP", 15, 77),
    DriftingBot("drift-03", "Drifter Charlie",  "WARSHIP", 15, 13),

    # 3 noisy — 90% fixed, 10% random
    NoisyBot("noisy-01", "Noisy Alpha",   "WARSHIP", 15, 42, 0.10),
    NoisyBot("noisy-02", "Noisy Bravo",   "WARSHIP", 15, 77, 0.15),
    NoisyBot("noisy-03", "Noisy Charlie",  "WARSHIP", 15, 13, 0.20),

    # 3 adaptive — learn from player's targeting
    AdaptiveBot("adaptive-01", "Adapter Alpha",   "WARSHIP", 15, 42),
    AdaptiveBot("adaptive-02", "Adapter Bravo",   "WARSHIP", 15, 77),
    AdaptiveBot("adaptive-03", "Adapter Charlie",  "WARSHIP", 15, 13),

    # 3 probability — strong occupancy-based firing
    ProbabilityBot("prob-01", "Solver Alpha",   "WARSHIP", 15),
    ProbabilityBot("prob-02", "Solver Bravo",   "WARSHIP", 15),
    ProbabilityBot("prob-03", "Solver Charlie",  "WARSHIP", 15),

    # 3 special — anti-heatmap, sparse, anti-parity
    AntiHeatmapBot("antiheat-01", "Ghost Alpha", "WARSHIP", 15),
    SparseBot("sparse-01", "Spreader Alpha",     "WARSHIP", 15),
    AntiParityBot("antiparity-01", "Oddball Alpha", "WARSHIP", 15),
]

ROSTER_SIZE = 15  # games per attempt — matches real competition

# BOTS is set per-attempt via pick_roster(); default for rules endpoint
BOTS = BOT_POOL[:ROSTER_SIZE]


def pick_roster() -> list:
    """Pick 15 random bots from the pool for one attempt (simulates real server)."""
    import random
    return random.sample(BOT_POOL, ROSTER_SIZE)
