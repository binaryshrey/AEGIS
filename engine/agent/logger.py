"""
Structured JSONL logger — machine-parseable audit trail.

Every game event is written as a single JSON line to a log file.
Evaluators can grep, jq, or load into pandas for analysis.

Format per line:
  {"ts": "2026-06-03T12:00:00.123Z", "event": "move_made", "data": {...}}
"""
import json
import time
from datetime import datetime, timezone
from dataclasses import asdict
from pathlib import Path

from engine.agent.events import (
    EventType,
    RegisteredEvent, AttemptStartedEvent, GameStartedEvent, MoveMadeEvent,
    PatternDetectedEvent, StrategyChangedEvent, GameEndedEvent,
    MemoryUpdatedEvent, AttemptEndedEvent, TimeoutWarningEvent, ErrorEvent,
)


class GameLogger:
    """Append-only JSONL logger. One file per agent run."""

    def __init__(self, path: str = "data/game_log.jsonl"):
        self.path = Path(path)
        self._fh = None
        self._run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self._attempt_num = 0
        self._game_num = 0
        # Cross-attempt tracking for learning curve
        self._attempt_scores: list[dict] = []

    def open(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a", buffering=1)  # line-buffered
        self._write("run_started", {
            "run_id": self._run_id,
            "timestamp": self._now(),
        })

    def close(self):
        if self._attempt_scores:
            self._write("learning_curve", {
                "attempts": self._attempt_scores,
                "total_attempts": len(self._attempt_scores),
            })
        self._write("run_ended", {
            "run_id": self._run_id,
            "timestamp": self._now(),
        })
        if self._fh:
            self._fh.close()
            self._fh = None

    def log_attempt_start(self, attempt_num: int):
        self._attempt_num = attempt_num
        self._write("attempt_started", {
            "attempt": attempt_num,
        })

    def log_attempt_end(self, attempt_num: int, wins: int, losses: int,
                        games: list[dict] = None, server_score: int | None = None):
        summary = {
            "attempt": attempt_num,
            "wins": wins,
            "losses": losses,
            "win_rate": wins / (wins + losses) if (wins + losses) else 0,
            "games_detail": games or [],
            "server_score": server_score,
        }
        self._attempt_scores.append(summary)
        self._write("attempt_ended", summary)

    def _write(self, event: str, data: dict):
        if not self._fh:
            return
        line = json.dumps({
            "ts": self._now(),
            "event": event,
            "attempt": self._attempt_num,
            "data": data,
        }, default=str)
        self._fh.write(line + "\n")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds")

    # ── Event handlers ────────────────────────────────────────────────────────

    def on_attempt_started(self, e: AttemptStartedEvent):
        self.log_attempt_start(e.attempt_num)

    def on_attempt_ended(self, e: AttemptEndedEvent):
        self.log_attempt_end(e.attempt_num, e.wins, e.losses, e.games_detail,
                             getattr(e, 'server_score', None))

    def on_registered(self, e: RegisteredEvent):
        self._write("registered", {
            "player_id": e.player_id,
            "turn_timeout": e.turn_timeout,
            "num_opponents": e.num_opponents,
        })

    def on_game_started(self, e: GameStartedEvent):
        self._game_num = e.game_num
        self._write("game_started", {
            "game_num": e.game_num,
            "opponent_id": e.opponent_id,
            "known_placement": e.known_placement,
            "known_firing": e.known_firing,
            "games_vs_opponent": e.games_vs_opponent,
            "win_rate": round(e.win_rate, 3),
            "chosen_strategy": e.chosen_strategy,
            "strategy_reason": e.strategy_reason,
        })

    def on_move_made(self, e: MoveMadeEvent):
        self._write("move", {
            "game_num": e.game_num,
            "turn": e.turn,
            "row": e.coord[0],
            "col": e.coord[1],
            "result": e.result,
            "elapsed_ms": round(e.elapsed_ms, 1),
            "strategy": e.strategy,
            "confidence": e.confidence,
        })

    def on_pattern_detected(self, e: PatternDetectedEvent):
        self._write("pattern_detected", {
            "opponent_id": e.opponent_id,
            "pattern_type": e.pattern_type,
            "games_confirmed": e.games_confirmed,
            "detail": e.detail,
        })

    def on_strategy_changed(self, e: StrategyChangedEvent):
        self._write("strategy_changed", {
            "opponent_id": e.opponent_id,
            "from": e.from_strategy,
            "to": e.to_strategy,
            "reason": e.reason,
        })

    def on_game_ended(self, e: GameEndedEvent):
        improvement = None
        if e.baseline_moves is not None:
            improvement = e.baseline_moves - e.total_moves
        self._write("game_ended", {
            "game_num": e.game_num,
            "opponent_id": e.opponent_id,
            "won": e.won,
            "total_moves": e.total_moves,
            "avg_ms": round(e.avg_ms, 1),
            "baseline_moves": e.baseline_moves,
            "improvement": improvement,
            "ships_lost": e.ships_lost,
            "hits_received": e.hits_received,
        })

    def on_memory_updated(self, e: MemoryUpdatedEvent):
        self._write("memory_updated", {
            "opponent_id": e.opponent_id,
            "games_played": e.games_played,
            "fixed_placement": e.fixed_placement,
            "fixed_firing": e.fixed_firing,
            "win_rate": round(e.win_rate, 3),
        })

    def on_timeout_warning(self, e: TimeoutWarningEvent):
        self._write("timeout_warning", {
            "game_num": e.game_num,
            "turn": e.turn,
            "elapsed_ms": round(e.elapsed_ms, 1),
            "budget_ms": e.budget_ms,
        })

    def on_error(self, e: ErrorEvent):
        self._write("error", {
            "context": e.context,
            "message": e.message,
            "recoverable": e.recoverable,
        })


def make_log_subscriber(logger: GameLogger) -> dict:
    """Wire logger to event emitter — same pattern as display/metrics subscribers."""
    return {
        EventType.REGISTERED:        logger.on_registered,
        EventType.ATTEMPT_STARTED:   logger.on_attempt_started,
        EventType.GAME_STARTED:      logger.on_game_started,
        EventType.MOVE_MADE:         logger.on_move_made,
        EventType.PATTERN_DETECTED:  logger.on_pattern_detected,
        EventType.STRATEGY_CHANGED:  logger.on_strategy_changed,
        EventType.GAME_ENDED:        logger.on_game_ended,
        EventType.MEMORY_UPDATED:    logger.on_memory_updated,
        EventType.ATTEMPT_ENDED:     logger.on_attempt_ended,
        EventType.TIMEOUT_WARNING:   logger.on_timeout_warning,
        EventType.ERROR:             logger.on_error,
    }
