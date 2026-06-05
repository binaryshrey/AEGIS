"""
Feedback Loop — structured lessons learned after every game.

After each game the agent writes a Lesson: what it observed, what worked,
what to do differently next time. Lessons are persisted, queryable, and
directly influence future strategy decisions.

This mirrors StarSling's CI optimization loop:
  run CI → observe result → generate optimization → apply next run
"""
import json
import os
import tempfile
import time
from dataclasses import dataclass, field, asdict
from enum import Enum


class LessonType(Enum):
    PLACEMENT_EXPLOIT  = "placement_exploit"   # known placement → go straight for it
    FIRING_DODGE       = "firing_dodge"        # known firing pattern → dodge it
    TIMING_OK          = "timing_ok"           # move latency was fine
    TIMING_RISK        = "timing_risk"         # move latency was risky


@dataclass
class Lesson:
    opponent_id:  str
    lesson_type:  str                    # LessonType value
    summary:      str                    # human-readable one-liner
    detail:       str                    # full rationale
    metric_before: float | None         # baseline (moves, ms, etc.)
    metric_after:  float | None         # result after applying lesson
    gain:          float | None         # metric_before - metric_after (positive = improvement)
    confidence:    float                # 0.0 – 1.0
    games_basis:   int                  # how many games this lesson is based on
    timestamp:     float = field(default_factory=time.time)
    applied_count: int = 0              # how many times this lesson was acted on

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Lesson":
        return cls(**d)

    def __str__(self) -> str:
        gain_str = f"  gain={self.gain:+.1f}" if self.gain is not None else ""
        return (
            f"[{self.lesson_type.upper()}] {self.opponent_id}: {self.summary}"
            f"  (confidence={self.confidence:.0%}, basis={self.games_basis} games{gain_str})"
        )


class FeedbackStore:
    """
    Persists lessons to disk. Queryable by opponent, type, confidence.
    Grows smarter with every game played.
    """

    def __init__(self, path: str = "data/lessons.json"):
        self.path = path
        self.lessons: list[Lesson] = []
        self._load()

    @staticmethod
    def _lesson_key(lesson: "Lesson") -> tuple:
        """Dedup key: (opponent_id, lesson_type). One lesson per type per opponent."""
        return (lesson.opponent_id, lesson.lesson_type)

    def add(self, lesson: Lesson):
        # Replace existing lesson with same dedup key.
        # Always accept newer lessons — the agent needs to unlearn stale data
        # (e.g., a strategy that used to work but no longer does).
        key = self._lesson_key(lesson)
        for i, existing in enumerate(self.lessons):
            if self._lesson_key(existing) == key:
                self.lessons[i] = lesson
                self._save()
                return
        self.lessons.append(lesson)
        self._save()

    def for_opponent(self, opponent_id: str) -> list[Lesson]:
        return [l for l in self.lessons if l.opponent_id == opponent_id]

    def by_type(self, lesson_type: LessonType) -> list[Lesson]:
        return [l for l in self.lessons if l.lesson_type == lesson_type.value]

    def high_confidence(self, threshold: float = 0.7) -> list[Lesson]:
        return [l for l in self.lessons if l.confidence >= threshold]

    def mark_applied(self, lesson: Lesson):
        lesson.applied_count += 1
        self._save()

    def summary(self) -> list[str]:
        if not self.lessons:
            return []
        lines = []
        for l in sorted(self.lessons, key=lambda x: -(x.confidence)):
            lines.append(str(l))
        return lines

    def _save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.path) or ".", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump([l.to_dict() for l in self.lessons], f, indent=2)
            os.replace(tmp, self.path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _load(self):
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path) as f:
                data = json.load(f)
            self.lessons = [Lesson.from_dict(d) for d in data]
        except (json.JSONDecodeError, ValueError) as e:
            print(f"  [warning] Corrupt lessons.json: {e} — starting fresh")
            backup = self.path + ".corrupt"
            try:
                os.replace(self.path, backup)
            except OSError:
                pass


class FeedbackEngine:
    """
    Generates structured lessons after each game.
    Reads lessons before each game to influence decisions.
    """

    def __init__(self, store: FeedbackStore):
        self.store = store

    # ── Post-game: generate lessons ───────────────────────────────────────────

    def generate(self, opponent_id: str, model, game_result: dict) -> list[Lesson]:
        """
        Called after a game ends. Returns new lessons generated from the result.
        game_result = {
            "won": bool,
            "moves": int,
            "avg_ms": float,
            "strategy_used": str,
            "baseline_moves": int | None,
            "ships_lost": int,
            "hits_received": int,
        }
        """
        lessons = []

        won            = game_result["won"]
        moves          = game_result["moves"]
        avg_ms         = game_result["avg_ms"]
        baseline_moves = game_result.get("baseline_moves")
        games_played   = model.games_played

        # Lesson 1: placement exploit readiness.
        # Generate whenever fixed placement is confirmed — regardless of which
        # strategy was used this game. This breaks the chicken-and-egg where
        # PLACEMENT_EXPLOIT only fires after we've already chosen "exploit",
        # but feedback never recommends "exploit" until the lesson exists.
        # Confidence factors in win rate — if we keep losing despite "fixed"
        # placement, don't lock in exploit (bot may have changed or data is wrong).
        if model.is_fixed_placement(min_games=5):
            gain = (baseline_moves - moves) if baseline_moves else None
            win_rate = model.wins / games_played if games_played else 0
            confidence = min(0.95, (0.5 + games_played * 0.15) * max(win_rate, 0.3))
            lessons.append(Lesson(
                opponent_id=opponent_id,
                lesson_type=LessonType.PLACEMENT_EXPLOIT.value,
                summary=f"Fixed placement confirmed — exploit drops moves to ~{moves}",
                detail=(
                    f"After {games_played} games (win rate {win_rate:.0%}), "
                    f"bot always places ships identically. "
                    f"Injecting known targets reduced game to {moves} moves "
                    f"({'vs baseline ' + str(baseline_moves) if baseline_moves else 'first exploit run'})."
                ),
                metric_before=float(baseline_moves) if baseline_moves else None,
                metric_after=float(moves),
                gain=gain,
                confidence=confidence,
                games_basis=games_played,
            ))

        # Lesson 2: firing pattern dodge (observability only — actual avoidance
        # comes from model.dangerous_squares() called directly in main.py,
        # not from reading this lesson).
        if model.is_fixed_firing(min_games=5):
            dangerous = model.dangerous_squares()
            confidence = min(0.9, 0.4 + games_played * 0.15)
            lessons.append(Lesson(
                opponent_id=opponent_id,
                lesson_type=LessonType.FIRING_DODGE.value,
                summary=f"Firing pattern locked — avoid {len(dangerous)} hot squares on placement",
                detail=(
                    f"Bot fires in a deterministic sequence. "
                    f"{len(dangerous)} squares appear in ≥60% of early turns. "
                    f"Adaptive placement now avoids these to survive longer."
                ),
                metric_before=None,
                metric_after=float(len(dangerous)),
                gain=None,
                confidence=confidence,
                games_basis=games_played,
            ))

        # Strategy effectiveness is tracked by the bandit (evidence-based:
        # games, avg_moves, efficiency per strategy per opponent).
        # No strategy lessons generated — they accumulate contradictory
        # anecdotes that conflict with the bandit's evidence.

        # Timing lessons removed — 70-126ms vs 10,000ms limit is pure noise.

        return lessons

    # Strategy selection is handled entirely by the bandit (evidence-based).
    # Lessons are observability-only — no pre-game strategy overrides.

