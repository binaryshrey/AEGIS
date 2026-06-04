"""
Heatmap — partial pattern detection via cell frequency analysis.

Instead of binary "fixed or random", the heatmap tracks how often a ship
occupied each cell across all observed games and produces a probability
surface. This catches everything from fully deterministic bots (spike) to
partially predictable ones (hot regions) to fully random ones (flat).

The heatmap is blended into the targeting probability map — cells that
have historically contained ships get a prior boost before the game starts.
Coordinates are (row, col), 0-indexed.
"""
import numpy as np


class Heatmap:
    """
    Tracks per-cell ship frequency across games for one opponent.
    Built from the opponent's observed ship placements in memory.
    """

    def __init__(self, board_size: int = 10):
        self.size = board_size
        self.counts = np.zeros((board_size, board_size), dtype=float)
        self.games_observed = 0

    def record(self, ship_cells: list):
        """Record one game's worth of ship positions."""
        for cell in ship_cells:
            row, col = int(cell[0]), int(cell[1])
            if 0 <= row < self.size and 0 <= col < self.size:
                self.counts[row][col] += 1
        self.games_observed += 1

    def frequency(self) -> np.ndarray:
        """
        Returns a [size x size] array of ship frequencies (0.0 – 1.0).
        0.0 = never seen a ship here
        1.0 = ship was here in every observed game
        """
        if self.games_observed == 0:
            return np.ones((self.size, self.size)) / (self.size * self.size)
        return self.counts / self.games_observed

    def stability(self) -> float:
        """
        Measures cross-game placement consistency (0.0 = random, 1.0 = fully deterministic).
        Computed as mean squared frequency of occupied cells.
        """
        if self.games_observed < 2:
            return 0.0
        freq = self.counts / self.games_observed
        nonzero = freq[freq > 0]
        if len(nonzero) == 0:
            return 0.0
        return float(np.mean(nonzero ** 2))

    def entropy(self) -> float:
        """Shannon entropy over occupied cells (kept for observability / display)."""
        if self.games_observed == 0:
            return 1.0
        freq = self.counts / self.games_observed
        flat = freq.flatten()
        nonzero = flat[flat > 0]
        if len(nonzero) == 0:
            return 1.0
        nonzero = nonzero / nonzero.sum()
        max_entropy = np.log2(len(nonzero)) if len(nonzero) > 1 else 1.0
        return float(-np.sum(nonzero * np.log2(nonzero)) / max_entropy)

    def hot_cells(self, threshold: float = 0.5) -> list[tuple]:
        """
        Returns cells that appeared in >= threshold fraction of games,
        sorted by frequency descending.
        """
        freq = self.frequency()
        cells = [
            (row, col)
            for row in range(self.size)
            for col in range(self.size)
            if freq[row][col] >= threshold
        ]
        return sorted(cells, key=lambda c: freq[c[0]][c[1]], reverse=True)

    def confidence(self) -> str:
        s = self.stability()
        if s > 0.8:
            return "high"
        elif s > 0.3:
            return "medium"
        else:
            return "low"

    def boost_matrix(self, weight: float = 3.0) -> np.ndarray:
        """
        Returns a multiplier matrix to blend into the targeting prob map.
        Cells with high historical frequency get a weight boost.
        No observations → identity matrix (no effect).
        Cells seen in < 30% of games are treated as noise and get no boost —
        this prevents mildly-patterned opponents from generating false priors.
        """
        if self.games_observed == 0:
            return np.ones((self.size, self.size))
        freq = self.counts / self.games_observed
        # Zero out low-frequency cells — only boost consistently-occupied positions
        masked = np.where(freq >= 0.3, freq, 0.0)
        return 1.0 + (weight - 1.0) * masked

    @classmethod
    def from_model(cls, model, board_size: int = 10) -> "Heatmap":
        """Build a heatmap from an OpponentModel's observed ship placements.
        Skips partial observations (< 9 cells) to avoid diluting frequencies —
        partial data from losses would systematically lower all cell frequencies.
        """
        h = cls(board_size=board_size)
        for placement in model.ship_placements:
            if len(placement) >= 9:
                h.record(placement)
        return h

    def summary(self, opponent_id: str) -> str:
        hot = self.hot_cells(threshold=0.6)
        return (
            f"[HEATMAP] {opponent_id}: stability={self.stability():.2f} ({self.confidence()}) "
            f"| {self.games_observed} games observed "
            f"| {len(hot)} hot cells (≥60% frequency)"
        )
