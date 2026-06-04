import json
import os

import numpy as np


_MAX_HISTORY = 30  # keep last N entries per list — enough for pattern detection


class OpponentModel:
    def __init__(self, opponent_id: str):
        self.id = opponent_id
        self.games_played = 0
        self.wins = 0
        self.losses = 0
        self.ship_placements: list[list] = []
        self.firing_sequences: list[list] = []
        self.move_history: list[int] = []   # persisted — survives restarts

    def record_game(self, their_shots: list, their_ships: list, we_won: bool,
                    record_placement: bool = True):
        self.firing_sequences.append([list(s) for s in their_shots])
        if len(self.firing_sequences) > _MAX_HISTORY:
            self.firing_sequences = self.firing_sequences[-_MAX_HISTORY:]
        # Only append placement when the server actually returned ship positions.
        # Appending an empty list would corrupt is_fixed_placement() comparisons.
        if record_placement and their_ships:
            self.ship_placements.append([list(s) for s in their_ships])
            if len(self.ship_placements) > _MAX_HISTORY:
                self.ship_placements = self.ship_placements[-_MAX_HISTORY:]
        self.games_played += 1
        if we_won:
            self.wins += 1
        else:
            self.losses += 1

    def record_moves(self, move_count: int):
        """Track moves-per-game for baseline calculation. Persisted to disk."""
        self.move_history.append(move_count)
        if len(self.move_history) > _MAX_HISTORY:
            self.move_history = self.move_history[-_MAX_HISTORY:]

    def last_moves(self) -> int | None:
        """Moves in the most recent game — used as baseline for improvement comparison."""
        return self.move_history[-1] if self.move_history else None

    def is_fixed_placement(self, min_games: int = 3) -> bool:
        if len(self.ship_placements) < min_games:
            return False
        # Group by length — partial data from losses has fewer cells.
        # Use the largest consistent group for detection.
        # Skip empty placements entirely.
        # Partial data (< 9 cells) is too sparse to confirm fixed placement
        # reliably — could just mean we always find the same ship first.
        by_len: dict[int, list] = {}
        for p in self.ship_placements:
            if len(p) >= 9:  # at least ~half the fleet
                by_len.setdefault(len(p), []).append(p)
        if not by_len:
            return False
        # Prefer complete placements (17), otherwise use the most common length
        best_len = 17 if 17 in by_len and len(by_len[17]) >= min_games else max(by_len, key=lambda k: len(by_len[k]))
        group = by_len[best_len]
        if len(group) < min_games:
            return False
        first = sorted(map(tuple, group[0]))
        return all(sorted(map(tuple, p)) == first for p in group[1:])

    def placement_stability(self) -> float:
        """
        Measure how consistent placements are (0.0 = random, 1.0 = fixed).
        Uses Jaccard similarity between consecutive placements.
        Detects drift: if recent placements diverge from earlier ones,
        stability drops even if earlier placements were identical.
        """
        valid = [p for p in self.ship_placements if len(p) >= 9]
        if len(valid) < 2:
            return 0.0
        similarities = []
        base = set(map(tuple, valid[0]))
        for p in valid[1:]:
            current = set(map(tuple, p))
            if not base or not current:
                continue
            jaccard = len(base & current) / len(base | current)
            similarities.append(jaccard)
        if not similarities:
            return 0.0
        # Weight recent observations more heavily (detect drift)
        if len(similarities) > 3:
            recent = similarities[-3:]
            older = similarities[:-3]
            recent_avg = sum(recent) / len(recent)
            older_avg = sum(older) / len(older)
            # If recent similarity is dropping, penalize
            if recent_avg < older_avg - 0.1:
                return recent_avg
        return sum(similarities) / len(similarities)

    def is_fixed_firing(self, min_games: int = 2) -> bool:
        """
        Checks if the bot fires in a deterministic sequence.
        Compares only the common prefix length across all sequences, since
        games end at different turns (sequences are not always the same length).
        """
        if len(self.firing_sequences) < min_games:
            return False
        min_len = min(len(s) for s in self.firing_sequences)
        if min_len == 0:
            return False
        return all(s[:min_len] == self.firing_sequences[0][:min_len]
                   for s in self.firing_sequences)

    def known_targets(self) -> list[tuple] | None:
        if not self.is_fixed_placement() or not self.ship_placements:
            return None
        # Return the longest (most complete) placement observation,
        # grouped by ship (contiguous clusters) with largest ships first
        # so we sink high-value targets early for maximum sink bonuses.
        best = max(self.ship_placements, key=len)
        cells = [tuple(c) for c in best]
        return self._group_by_ship(cells)

    @staticmethod
    def _group_by_ship(cells: list[tuple]) -> list[tuple]:
        """Group cells into contiguous ship clusters, largest first."""
        remaining = set(cells)
        ships: list[list[tuple]] = []
        while remaining:
            seed = next(iter(remaining))
            # BFS to find connected cells
            cluster = set()
            queue = [seed]
            while queue:
                c = queue.pop()
                if c in cluster:
                    continue
                cluster.add(c)
                for dr, dc in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                    nb = (c[0] + dr, c[1] + dc)
                    if nb in remaining and nb not in cluster:
                        queue.append(nb)
            remaining -= cluster
            ships.append(sorted(cluster))
        # Largest ships first (higher sink bonuses)
        ships.sort(key=len, reverse=True)
        result = []
        for ship in ships:
            result.extend(ship)
        return result

    # ------------------------------------------------------------------
    # Opponent classification
    # ------------------------------------------------------------------

    def classify(self) -> str:
        """
        Return the opponent archetype extracted from the opponent ID.
        e.g. "scout-01" → "scout", "antiheat-01" → "antiheat"
        Falls back to stability-based classification if ID has no prefix.
        """
        # Extract type from ID: everything before the last "-NN"
        parts = self.id.rsplit("-", 1)
        if len(parts) == 2 and parts[1].isdigit():
            return parts[0]
        # Fallback: stability-based
        if self.is_fixed_placement():
            return "fixed"
        stability = self.placement_stability()
        if stability >= 0.4:
            return "semi_fixed"
        return "unstable"

    def prediction_accuracy(self) -> float | None:
        """
        Compare heatmap-predicted top-17 cells against the most recent
        actual ship placement.

        Returns overlap ratio (0.0 = no overlap, 1.0 = perfect prediction).
        Returns None if insufficient data (need >= 2 placement entries).
        """
        if len(self.ship_placements) < 2:
            return None
        # Build a frequency map from all placements *except* the last one
        freq: dict[tuple, int] = {}
        history = self.ship_placements[:-1]
        games = 0
        for placement in history:
            if len(placement) >= 9:
                games += 1
                for cell in placement:
                    key = (int(cell[0]), int(cell[1]))
                    freq[key] = freq.get(key, 0) + 1
        if games == 0:
            return None
        # Top-17 predicted cells by frequency
        ranked = sorted(freq.keys(), key=lambda c: freq[c], reverse=True)
        predicted = set(ranked[:17])
        # Actual last placement
        actual = {(int(c[0]), int(c[1])) for c in self.ship_placements[-1]}
        if not actual:
            return None
        overlap = len(predicted & actual)
        return overlap / max(len(actual), 1)

    def is_degrading(self) -> bool:
        """
        Returns True if the last 3 entries in move_history are monotonically
        increasing (each game takes more moves than the previous).
        Requires at least 3 entries.
        """
        if len(self.move_history) < 3:
            return False
        last3 = self.move_history[-3:]
        return last3[0] < last3[1] < last3[2]

    def dangerous_squares(self) -> set[tuple]:
        """
        Squares the opponent fires at frequently in early turns.

        Uses turn-weighted scoring: shots at turn t contribute 1/(t+1) to a
        cell's danger score.  Early shots count far more than late ones because
        a ship destroyed on turn 3 gives the opponent a larger advantage than
        one destroyed on turn 20.

        Window scales with observed data: use median game length (capped at 25)
        so we cover the turns where our ships are still alive and vulnerable.
        """
        if not self.firing_sequences:
            return set()
        # Adaptive window: median sequence length, capped at 25
        lengths = [len(s) for s in self.firing_sequences]
        median_len = sorted(lengths)[len(lengths) // 2]
        window = min(max(median_len, 12), 25)
        score: dict[tuple, float] = {}
        for seq in self.firing_sequences:
            for turn, shot in enumerate(seq[:window]):
                key = tuple(shot)
                # Turn 0 = weight 1.0; turn 1 = 0.5; turn 2 = 0.33 …
                score[key] = score.get(key, 0.0) + 1.0 / (turn + 1)
        # Threshold: equivalent to appearing at turn 0 in ≥50% of games.
        # Using the same 0.5 factor as before keeps backward compatibility
        # with the frequency-based tests while rewarding early-turn consistency.
        threshold = max(0.1, len(self.firing_sequences) * 0.5)
        return {sq for sq, s in score.items() if s >= threshold}

    def shot_frequency_map(self, board_size: int = 10) -> np.ndarray | None:
        """
        Build a 10x10 frequency grid from observed opponent firing sequences.

        Returns None if fewer than 3 games observed (not enough data).
        Each shot at turn t contributes weight 1/(t+1) — early shots are
        weighted more heavily because early hits hurt us more.
        The result is normalized to [0, 1] range.
        """
        if len(self.firing_sequences) < 3:
            return None
        grid = np.zeros((board_size, board_size), dtype=np.float64)
        for seq in self.firing_sequences:
            for turn, shot in enumerate(seq):
                r, c = shot[0], shot[1]
                if 0 <= r < board_size and 0 <= c < board_size:
                    grid[r, c] += 1.0 / (turn + 1)
        max_val = grid.max()
        if max_val > 0:
            grid /= max_val
        return grid

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "games_played": self.games_played,
            "wins": self.wins,
            "losses": self.losses,
            "ship_placements": self.ship_placements,
            "firing_sequences": self.firing_sequences,
            "move_history": self.move_history,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "OpponentModel":
        m = cls(d["id"])
        m.games_played = d.get("games_played", 0)
        m.wins = d.get("wins", 0)
        m.losses = d.get("losses", 0)
        m.ship_placements = d.get("ship_placements", [])
        m.firing_sequences = d.get("firing_sequences", [])
        m.move_history = d.get("move_history", [])
        return m


class Memory:
    def __init__(self, path: str = "data/memory.json"):
        self.path = path
        self.models: dict[str, OpponentModel] = {}
        self._load()

    def get(self, oid: str) -> OpponentModel:
        if oid not in self.models:
            self.models[oid] = OpponentModel(oid)
        return self.models[oid]

    def save(self):
        with open(self.path, "w") as f:
            json.dump({k: v.to_dict() for k, v in self.models.items()}, f, indent=2)

    def _load(self):
        if os.path.exists(self.path):
            with open(self.path) as f:
                data = json.load(f)
            self.models = {k: OpponentModel.from_dict(v) for k, v in data.items()}

    def summary(self) -> list[str]:
        rows = []
        for m in self.models.values():
            tags = [m.classify().upper()]
            if m.is_fixed_firing():
                tags.append("FIXED-FIRE")
            if m.is_degrading():
                tags.append("DEGRADING")
            rows.append(f"{m.id:<22} G:{m.games_played} W:{m.wins} L:{m.losses}  {' '.join(tags)}")
        return rows
