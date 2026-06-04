import numpy as np
from engine.strategies.heatmap import Heatmap


class Targeting:
    """
    Probability-map targeting with hunt/target and known-position injection.

    Two operating modes:

    ENUMERATION (ship_classes provided — preferred):
        Every turn, enumerate all legal single-ship positions for every remaining
        ship and sum per-cell occupancy counts.  In hunt mode (active hits) only
        placements that cover ≥1 active hit cell are counted.  This gives a true
        Bayesian-style occupancy probability and automatically handles:
          - Orientation inference: if hits are horizontal, vertical placements
            that don't cover them contribute zero.
          - Dynamic fleet adaptation: sunk ships are removed from enumeration.
          - Hunt and sweep in one unified computation (no parity heuristic needed).
          - Heatmap priors blended multiplicatively into the counts.
          - Ship-value weighting: larger ships (higher sink bonus) contribute more
            probability per cell, biasing targeting toward high-value ships.

    HEURISTIC (no ship_classes — backward-compatible fallback):
        Neighbour-boost on hit, hunt stack with orientation inference, and
        dynamic parity sweep scaled to the smallest remaining ship size.

    O(n² · k) per turn where n=board_size and k=ship_count — well within timeout.
    Coordinates are (row, col), 0-indexed.
    """

    # Sink bonus per ship class — used to weight enumeration toward high-value targets
    _SINK_BONUS = {"CARRIER": 10, "BATTLESHIP": 8, "CRUISER": 7, "SUBMARINE": 6, "DESTROYER": 4}

    def __init__(self, board_size: int, ship_classes: list[tuple] = None):
        self.size = board_size
        self.hits:   set[tuple] = set()
        self.misses: set[tuple] = set()
        self.sunk:   set[tuple] = set()
        self.hunt_stack:      list[tuple] = []
        self._priority_queue: list[tuple] = []  # known targets go here first
        # Fleet tracking (enumeration mode)
        self._ship_classes: list[tuple] = sorted(
            (ship_classes or []), key=lambda x: x[1], reverse=True
        )
        self._ship_sizes: list[int] = [s for _, s in self._ship_classes]
        self._sunk_sizes: list[int] = []
        self._sunk_classes: list[str] = []
        self._heatmap_boost: np.ndarray | None = None
        # Initialise probability map
        if self._ship_sizes:
            self.prob = np.zeros((board_size, board_size), dtype=float)
            self._rebuild_prob()  # flat enumeration prior (center cells > corners)
        else:
            self.prob = np.ones((board_size, board_size), dtype=float)

    @property
    def _use_enum_prob(self) -> bool:
        return bool(self._ship_sizes)

    # ── Public interface ───────────────────────────────────────────────────────

    def apply_heatmap(self, heatmap: Heatmap, weight: float = None):
        """
        Blend historical ship frequency into the probability map before the game.
        Requires ≥3 observed games to avoid amplifying random early-game noise.
        Weight scales with confidence: low data → mild boost, high data → strong.
        """
        if heatmap.games_observed < 3:
            return
        if weight is None:
            stability = heatmap.stability()
            games = heatmap.games_observed
            # 1.5 (few games, low stability) → 5.0 (many games, high stability)
            weight = 1.5 + 3.5 * min(stability, 1.0) * min(games / 5, 1.0)
        boost = heatmap.boost_matrix(weight=weight)
        self._heatmap_boost = boost
        if self._use_enum_prob:
            # Store boost; _rebuild_prob() will blend it on every update
            self._rebuild_prob()
        else:
            # Heuristic path: multiply directly into existing prob map
            self.prob *= boost

    def inject_known_targets(self, cells: list[tuple]):
        self._priority_queue = [c for c in cells if c not in self._played()]

    def update(self, row: int, col: int, result: str, sunk_ship_size: int = None,
               sunk_ship_class: str = None):
        coord = (row, col)
        if result == "miss":
            self.misses.add(coord)
            self.prob[row][col] = 0
        elif result in ("hit", "sunk"):
            self.prob[row][col] = 0
            if result == "hit":
                self.hits.add(coord)
                if not self._use_enum_prob:
                    # Heuristic path only — enumeration handles this automatically
                    self._boost_neighbors(row, col)
                    self._push_neighbors(row, col)
            else:
                # Sunk: identify ship cells via line-finding, then clean up
                self.hits.add(coord)  # temporarily include so line search can find it
                ship_cells = self._find_sunk_ship(row, col, sunk_ship_size)
                self.hits -= ship_cells
                self.sunk |= ship_cells
                if sunk_ship_size is not None:
                    self._sunk_sizes.append(sunk_ship_size)
                if sunk_ship_class is not None:
                    self._sunk_classes.append(sunk_ship_class)
                # Clear hunt_stack entries adjacent to the sunk ship,
                # but preserve cells still in self.hits (another ship being hunted)
                stale = set()
                for hr, hc in ship_cells:
                    for dr, dc in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                        stale.add((hr + dr, hc + dc))
                self.hunt_stack = [
                    c for c in self.hunt_stack
                    if c not in self.sunk and (c not in stale or c in self.hits)
                ]

        # Recompute enumeration-based probability after every state change
        if self._use_enum_prob:
            self._rebuild_prob()

    def next_move(self) -> tuple[int, int]:
        move, _ = self._next_move_with_reason()
        return move

    def next_move_reason(self) -> dict:
        """Return explanation context for the last/next move decision."""
        _, reason = self._next_move_with_reason()
        return reason

    def _next_move_with_reason(self) -> tuple[tuple[int, int], dict]:
        played = self._played()
        remaining = self._remaining_ships()

        # 1. Known targets first (exploit mode — always bypasses probability)
        while self._priority_queue:
            c = self._priority_queue.pop(0)
            if c not in played:
                return c, {
                    "mode": "exploit",
                    "remaining_targets": len(self._priority_queue),
                    "remaining_ships": remaining,
                }

        candidates = [
            (row, col)
            for row in range(self.size)
            for col in range(self.size)
            if (row, col) not in played
        ]
        if not candidates:
            raise RuntimeError("Board exhausted")

        if self._use_enum_prob:
            best = max(candidates, key=lambda c: self.prob[c[0]][c[1]])
            prob_val = float(self.prob[best[0]][best[1]])
            # Compute rank: how many candidates have higher or equal probability
            total_prob = sum(float(self.prob[r][c]) for r, c in candidates)
            return best, {
                "mode": "hunt" if self.hits else "probability",
                "prob": prob_val,
                "total_candidates": len(candidates),
                "active_hits": len(self.hits),
                "remaining_ships": remaining,
                "concentration": prob_val / (total_prob / len(candidates)) if total_prob > 0 else 0,
            }

        # ── Heuristic fallback (no ship_classes provided) ─────────────────────

        # 2. Hunt stack (follow adjacent hits, orientation-aware)
        while self.hunt_stack:
            c = self.hunt_stack.pop(0)
            if c not in played:
                return c, {
                    "mode": "hunt",
                    "remaining_ships": remaining,
                    "active_hits": len(self.hits),
                }

        # 3. Dynamic parity sweep.
        min_ship = min(remaining) if remaining else 2
        parity = [c for c in candidates if (c[0] + c[1]) % min_ship == 0]
        pool = parity if parity else candidates
        best = max(pool, key=lambda c: self.prob[c[0]][c[1]])
        return best, {
            "mode": "probability",
            "remaining_ships": remaining,
            "total_candidates": len(pool),
        }

    # ── Enumeration ────────────────────────────────────────────────────────────

    def _rebuild_prob(self):
        """
        Recompute the probability map by enumerating all legal single-ship
        positions for each remaining ship and summing per-cell occupancy.

        Hunt mode (self.hits non-empty): only placements that cover ≥1 active
        hit cell are counted.  This is the key mechanism for orientation
        inference — if two cells in the same row are hit, only horizontal
        placements through them survive, concentrating probability along the row.

        Heatmap boost (if set) is blended multiplicatively into the raw counts
        before storing, so historical priors persist across turns.
        """
        remaining = self._remaining_ships()
        remaining_classes = self._remaining_classes()
        # A placement is illegal if it overlaps a MISS or SUNK cell (definitely empty).
        # Hit cells are confirmed ship cells — placements that include them ARE legal.
        no_ship = self.misses | self.sunk
        counts = np.zeros((self.size, self.size), dtype=float)
        hunt_mode = bool(self.hits)

        # Per-cluster orientation inference: group unsunk hits into connected
        # clusters (each cluster = one unsunk ship), then determine orientation
        # per cluster.  A placement must be consistent with the cluster it covers.
        # This prevents hits from separate ships diluting each other's axis.
        clusters = self._hit_clusters() if hunt_mode else []
        cluster_axis = {}  # cluster_id → "H", "V", or None (unknown)
        for i, cluster in enumerate(clusters):
            if len(cluster) >= 2:
                rows = {r for r, _ in cluster}
                cols = {c for _, c in cluster}
                if len(rows) == 1:
                    cluster_axis[i] = "H"
                elif len(cols) == 1:
                    cluster_axis[i] = "V"
                else:
                    cluster_axis[i] = None
            else:
                cluster_axis[i] = None

        # Build a map: hit_cell → cluster_id for quick lookup
        cell_to_cluster = {}
        for i, cluster in enumerate(clusters):
            for cell in cluster:
                cell_to_cluster[cell] = i

        for ship_class, ship_size in remaining_classes:
            # Weight by sink bonus: CARRIER placements contribute ~2.5x more
            # than DESTROYER placements, biasing targeting toward high-value ships
            weight = self._SINK_BONUS.get(ship_class, 4) / 4.0  # normalize: DESTROYER=1.0, CARRIER=2.5
            for row in range(self.size):
                for col in range(self.size):
                    # Horizontal placement starting at (row, col)
                    if col + ship_size <= self.size:
                        cells = [(row, col + i) for i in range(ship_size)]
                        cell_set = set(cells)
                        if not (cell_set & no_ship):
                            if not hunt_mode or (cell_set & self.hits):
                                # Check axis consistency: if this placement covers
                                # a cluster with known vertical axis, skip it
                                axis_ok = True
                                for c in cells:
                                    ci = cell_to_cluster.get(c)
                                    if ci is not None and cluster_axis.get(ci) == "V":
                                        axis_ok = False
                                        break
                                if axis_ok:
                                    for r, c in cells:
                                        counts[r][c] += weight
                    # Vertical placement starting at (row, col)
                    if row + ship_size <= self.size:
                        cells = [(row + i, col) for i in range(ship_size)]
                        cell_set = set(cells)
                        if not (cell_set & no_ship):
                            if not hunt_mode or (cell_set & self.hits):
                                axis_ok = True
                                for c in cells:
                                    ci = cell_to_cluster.get(c)
                                    if ci is not None and cluster_axis.get(ci) == "H":
                                        axis_ok = False
                                        break
                                if axis_ok:
                                    for r, c in cells:
                                        counts[r][c] += weight

        # Blend heatmap prior into raw enumeration counts
        if self._heatmap_boost is not None:
            counts = counts * self._heatmap_boost

        # Zero out confirmed-empty cells so they're never selected as next move
        for r, c in no_ship:
            counts[r][c] = 0

        self.prob = counts

    # ── Shared helpers ────────────────────────────────────────────────────────

    def _hit_clusters(self) -> list[set[tuple]]:
        """Group unsunk hits into connected clusters (each = one unsunk ship)."""
        remaining = set(self.hits)
        clusters = []
        while remaining:
            seed = next(iter(remaining))
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
            clusters.append(cluster)
        return clusters

    def _played(self) -> set[tuple]:
        return self.hits | self.misses | self.sunk

    # ── Heuristic helpers (fallback path only) ────────────────────────────────

    def _boost_neighbors(self, row: int, col: int):
        for dr, dc in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nr, nc = row + dr, col + dc
            if 0 <= nr < self.size and 0 <= nc < self.size:
                self.prob[nr][nc] *= 3

    def _push_neighbors(self, row: int, col: int):
        """
        Push adjacent cells onto the hunt stack.
        Orientation-aware: once ≥2 cells are hit in the same row or column,
        only extend in that axis — avoids wasting shots perpendicular to a
        confirmed ship orientation.
        """
        played = self._played()
        h_aligned = [c for c in self.hits if c[0] == row and c != (row, col)]
        v_aligned = [c for c in self.hits if c[1] == col and c != (row, col)]

        if h_aligned:
            directions = [(0, -1), (0, 1)]    # confirmed horizontal → left/right only
        elif v_aligned:
            directions = [(-1, 0), (1, 0)]    # confirmed vertical   → up/down only
        else:
            directions = [(0, 1), (0, -1), (1, 0), (-1, 0)]  # orientation unknown

        for dr, dc in directions:
            nr, nc = row + dr, col + dc
            if (0 <= nr < self.size and 0 <= nc < self.size
                    and (nr, nc) not in played
                    and (nr, nc) not in self.hunt_stack):
                self.hunt_stack.append((nr, nc))

    # ── Ship identification ────────────────────────────────────────────────────

    def _find_sunk_ship(self, row: int, col: int, ship_size: int = None) -> set[tuple]:
        """
        Identify cells of the sunk ship through the final sunk cell.
        Uses line-finding (ships are straight lines) bounded by ship_size to
        avoid crossing into adjacent ships when allowAdjacency=True.
        """
        h_cells = [(row, col)]
        for dc in [-1, 1]:
            c = col + dc
            while 0 <= c < self.size and (row, c) in self.hits:
                h_cells.append((row, c))
                c += dc

        v_cells = [(row, col)]
        for dr in [-1, 1]:
            r = row + dr
            while 0 <= r < self.size and (r, col) in self.hits:
                v_cells.append((r, col))
                r += dr

        if ship_size:
            if len(h_cells) == ship_size:
                return set(h_cells)
            if len(v_cells) == ship_size:
                return set(v_cells)
            # Line is longer than expected (collinear adjacent ships).
            # Try windows where the sunk cell is at an edge (start or end),
            # since the sunk cell typically completes the ship from one end.
            for line in [h_cells, v_cells]:
                if len(line) >= ship_size:
                    is_horiz = all(c[0] == line[0][0] for c in line)
                    line_sorted = sorted(line, key=lambda c: c[1] if is_horiz else c[0])
                    pivot = line_sorted.index((row, col))
                    # Try window ending at pivot (ship extends backward)
                    end_at = max(0, pivot - ship_size + 1)
                    # Try window starting at pivot (ship extends forward)
                    start_at = min(pivot, len(line_sorted) - ship_size)
                    # Prefer the window where the pivot is at the very edge
                    if pivot == end_at + ship_size - 1:
                        return set(line_sorted[end_at:end_at + ship_size])
                    if pivot == start_at:
                        return set(line_sorted[start_at:start_at + ship_size])
                    # Pivot is in the middle — use ending-at-pivot as fallback
                    return set(line_sorted[end_at:end_at + ship_size])
            return set(h_cells) if len(h_cells) >= len(v_cells) else set(v_cells)

        return set(h_cells) if len(h_cells) >= len(v_cells) else set(v_cells)

    def _connected_hits(self, row: int, col: int) -> set[tuple]:
        """BFS through contiguous hit cells — kept for backward compatibility."""
        visited: set[tuple] = set()
        queue = [(row, col)]
        while queue:
            cr, cc = queue.pop()
            if (cr, cc) in visited:
                continue
            visited.add((cr, cc))
            for dr, dc in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nr, nc = cr + dr, cc + dc
                if (nr, nc) in self.hits and (nr, nc) not in visited:
                    queue.append((nr, nc))
        return visited

    def _remaining_ships(self) -> list[int]:
        remaining = list(self._ship_sizes)
        for s in self._sunk_sizes:
            try:
                remaining.remove(s)
            except ValueError:
                pass
        return remaining

    def _remaining_classes(self) -> list[tuple[str, int]]:
        """Return (class_name, size) for each remaining unsunk ship."""
        remaining = list(self._ship_classes)
        for cls in self._sunk_classes:
            for i, (c, s) in enumerate(remaining):
                if c == cls:
                    remaining.pop(i)
                    break
        return remaining

    def render(self) -> str:
        lines = ["    " + "  ".join(f"{c}" for c in range(self.size))]
        for row in range(self.size):
            cells = [f"{row:2} |"]
            for col in range(self.size):
                if (row, col) in self.sunk:
                    cells.append(" #")
                elif (row, col) in self.hits:
                    cells.append(" X")
                elif (row, col) in self.misses:
                    cells.append(" ·")
                else:
                    cells.append(" ~")
            lines.append(" ".join(cells))
        return "\n".join(lines)
