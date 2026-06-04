"""
Event Emitter — observable game loop.

Every meaningful action emits a typed event. Any component can subscribe
to any event without coupling to the game loop directly.

Pattern: publish / subscribe (observer pattern)
Why: makes the closed-loop auditable, extensible, and testable in isolation.
     Mirrors how StarSling's agent harness emits CI pipeline events.
"""
from dataclasses import dataclass, field
from typing import Callable, Any
from enum import Enum


# ── Event Types ────────────────────────────────────────────────────────────────

class EventType(Enum):
    REGISTERED       = "registered"
    ATTEMPT_STARTED  = "attempt_started"
    GAME_STARTED     = "game_started"
    MOVE_MADE        = "move_made"
    PATTERN_DETECTED = "pattern_detected"
    STRATEGY_CHANGED = "strategy_changed"
    GAME_ENDED       = "game_ended"
    MEMORY_UPDATED   = "memory_updated"
    ATTEMPT_ENDED    = "attempt_ended"
    TIMEOUT_WARNING  = "timeout_warning"
    ERROR            = "error"


# ── Event Payloads ─────────────────────────────────────────────────────────────

@dataclass
class RegisteredEvent:
    player_id: str
    turn_timeout: float
    num_opponents: int

@dataclass
class GameStartedEvent:
    game_num: int
    opponent_id: str
    known_placement: bool
    known_firing: bool
    games_vs_opponent: int
    win_rate: float = 0.0
    chosen_strategy: str = ""
    strategy_reason: str = ""
    trust: float = 0.0
    classification: str = "unknown"
    stability: float = 0.0

@dataclass
class MoveMadeEvent:
    game_num: int
    turn: int
    coord: tuple
    result: str          # hit | miss | sunk
    elapsed_ms: float
    strategy: str        # probability | hunt | exploit
    confidence: str      # low | medium | high
    move_reason: dict | None = None  # targeting context for explainability

@dataclass
class PatternDetectedEvent:
    opponent_id: str
    pattern_type: str    # fixed_placement | fixed_firing | partial_placement
    games_confirmed: int
    detail: str

@dataclass
class StrategyChangedEvent:
    opponent_id: str
    from_strategy: str
    to_strategy: str
    reason: str

@dataclass
class GameEndedEvent:
    game_num: int
    opponent_id: str
    won: bool
    total_moves: int
    avg_ms: float
    baseline_moves: int | None   # previous game's move count vs this bot (None if first game)
    ships_lost: int = 0          # our ships sunk by opponent
    hits_received: int = 0       # total hits on our fleet
    sunk_classes: list = field(default_factory=list)   # opponent ship classes we sunk
    lost_classes: list = field(default_factory=list)    # our ship classes lost

@dataclass
class MemoryUpdatedEvent:
    opponent_id: str
    games_played: int
    fixed_placement: bool
    fixed_firing: bool
    win_rate: float

@dataclass
class TimeoutWarningEvent:
    game_num: int
    turn: int
    elapsed_ms: float
    budget_ms: float

@dataclass
class AttemptStartedEvent:
    attempt_num: int
    prior_attempts: int      # how many attempts completed before this one
    memory_opponents: int    # how many opponents we have data on

@dataclass
class AttemptEndedEvent:
    attempt_num: int
    wins: int
    losses: int
    games_detail: list       # per-game summaries for this attempt

@dataclass
class ErrorEvent:
    context: str
    message: str
    recoverable: bool


# ── Emitter ────────────────────────────────────────────────────────────────────

class EventEmitter:
    """
    Central event bus. Components subscribe to event types they care about.
    All handlers are called synchronously in subscription order.
    """

    def __init__(self):
        self._handlers: dict[EventType, list[Callable]] = {e: [] for e in EventType}

    def on(self, event_type: EventType, handler: Callable):
        """Subscribe a handler to an event type."""
        self._handlers[event_type].append(handler)
        return self  # allow chaining

    def emit(self, event_type: EventType, payload: Any):
        """Emit an event — calls all subscribed handlers."""
        for handler in self._handlers[event_type]:
            try:
                handler(payload)
            except Exception as e:
                # Handler errors must never crash the game loop
                print(f"  [emitter] handler error on {event_type.value}: {e}")

    def off(self, event_type: EventType, handler: Callable):
        """Unsubscribe a handler."""
        self._handlers[event_type] = [
            h for h in self._handlers[event_type] if h != handler
        ]


# ── Built-in Subscribers ───────────────────────────────────────────────────────

def make_display_subscriber(display) -> dict[EventType, Callable]:
    """Wire display output to events — decouples display from game loop."""
    return {
        EventType.REGISTERED: lambda e: display.header(
            e.player_id, e.turn_timeout, e.num_opponents
        ),
        EventType.ATTEMPT_STARTED: lambda e: display.attempt_start(
            e.attempt_num, e.prior_attempts, e.memory_opponents
        ),
        EventType.GAME_STARTED: lambda e: display.game_start(
            e.game_num, e.opponent_id, e.known_placement, e.known_firing,
            games_played=e.games_vs_opponent, win_rate=e.win_rate,
            strategy=e.chosen_strategy, strategy_reason=e.strategy_reason,
        ),
        EventType.MOVE_MADE: lambda e: display.move(
            e.turn, e.coord[0], e.coord[1], e.result, e.elapsed_ms, e.strategy,
            move_reason=e.move_reason,
        ),
        EventType.PATTERN_DETECTED: lambda e: _display_pattern(display, e),
        EventType.STRATEGY_CHANGED: lambda e: None,  # shown in game header; mid-game shifts visible via per-move strategy tag
        EventType.GAME_ENDED: lambda e: _display_game_end(display, e),
        EventType.MEMORY_UPDATED: lambda e: None,  # covered by PATTERN_DETECTED events
        EventType.ATTEMPT_ENDED: lambda e: display.attempt_end(
            e.attempt_num, e.wins, e.losses
        ),
        EventType.TIMEOUT_WARNING: lambda e: display.error(
            f"TIMEOUT WARNING turn {e.turn}: {e.elapsed_ms:.0f}ms / {e.budget_ms:.0f}ms budget"
        ),
        EventType.ERROR: lambda e: display.error(
            f"[{e.context}] {e.message} ({'recoverable' if e.recoverable else 'fatal'})"
        ),
    }


_LESSON_TYPES = {
    "placement_exploit", "firing_dodge",
    "strategy_effective", "strategy_failed",
    "timing_ok", "timing_risk",
}
_STRUCTURAL_TYPES = {"fixed_placement", "fixed_firing"}


def _display_pattern(display, e: PatternDetectedEvent):
    if e.pattern_type == "heatmap_prior":
        # heatmap.summary() format: "[HEATMAP] opp: stability=X (Y) | N games observed | M hot cells"
        # Strip the prefix and show compactly
        detail = e.detail
        if ": " in detail:
            detail = detail.split(": ", 1)[1]
        display.info(f"heatmap  {detail}")
    elif e.pattern_type in _STRUCTURAL_TYPES:
        display.pattern(e.detail)
    elif e.pattern_type == "timing_ok":
        pass  # fires every game — not actionable
    elif e.pattern_type in _LESSON_TYPES:
        display.lesson(e.detail)
    else:
        display.info(e.detail)


def _display_game_end(display, e: GameEndedEvent):
    delta = (e.baseline_moves - e.total_moves) if e.baseline_moves is not None else None
    display.game_end(e.won, e.total_moves, e.avg_ms, delta,
                     ships_lost=e.ships_lost, hits_received=e.hits_received)


def make_metrics_subscriber() -> tuple[dict, dict[EventType, Callable]]:
    """
    Collects in-memory metrics across all games.
    Returns (metrics_dict, handlers).
    """
    metrics = {
        "total_games": 0,
        "wins": 0,
        "losses": 0,
        "patterns_detected": 0,
        "strategy_changes": 0,
        "timeout_warnings": 0,
        "errors": 0,
        "move_times_ms": [],
        "moves_per_game": [],
        "improvements": [],      # (opponent_id, delta_moves)
        "per_opponent": {},      # { opp_id: { games, wins, moves } }
        "attempts": [],          # per-attempt {wins, losses} for learning curve
    }

    handlers = {
        EventType.GAME_STARTED: lambda e: _record_trust(metrics, e),
        EventType.GAME_ENDED: lambda e: _record_game(metrics, e),
        EventType.MOVE_MADE: lambda e: metrics["move_times_ms"].append(e.elapsed_ms),
        EventType.PATTERN_DETECTED: lambda e: metrics.__setitem__(
            "patterns_detected", metrics["patterns_detected"] + 1
        ),
        EventType.STRATEGY_CHANGED: lambda e: metrics.__setitem__(
            "strategy_changes", metrics["strategy_changes"] + 1
        ),
        EventType.TIMEOUT_WARNING: lambda e: metrics.__setitem__(
            "timeout_warnings", metrics["timeout_warnings"] + 1
        ),
        EventType.ERROR: lambda e: metrics.__setitem__(
            "errors", metrics["errors"] + 1
        ),
        EventType.ATTEMPT_ENDED: lambda e: metrics["attempts"].append({
            "attempt": e.attempt_num, "wins": e.wins, "losses": e.losses,
        }),
    }
    return metrics, handlers


def _record_trust(metrics: dict, e: GameStartedEvent):
    """Track latest trust, classification, stability per opponent (overwritten each game)."""
    if "trust_per_opponent" not in metrics:
        metrics["trust_per_opponent"] = {}
    metrics["trust_per_opponent"][e.opponent_id] = e.trust
    if "classification_per_opponent" not in metrics:
        metrics["classification_per_opponent"] = {}
    metrics["classification_per_opponent"][e.opponent_id] = e.classification
    if "stability_per_opponent" not in metrics:
        metrics["stability_per_opponent"] = {}
    metrics["stability_per_opponent"][e.opponent_id] = e.stability


def _record_game(metrics: dict, e: GameEndedEvent):
    metrics["total_games"] += 1
    metrics["moves_per_game"].append(e.total_moves)
    if e.won:
        metrics["wins"] += 1
    else:
        metrics["losses"] += 1
    if e.baseline_moves is not None and e.total_moves < e.baseline_moves:
        metrics["improvements"].append((e.opponent_id, e.baseline_moves - e.total_moves))

    opp = e.opponent_id
    if opp not in metrics["per_opponent"]:
        metrics["per_opponent"][opp] = {
            "games": 0, "wins": 0, "moves": [],
            "ships_lost": [], "hits_received": [],
            "sunk_classes": [], "lost_classes": [],
        }
    m = metrics["per_opponent"][opp]
    m["games"] += 1
    m["moves"].append(e.total_moves)
    m["ships_lost"].append(e.ships_lost)
    m["hits_received"].append(e.hits_received)
    m["sunk_classes"].append(e.sunk_classes)
    m["lost_classes"].append(e.lost_classes)
    if e.won:
        m["wins"] += 1


def print_metrics_summary(metrics: dict):
    """Print a final metrics summary using Rich tables and panels."""
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich import box

    con = Console()

    if not metrics["moves_per_game"]:
        return
    avg_moves = sum(metrics["moves_per_game"]) / len(metrics["moves_per_game"])
    avg_ms = sum(metrics["move_times_ms"]) / len(metrics["move_times_ms"]) if metrics["move_times_ms"] else 0
    total_savings = sum(d for _, d in metrics["improvements"])
    win_rate = metrics["wins"] / metrics["total_games"] if metrics["total_games"] else 0
    wr_color = "green" if win_rate >= 0.9 else "yellow" if win_rate >= 0.7 else "red"

    # ── Overview panel ────────────────────────────────────────────────────────
    all_ships_lost = []
    all_hits_received = []
    for m in metrics["per_opponent"].values():
        all_ships_lost.extend(m.get("ships_lost", []))
        all_hits_received.extend(m.get("hits_received", []))
    avg_surviving = 5.0 - (sum(all_ships_lost) / len(all_ships_lost)) if all_ships_lost else 5.0
    avg_hits = sum(all_hits_received) / len(all_hits_received) if all_hits_received else 0

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold cyan", min_width=16)
    grid.add_column()
    grid.add_row("Games", str(metrics["total_games"]))
    grid.add_row("Record", f"[{wr_color} bold]{metrics['wins']}W / {metrics['losses']}L  ({win_rate:.0%})[/]")
    grid.add_row("Avg Moves", f"{avg_moves:.1f}")
    grid.add_row("Avg ms/move", f"{avg_ms:.1f}ms")
    grid.add_row("Move Savings", f"{total_savings} from learning")
    grid.add_row("Ships Surviving", f"{avg_surviving:.1f} / 5")
    grid.add_row("Hits Taken", f"{avg_hits:.1f} avg")
    if metrics["timeout_warnings"]:
        grid.add_row("Timeouts", f"[yellow]{metrics['timeout_warnings']}[/]")
    if metrics["errors"]:
        grid.add_row("Errors", f"[red]{metrics['errors']}[/]")

    con.print()
    con.print(Panel(grid, title="[bold white]METRICS SUMMARY[/]",
                    border_style="cyan", box=box.HEAVY))

    # ── Learning curve ────────────────────────────────────────────────────────
    if len(metrics["attempts"]) > 1:
        lc = Table(title="Learning Curve", box=box.SIMPLE_HEAVY,
                   border_style="blue", title_style="bold white")
        lc.add_column("Attempt", justify="center", style="bold")
        lc.add_column("Result", min_width=10)
        lc.add_column("Bar", min_width=30)
        lc.add_column("Win%", justify="right")
        for a in metrics["attempts"]:
            total = a["wins"] + a["losses"]
            wr = a["wins"] / total if total else 0
            bar = f"[green]{'█' * a['wins']}[/][red]{'░' * a['losses']}[/]"
            color = "green" if wr >= 0.9 else "yellow" if wr >= 0.7 else "red"
            lc.add_row(
                str(a["attempt"]),
                f"{a['wins']}W/{a['losses']}L",
                bar,
                f"[{color}]{wr:.0%}[/]",
            )
        con.print(lc)

    # ── Per-opponent table ────────────────────────────────────────────────────
    if metrics["per_opponent"]:
        tbl = Table(title="Per-Opponent Breakdown", box=box.ROUNDED,
                    border_style="cyan", title_style="bold white")
        tbl.add_column("Opponent", style="bold", min_width=18)
        tbl.add_column("G", justify="center", width=3)
        tbl.add_column("W/L", justify="center", width=6)
        tbl.add_column("Win%", justify="right", width=5)
        tbl.add_column("Avg", justify="right", width=5)
        tbl.add_column("Best", justify="right", width=5)
        tbl.add_column("Surv", justify="right", width=5)
        tbl.add_column("Hits", justify="right", width=5)
        tbl.add_column("Trajectory", min_width=20)

        for opp, m in sorted(metrics["per_opponent"].items()):
            avg = sum(m["moves"]) / len(m["moves"])
            best = min(m["moves"])
            losses = m["games"] - m["wins"]
            wr = m["wins"] / m["games"] if m["games"] else 0
            avg_sl = sum(m["ships_lost"]) / len(m["ships_lost"]) if m["ships_lost"] else 0
            avg_hr = sum(m["hits_received"]) / len(m["hits_received"]) if m["hits_received"] else 0
            surv = 5.0 - avg_sl

            wr_c = "green" if wr >= 0.9 else "yellow" if wr >= 0.7 else "red"
            surv_c = "green" if surv >= 4.0 else "yellow" if surv >= 3.0 else "red"

            trajectory = ""
            if len(m["moves"]) > 1:
                trajectory = " → ".join(str(x) for x in m["moves"])

            row_style = "on red" if losses > 0 and wr < 0.7 else ""
            tbl.add_row(
                opp,
                str(m["games"]),
                f"{m['wins']}/{losses}",
                f"[{wr_c}]{wr:.0%}[/]",
                f"{avg:.0f}",
                str(best),
                f"[{surv_c}]{surv:.1f}[/]",
                f"{avg_hr:.0f}",
                f"[dim]{trajectory}[/]",
                style=row_style,
            )
        con.print(tbl)

    # ── Placement weakness ────────────────────────────────────────────────────
    if metrics["per_opponent"]:
        weak_defense = []
        for opp, m in sorted(metrics["per_opponent"].items()):
            if m["ships_lost"]:
                avg_sl = sum(m["ships_lost"]) / len(m["ships_lost"])
                surv = 5.0 - avg_sl
                avg_hr = sum(m["hits_received"]) / len(m["hits_received"]) if m["hits_received"] else 0
                if surv < 3.0:
                    weak_defense.append((opp, surv, avg_hr, m["games"]))
        if weak_defense:
            wt = Table(title="Placement Weakness (survival < 3.0)", box=box.SIMPLE,
                       border_style="red", title_style="bold red")
            wt.add_column("Opponent", style="bold")
            wt.add_column("Survival", justify="right")
            wt.add_column("Hits", justify="right")
            wt.add_column("Games", justify="right")
            for opp, surv, avg_hr, games in sorted(weak_defense, key=lambda x: x[1]):
                wt.add_row(opp, f"[red]{surv:.1f}[/]", f"{avg_hr:.0f}", str(games))
            con.print(wt)

    # ── Memory health ─────────────────────────────────────────────────────────
    trust_map = metrics.get("trust_per_opponent", {})
    if trust_map:
        t_active  = sum(1 for t in trust_map.values() if t >= 0.15)
        t_high    = sum(1 for t in trust_map.values() if t >= 0.4)
        t_exploit = sum(1 for t in trust_map.values() if t >= 0.8)

        mg = Table.grid(padding=(0, 2))
        mg.add_column(style="bold cyan", min_width=20)
        mg.add_column()
        mg.add_row("Opponents Seen", str(len(trust_map)))
        mg.add_row("Trust >= 0.15", f"{t_active}  [dim](heatmap active)[/]")
        mg.add_row("Trust >= 0.40", f"{t_high}  [dim](exploit eligible)[/]")
        mg.add_row("Trust >= 0.80", f"{t_exploit}  [dim](high confidence)[/]")

        active = [(opp, t) for opp, t in sorted(trust_map.items()) if t >= 0.15]
        if active:
            mg.add_row("", "")
            for opp, t in active:
                bar_len = int(t * 20)
                bar = f"[green]{'█' * bar_len}[/][dim]{'░' * (20 - bar_len)}[/]"
                mg.add_row(f"  {opp}", f"{bar} {t:.2f}")

        con.print(Panel(mg, title="[bold white]Memory Health[/]",
                        border_style="magenta", box=box.ROUNDED))
    con.print()
