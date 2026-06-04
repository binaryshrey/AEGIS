"""
ReAct (Reason + Act) agent loop.

Instead of blindly picking the best probability cell, the agent explicitly
reasons about what it knows before each move — matching how StarSling's
production agents work.

Observation → Reason → Act → Observe → ...
Coordinates are (row, col), 0-indexed.
"""
from dataclasses import dataclass


@dataclass
class Observation:
    """What the agent perceived after its last action."""
    last_result:   str | None   = None   # hit | miss | sunk | None (first turn)
    last_coord:    tuple | None = None   # (row, col)
    opponent_shot: tuple | None = None   # (row, col) of opponent's return shot
    game_status:   str          = "ongoing"
    turn:          int          = 0


@dataclass
class Reasoning:
    """The agent's internal monologue before acting."""
    strategy:     str           = "probability"   # probability | hunt | exploit
    rationale:    str           = ""
    chosen_move:  tuple | None  = None            # (row, col)
    confidence:   str           = "low"           # low | medium | high
    move_reason:  dict | None   = None            # detailed targeting context


class ReActAgent:
    """
    Wraps the targeting strategy in an explicit Observe → Reason → Act loop.
    Makes the closed-loop learning visible and auditable.
    """

    def __init__(self, targeter, opponent_model, turn_timeout: float = 10):
        self.targeter = targeter
        self.model    = opponent_model
        self._last_reason: dict | None = None

        # Pre-compute first move so act() is always instant
        self._next_move = self._compute()

    def observe(self, result: str, coord: tuple, opponent_shot: tuple | None,
                status: str, turn: int, sunk_ship_size: int = None,
                sunk_ship_class: str = None) -> Observation:
        """Step 1: Update internal state from what just happened."""
        self.targeter.update(coord[0], coord[1], result, sunk_ship_size=sunk_ship_size,
                             sunk_ship_class=sunk_ship_class)
        return Observation(
            last_result=result,
            last_coord=coord,
            opponent_shot=opponent_shot,
            game_status=status,
            turn=turn,
        )

    def reason(self, obs: Observation) -> Reasoning:
        """Step 2: Decide strategy based on current knowledge."""
        r = Reasoning()

        # Priority 1: we know exactly where ships are
        if self.model.is_fixed_placement() and self.targeter._priority_queue:
            r.strategy   = "exploit"
            r.confidence = "high"
            r.rationale  = (
                f"Bot has fixed placement (confirmed over {self.model.games_played} games). "
                f"Targeting known cells directly. "
                f"{len(self.targeter._priority_queue)} known targets remaining."
            )

        # Priority 2: following up a hit (hunt_stack in heuristic mode,
        # active hits in enumeration mode — both indicate hunt behavior)
        elif self.targeter.hunt_stack or self.targeter.hits:
            r.strategy   = "hunt"
            r.confidence = "medium"
            active = len(self.targeter.hunt_stack) or len(self.targeter.hits)
            r.rationale  = (
                f"Active hit at {obs.last_coord if obs.last_result in ('hit','sunk') else 'prior turn'}. "
                f"Hunting {active} active targets."
            )

        # Priority 3: probability sweep
        else:
            r.strategy   = "probability"
            r.confidence = "low"
            r.rationale  = (
                f"No active hits, no known placement. "
                f"Using probability map — {len(self.targeter._played())} cells eliminated so far."
            )

        return r

    def act(self, reasoning: Reasoning) -> tuple[int, int]:
        """Step 3: Return the pre-computed move (always ready from last iteration)."""
        move = self._next_move
        # Safety: if the pre-computed move was already played (e.g., state changed
        # between pre-computation and now), recompute immediately.
        try:
            if move in self.targeter._played():
                move = self._compute()
        except RuntimeError:
            pass  # board truly exhausted — use whatever we have
        reasoning.chosen_move = move
        reasoning.move_reason = self._last_reason
        return move

    def pre_compute_next(self, status: str):
        """Pre-compute next move while caller processes the HTTP response."""
        if status not in ("won", "lost"):
            self._next_move = self._compute()

    def _compute(self) -> tuple[int, int]:
        try:
            move, reason = self.targeter._next_move_with_reason()
            self._last_reason = reason
            return move
        except RuntimeError:
            # Board exhausted — scan for any unplayed cell as last resort
            played = self.targeter._played()
            for row in range(self.targeter.size):
                for col in range(self.targeter.size):
                    if (row, col) not in played:
                        return (row, col)
            raise  # truly exhausted — propagate up
