"""
StarSling Closed-Loop Agent
Run:  python -m engine.main
      python -m engine.main --url https://intern-battleship-game-server.vercel.app \
                            --competition <id> --rounds 4
"""
import argparse
import os
import time

# Default ship configuration — used as fallback when the server rules are
# unavailable or boardRules.shipClasses is missing.
_DEFAULT_SHIP_CLASSES = [
    ("CARRIER", 5), ("BATTLESHIP", 4), ("CRUISER", 3),
    ("SUBMARINE", 3), ("DESTROYER", 2),
]

from engine.agent.client import Client
from engine.agent.display import Display
from engine.agent.events import (
    EventEmitter, EventType,
    RegisteredEvent, AttemptStartedEvent, GameStartedEvent, MoveMadeEvent,
    PatternDetectedEvent, StrategyChangedEvent, GameEndedEvent,
    MemoryUpdatedEvent, AttemptEndedEvent, TimeoutWarningEvent, ErrorEvent,
    make_display_subscriber, make_metrics_subscriber, print_metrics_summary,
)
from engine.agent.logger import GameLogger, make_log_subscriber
from engine.agent.bandit import BanditStore
from engine.strategies.heatmap import Heatmap
from engine.agent.feedback import FeedbackEngine, FeedbackStore
from engine.agent.react import ReActAgent, Observation
from engine.models.opponent import Memory
from engine.strategies.targeting import Targeting
from engine.strategies.placement import Placement

# Real API outcome values → internal result strings
_OUTCOME = {"HIT": "hit", "MISS": "miss", "SINK": "sunk"}
_SHIP_SIZES = {"CARRIER": 5, "BATTLESHIP": 4, "CRUISER": 3, "SUBMARINE": 3, "DESTROYER": 2}


import numpy as np

# Cached anti-occupancy prior (computed once per board_size + ship config)
def _anti_occupancy_prior(board_size: int, ship_classes: list[tuple],
                          noisy: bool = True) -> "np.ndarray":
    """
    Uniform noise prior with no systematic bias.

    Earlier versions computed occupancy density (center = high, edges = low)
    and placed ships in LOW-density cells — pushing ships to edges/corners.
    This was catastrophically exploitable: smart opponents sweep edges first.

    Now returns a flat grid with per-cell noise so candidate scoring still
    differentiates placements (via opponent-specific firing data or spread bonus)
    without introducing any systematic positional bias.
    """
    base = np.ones((board_size, board_size), dtype=np.float64)
    if noisy:
        noise = np.random.uniform(0.8, 1.2, size=base.shape)
        return base * noise
    return base


def _get_outcome(resp: dict) -> str | None:
    """
    Extract game outcome from a response envelope.
    Real API uses 'gameOutcome'; mock server uses 'outcome'.
    Check both for compatibility.
    """
    return resp.get("gameOutcome") or resp.get("outcome")


def _game_state(resp: dict) -> dict:
    """
    Extract game state from a response envelope.
    Real API nests all game fields under a 'state' key:
      { "responseType": "MOVE_REQUIRED", "state": { "gameOrdinal": 1, ... } }
    For GAME_COMPLETED the mock also includes 'state' with the final game snapshot.
    Returns {} if no state is available (e.g. real API GAME_COMPLETED without state).
    """
    return resp.get("state", {})


def _safe_fire(client, row: int, col: int, http_budget: float,
               prev_shot_count: int = 0) -> dict:
    """
    Fire a shot with safe retry.  If the request fails, poll current state
    to determine whether the shot was accepted before retrying.  Re-firing
    the same cell would cause ATTEMPT_DISQUALIFIED.

    prev_shot_count: number of yourShots BEFORE this shot — used to detect
                     whether the shot was accepted even if the game advanced
                     to a new context (GAME_COMPLETED → next game).
    """
    import requests
    try:
        return client.fire_shot(row, col, http_timeout=http_budget)
    except (requests.exceptions.RequestException, requests.exceptions.Timeout) as orig_err:
        # Request failed (timeout or network) but may have reached the server.
        # Poll current state to check.
        try:
            current = client.get_current()
        except Exception:
            # Can't poll — do NOT retry blindly (shot may have been accepted)
            raise RuntimeError(
                f"Shot ({row},{col}) failed and state poll also failed — "
                f"not retrying to avoid duplicate shot DQ"
            ) from orig_err

        rt = current.get("responseType")

        # If the attempt ended or was DQ'd, return the terminal state
        if rt in ("ATTEMPT_COMPLETED", "ATTEMPT_DISQUALIFIED"):
            return current

        gs = current.get("state", {})
        your_shots = gs.get("yourShots", [])

        # Check 1: shot count increased → our shot was accepted
        if len(your_shots) > prev_shot_count:
            return current

        # Check 2: game advanced (GAME_COMPLETED → next game with empty yourShots)
        # If the game moved to PLACE_SHIPS, our shot ended the previous game.
        # We can't determine the true outcome from the polled state, so we use
        # "UNKNOWN" rather than forcing a loss — an incorrect OPPONENT_WIN would
        # corrupt OpponentModel.wins, bandit scores, and feedback lessons.
        # The GAME_COMPLETED handler skips learning for UNKNOWN outcomes.
        if gs.get("nextRequiredMove") == "PLACE_SHIPS" and prev_shot_count > 0:
            return {
                "responseType": "GAME_COMPLETED",
                "gameOutcome": "UNKNOWN",
                "outcome": "UNKNOWN",  # backward compat with mock server
                "state": {},  # game state unavailable — fallback to last_gs
                "next": current,
            }

        # Shot was NOT recorded — safe to retry once
        try:
            return client.fire_shot(row, col, http_timeout=http_budget)
        except Exception as retry_err:
            raise RuntimeError(f"Shot ({row},{col}) retry also failed") from retry_err


def play_attempt(client, memory, emitter, feedback, bandit_store,
                 attempt_num, board_size, ship_classes, turn_timeout,
                 allow_adjacency: bool = True):
    """
    Play one full Attempt (all 15 games sequentially).
    Ships are placed fresh before each game.
    Returns (wins, losses) for this attempt.
    """
    http_budget = max(1.0, turn_timeout - 0.5)

    emitter.emit(EventType.ATTEMPT_STARTED, AttemptStartedEvent(
        attempt_num=attempt_num,
        prior_attempts=attempt_num - 1,
        memory_opponents=len(memory.models),
    ))

    try:
        state = client.start_attempt()
    except Exception as e:
        # 409 means a prior attempt is still active — abandon and retry once
        is_409 = (
            hasattr(e, "response")
            and getattr(e.response, "status_code", None) == 409
        )
        if is_409:
            try:
                client.abandon()
                state = client.start_attempt()
            except Exception as e2:
                emitter.emit(EventType.ERROR, ErrorEvent(
                    context=f"attempt {attempt_num} start (abandon+retry)",
                    message=str(e2),
                    recoverable=False,
                ))
                return 0, 0, None
        else:
            emitter.emit(EventType.ERROR, ErrorEvent(
                context=f"attempt {attempt_num} start",
                message=str(e),
                recoverable=False,
            ))
            return 0, 0, None

    wins   = 0
    losses = 0
    _server_score = None
    games_detail: list[dict] = []   # per-game summaries for attempt log

    # Per-game state — reset on each PLACE_SHIPS
    model:        object       = None
    agent:        object       = None
    obs:          object       = None
    opponent_id:  str          = ""
    move_count:   int          = 0
    move_times:   list[float]  = []
    prev_incoming: int         = 0
    bandit_strategy: str       = None
    baseline:     object       = None
    game_num:     int          = 0
    prev_strategy: str         = None
    last_gs:      dict         = {}   # last known game state from MOVE_REQUIRED

    while True:
        rt = state.get("responseType")

        # ── Disqualified ───────────────────────────────────────────────────────
        if rt == "ATTEMPT_DISQUALIFIED":
            ctx = state.get("context", {})
            emitter.emit(EventType.ERROR, ErrorEvent(
                context=f"attempt {attempt_num} game {ctx.get('gameOrdinal','?')}",
                message=(
                    f"DISQUALIFIED: {state.get('reason', '?')} "
                    f"at {ctx.get('lastRequiredMove','?')} "
                    f"(opponent: {ctx.get('opponentId','?')})"
                ),
                recoverable=False,
            ))
            break

        # ── All 15 games done ──────────────────────────────────────────────────
        if rt == "ATTEMPT_COMPLETED":
            raw_outcome = _get_outcome(state)
            outcome_known = raw_outcome in ("AGENT_WIN", "OPPONENT_WIN")
            if model is not None and outcome_known:
                we_won   = raw_outcome == "AGENT_WIN"
                final_gs = _game_state(state) or last_gs
                _record_game(
                    final_gs, model, memory, bandit_store, feedback, emitter,
                    opponent_id, game_num, move_count, move_times, we_won,
                    baseline, bandit_strategy,
                )
                if we_won:
                    wins += 1
                else:
                    losses += 1
                games_detail.append({
                    "game": game_num, "opponent": opponent_id,
                    "won": we_won, "moves": move_count,
                    "strategy": bandit_strategy or "probability",
                })
            # Capture server's finalScore for dashboard reporting
            result_block = state.get("result", {})
            _server_score = result_block.get("finalScore")
            break

        # ── Game ended, next game available ───────────────────────────────────
        if rt == "GAME_COMPLETED":
            raw_outcome = _get_outcome(state)
            outcome_known = raw_outcome in ("AGENT_WIN", "OPPONENT_WIN")
            we_won = raw_outcome == "AGENT_WIN"
            if model is not None and outcome_known:
                # Skip learning for UNKNOWN outcomes (network-recovery synthetics)
                # — recording a guessed result would corrupt bandit/feedback data.
                final_gs = _game_state(state) or last_gs
                _record_game(
                    final_gs, model, memory, bandit_store, feedback, emitter,
                    opponent_id, game_num, move_count, move_times, we_won,
                    baseline, bandit_strategy,
                )
            if outcome_known:
                if we_won:
                    wins += 1
                else:
                    losses += 1
                games_detail.append({
                    "game": game_num, "opponent": opponent_id,
                    "won": we_won, "moves": move_count,
                    "strategy": bandit_strategy or "probability",
                })

            state = state.get("next", {})
            if not state:
                break

            # Reset per-game state — re-initialised on next PLACE_SHIPS
            client.reset_game_state()
            model         = None
            agent         = None
            obs           = None
            move_count    = 0
            move_times    = []
            prev_incoming = 0
            prev_strategy = None
            last_gs       = {}
            continue

        # ── MOVE_REQUIRED ──────────────────────────────────────────────────────
        gs = _game_state(state)
        if gs:
            last_gs = gs   # only update when we have a valid state
        nr = gs.get("nextRequiredMove")

        # If the state is empty (server omitted it) try recovering via polling
        if not nr:
            try:
                polled = client.get_current()
                prt = polled.get("responseType")
                if prt in ("ATTEMPT_COMPLETED", "ATTEMPT_DISQUALIFIED", "GAME_COMPLETED"):
                    state = polled
                    continue  # re-enter loop to handle the terminal state
                pgs = _game_state(polled)
                if pgs:
                    gs = pgs
                    last_gs = pgs
                    nr = pgs.get("nextRequiredMove")
                    state = polled
            except Exception:
                pass
            if not nr:
                emitter.emit(EventType.ERROR, ErrorEvent(
                    context=f"attempt {attempt_num} game {game_num}",
                    message="Empty game state and poll failed — cannot determine next move",
                    recoverable=False,
                ))
                break

        # ── Place ships ────────────────────────────────────────────────────────
        if nr == "PLACE_SHIPS":
            game_num    += 1
            opponent_id  = gs["opponent"]["opponentId"]
            model        = memory.get(opponent_id)
            baseline     = model.last_moves()

            known_fire  = model.is_fixed_firing()

            # ── Trust score: continuous measure of how much to trust learned priors
            # prediction_accuracy() returns overlap (0=bad, 1=perfect prediction)
            stability   = model.placement_stability()
            fire_stab   = model.firing_stability()
            pred_acc    = model.prediction_accuracy()  # None if < 2 placements
            # Faster ramp: 0→1 over 5 games (was 10).
            # With 15 games per attempt, need useful trust by game 3-4.
            sample_conf = min(model.games_played / 5.0, 1.0)

            # Prediction accuracy proxy:
            # - If we have actual prediction data, use it directly.
            # - If stability is very high (> 0.9) with 2+ games, placements
            #   are nearly identical → predictions WOULD be accurate. Use
            #   stability as proxy so scouts aren't blocked for 3 games.
            # - If firing is very stable, that's also a trust signal — the
            #   opponent is predictable even if we can't see their placements.
            # - Otherwise: no evidence = no trust.
            if pred_acc is not None:
                pa = pred_acc
            elif stability > 0.9 and model.games_played >= 2:
                pa = stability  # near-identical placements → trust early
            elif fire_stab > 0.5 and model.games_played >= 2:
                pa = fire_stab * 0.7  # firing pattern is stable → partial trust
            else:
                pa = 0.0

            trust = stability * pa * sample_conf
            opp_type = model.classify()

            # ── Trust gating: hard cutoffs ──────────────────────────────
            # trust < 0.15 → UNTRUSTED: no heatmap, no exploit, no memory
            #                Agent plays as if seeing this opponent for first time.
            # trust 0.15–0.4 → LOW: weak heatmap, defensive avoidance
            # trust >= 0.4  → TRUSTED: full heatmap + exploit eligible
            _TRUST_MIN = 0.15

            # Model reset: bad predictions + degrading → forget stale data
            if (pred_acc is not None and pred_acc < 0.15
                    and model.is_degrading()
                    and model.games_played >= 4):
                model.ship_placements = model.ship_placements[-1:]
                trust = 0.0  # force untrusted after reset

            # Exploit: fire at known positions. Threshold scales with data:
            # more games → more confidence even with slightly lower accuracy.
            _exploit_acc_min = 0.80 if model.games_played >= 15 else 0.90
            known_place = (
                trust >= 0.35
                and model.is_fixed_placement(min_games=5)
                and stability > 0.65
                and (pred_acc is not None and pred_acc > _exploit_acc_min)
            )

            available       = ["exploit", "hunt", "probability"] if known_place else ["hunt", "probability"]
            chosen_strategy = bandit_store.bandit.select(opponent_id, available=available)
            bandit_strategy = chosen_strategy
            pa_disp = f"{pred_acc:.2f}" if pred_acc is not None else f"~{pa:.2f}"
            n_place = len(model.ship_placements)
            n_valid = sum(1 for p in model.ship_placements if len(p) >= 9)
            fire_arch_disp = model.fire_archetype()
            strategy_reason = (
                f"bandit (trust={trust:.2f} {opp_type}"
                f" | stab={stability:.2f} fire_stab={fire_stab:.2f} pa={pa_disp}"
                f" fire={fire_arch_disp}"
                f" games={model.games_played} place={n_valid}/{n_place})"
            )

            emitter.emit(EventType.GAME_STARTED, GameStartedEvent(
                game_num=game_num,
                opponent_id=opponent_id,
                known_placement=known_place,
                known_firing=known_fire,
                games_vs_opponent=model.games_played,
                win_rate=model.wins / model.games_played if model.games_played else 0.0,
                chosen_strategy=chosen_strategy,
                strategy_reason=strategy_reason,
                trust=trust,
                classification=opp_type,
                stability=stability,
            ))

            targeter = Targeting(board_size, ship_classes=ship_classes)

            # Below _TRUST_MIN → skip heatmap entirely (pure probability/hunt)
            # Above threshold → weight scales with trust^1.5:
            #   trust 0.20 → weight 0.45
            #   trust 0.40 → weight 1.26
            #   trust 0.60 → weight 2.32
            #   trust 0.80 → weight 3.58
            #   trust 1.00 → weight 5.00
            if trust >= _TRUST_MIN and model.ship_placements:
                heatmap = Heatmap.from_model(model, board_size=board_size)
                # High trust → max heatmap weight. At trust>0.7 we're confident
                # enough to go near-deterministic on the heatmap prior.
                if trust >= 0.7:
                    heatmap_weight = 8.0  # very aggressive — almost pure heatmap
                else:
                    heatmap_weight = trust * 5.0
                targeter.apply_heatmap(heatmap, weight=heatmap_weight)
                pa_str = f"pred_acc={pred_acc:.2f}" if pred_acc is not None else "pred_acc=N/A"
                emitter.emit(EventType.PATTERN_DETECTED, PatternDetectedEvent(
                    opponent_id=opponent_id,
                    pattern_type="heatmap_prior",
                    games_confirmed=heatmap.games_observed,
                    detail=f"{heatmap.summary(opponent_id)} | {pa_str} trust={trust:.2f}",
                ))

            if known_place:
                known = model.known_targets()
                if known:
                    targeter.inject_known_targets(known)

            # Defensive placement:
            #   Firing data is ALWAYS used if available — decoupled from trust.
            #   Trust gates offensive heatmaps (predicting ship placement),
            #   but defensive avoidance (where they shoot) is a different signal.
            #   Even 1 game of firing data is better than nothing.
            # Defensive placement: use OPENING heatmap (first 12 shots per game)
            # as primary signal. Opening shots are the most predictable and
            # determine whether we survive long enough for targeting to matter.
            uniform_noise = _anti_occupancy_prior(board_size, ship_classes)
            avoid         = model.dangerous_squares()
            opening       = model.opening_heatmap(board_size)
            full_freq     = model.shot_frequency_map(board_size)
            fire_arch     = model.fire_archetype()

            if opening is not None:
                # Opening heatmap is the primary defensive signal.
                obs_weight = min(0.9, 0.6 + 0.04 * len(model.firing_sequences))
                if full_freq is not None:
                    combined = 0.7 * opening + 0.3 * full_freq
                else:
                    combined = opening

                # Hard-avoid rows where opponent concentrates opening fire.
                # If 60%+ of opening shots land in rows 0-2, those rows are
                # death zones — no ship should be placed there regardless of
                # candidate scoring. This converts soft penalty → hard constraint.
                if len(model.firing_sequences) >= 3:
                    top3_mass = float(opening[:3, :].sum())
                    total_mass = float(opening.sum())
                    if total_mass > 0 and top3_mass / total_mass > 0.55:
                        for _r in range(3):
                            for _c in range(board_size):
                                avoid.add((_r, _c))
                        # Also check row 3 — if 75%+ is in rows 0-3, avoid row 3 too
                        top4_mass = float(opening[:4, :].sum())
                        if top4_mass / total_mass > 0.70:
                            for _c in range(board_size):
                                avoid.add((3, _c))

                shot_freq = obs_weight * combined + (1 - obs_weight) * uniform_noise
                n_candidates = 500
            else:
                shot_freq = uniform_noise
                n_candidates = 100
            placer     = Placement(board_size, ship_classes,
                                   allow_adjacency=allow_adjacency)
            try:
                placements = placer.place(avoid=avoid, shot_frequency=shot_freq,
                                          num_candidates=n_candidates)
            except Exception as e:
                emitter.emit(EventType.ERROR, ErrorEvent(
                    context=f"attempt {attempt_num} game {game_num} placer",
                    message=f"Placement algorithm failed: {e}",
                    recoverable=False,
                ))
                break

            # Log placement row distribution for diagnostics
            _ship_sizes = dict(ship_classes)
            _placed_rows = []
            for p in placements:
                sz = _ship_sizes[p["shipClass"]]
                cells = [(p["startRow"] + i, p["startCol"]) if p["orientation"] == "VERTICAL"
                         else (p["startRow"], p["startCol"] + i) for i in range(sz)]
                _placed_rows.extend(r for r, c in cells)
            _row_min, _row_max = min(_placed_rows), max(_placed_rows)
            _top3 = sum(1 for r in _placed_rows if r <= 2)
            _bot5 = sum(1 for r in _placed_rows if r >= 5)
            emitter.emit(EventType.PATTERN_DETECTED, PatternDetectedEvent(
                opponent_id=opponent_id,
                pattern_type="placement_zone",
                games_confirmed=len(model.firing_sequences),
                detail=f"rows {_row_min}-{_row_max} | top3={_top3}/{len(_placed_rows)} bot5={_bot5}/{len(_placed_rows)} fire={fire_arch}",
            ))

            try:
                state = client.place_ships(placements, http_timeout=http_budget)
            except Exception as e:
                emitter.emit(EventType.ERROR, ErrorEvent(
                    context=f"attempt {attempt_num} game {game_num} place_ships",
                    message=str(e),
                    recoverable=False,
                ))
                break

            agent         = ReActAgent(targeter, model, turn_timeout)
            obs           = None
            move_count    = 0
            move_times    = []
            prev_incoming = 0

        # ── Fire shot ──────────────────────────────────────────────────────────
        elif nr == "SUBMIT_SHOT":
            if agent is None:
                # SUBMIT_SHOT before PLACE_SHIPS — server state mismatch
                emitter.emit(EventType.ERROR, ErrorEvent(
                    context=f"attempt {attempt_num} game {game_num}",
                    message="SUBMIT_SHOT received before agent was initialised",
                    recoverable=False,
                ))
                break

            reasoning = agent.reason(obs if obs is not None else Observation())

            if reasoning.strategy != prev_strategy and prev_strategy is not None:
                emitter.emit(EventType.STRATEGY_CHANGED, StrategyChangedEvent(
                    opponent_id=opponent_id,
                    from_strategy=prev_strategy,
                    to_strategy=reasoning.strategy,
                    reason=reasoning.rationale[:80],
                ))
            prev_strategy = reasoning.strategy

            t0       = time.perf_counter()
            row, col = agent.act(reasoning)

            try:
                shot_count = len(last_gs.get("yourShots", []))
                state = _safe_fire(client, row, col, http_budget,
                                   prev_shot_count=shot_count)
            except RuntimeError as e:
                emitter.emit(EventType.ERROR, ErrorEvent(
                    context=f"attempt {attempt_num} game {game_num} turn {move_count}",
                    message=str(e),
                    recoverable=False,
                ))
                break

            elapsed_ms = (time.perf_counter() - t0) * 1000
            move_times.append(elapsed_ms)

            # Shot outcome lives in game state (may be empty for real-API GAME_COMPLETED)
            gs_now     = _game_state(state)
            if gs_now:
                last_gs = gs_now  # keep latest state for GAME_COMPLETED fallback
            your_shots = gs_now.get("yourShots", [])
            # Look up OUR shot by coordinate — competition server may not
            # return yourShots in chronological order, so [-1] is unreliable.
            last_shot  = {}
            for _s in your_shots:
                try:
                    if int(_s.get("row", -1)) == row and int(_s.get("col", -1)) == col:
                        last_shot = _s
                        break
                except (ValueError, TypeError):
                    continue
            # Fallback: index by pre-shot count (works if chronological)
            if not last_shot and len(your_shots) > shot_count:
                last_shot = your_shots[shot_count]
            outcome    = _OUTCOME.get(last_shot.get("outcome", "MISS"), "miss")
            sunk_ship_size = None
            sunk_class = None
            if outcome == "sunk":
                sunk_class = last_shot.get("sunkShipClass")
                sunk_ship_size = _SHIP_SIZES.get(sunk_class)

            # Fallback for real-API GAME_COMPLETED (no 'state' key):
            # We can't infer the exact shot outcome without game state.
            # Use last known state's yourShots if available, otherwise
            # mark as "hit" (safe: doesn't falsely trigger sunk-ship logic).
            if not gs_now:
                rt_now_fb = state.get("responseType")
                if rt_now_fb in ("GAME_COMPLETED", "ATTEMPT_COMPLETED"):
                    outcome = "hit" if _get_outcome(state) == "AGENT_WIN" else "miss"

            # New incoming shots since last turn
            incoming    = gs_now.get("incomingShots", [])
            new_shots   = incoming[prev_incoming:]
            opp_shot    = (int(new_shots[-1]["row"]), int(new_shots[-1]["col"])) if new_shots else None
            if gs_now:
                prev_incoming = len(incoming)

            # Map response type → game status for Observation + pre_compute_next
            rt_now = state.get("responseType")
            if rt_now in ("GAME_COMPLETED", "ATTEMPT_COMPLETED"):
                game_status = "won" if _get_outcome(state) == "AGENT_WIN" else "lost"
            elif rt_now == "ATTEMPT_DISQUALIFIED":
                game_status = "lost"
            else:
                game_status = "ongoing"

            obs = agent.observe(outcome, (row, col), opp_shot, game_status, move_count,
                                sunk_ship_size=sunk_ship_size,
                                sunk_ship_class=sunk_class)
            agent.pre_compute_next(game_status)

            emitter.emit(EventType.MOVE_MADE, MoveMadeEvent(
                game_num=game_num,
                turn=move_count,
                coord=(row, col),
                result=outcome,
                elapsed_ms=elapsed_ms,
                strategy=reasoning.strategy,
                confidence=reasoning.confidence,
                move_reason=reasoning.move_reason,
            ))

            if elapsed_ms > turn_timeout * 1000 * 0.7:
                emitter.emit(EventType.TIMEOUT_WARNING, TimeoutWarningEvent(
                    game_num=game_num,
                    turn=move_count,
                    elapsed_ms=elapsed_ms,
                    budget_ms=turn_timeout * 1000,
                ))

            move_count += 1

        else:
            # Unknown nextRequiredMove — safety exit
            break

    emitter.emit(EventType.ATTEMPT_ENDED, AttemptEndedEvent(
        attempt_num=attempt_num,
        wins=wins,
        losses=losses,
        games_detail=games_detail,
        server_score=_server_score,
    ))
    return wins, losses, _server_score


def _record_game(gs, model, memory, bandit_store, feedback, emitter,
                 opponent_id, game_num, move_count, move_times, we_won,
                 baseline, bandit_strategy):
    """
    Record game result into memory/bandit/feedback and emit events.
    gs: game state dict (from _game_state()), may be empty if real API
        didn't include it — gracefully degrades (no ship placement recorded).
    """
    avg_ms = sum(move_times) / len(move_times) if move_times else 0

    # Defensive metrics: count ships lost and total hits received
    our_fleet = gs.get("yourFleet", [])
    ships_lost = sum(1 for s in our_fleet if s.get("sunk", False))
    lost_classes = [s["shipClass"] for s in our_fleet if s.get("sunk", False)]
    hits_received = sum(
        1 for s in gs.get("incomingShots", [])
        if s.get("outcome") in ("HIT", "SINK")
    )

    # Opponent ships we sunk (from our shot outcomes)
    sunk_classes = [
        s["sunkShipClass"] for s in gs.get("yourShots", [])
        if s.get("outcome") == "SINK" and s.get("sunkShipClass")
    ]

    # Loss margin: how many enemy ship cells we hadn't hit yet
    our_hits_on_enemy = sum(
        1 for s in gs.get("yourShots", [])
        if s.get("outcome") in ("HIT", "SINK")
    )
    enemy_cells_remaining = 17 - our_hits_on_enemy  # 17 total ship cells

    emitter.emit(EventType.GAME_ENDED, GameEndedEvent(
        game_num=game_num,
        opponent_id=opponent_id,
        won=we_won,
        total_moves=move_count,
        avg_ms=avg_ms,
        baseline_moves=baseline,
        ships_lost=ships_lost,
        hits_received=hits_received,
        sunk_classes=sunk_classes,
        lost_classes=lost_classes,
        enemy_cells_remaining=enemy_cells_remaining,
    ))

    their_shots = [
        (int(s["row"]), int(s["col"])) for s in gs.get("incomingShots", [])
    ]
    # Ship cells inferred from our HIT/SINK shots — complete when we win (all 17 hit).
    # On losses we still record partial data — helps heatmap learn faster.
    ship_cells = [
        (int(s["row"]), int(s["col"]))
        for s in gs.get("yourShots", [])
        if s.get("outcome") in ("HIT", "SINK")
    ]
    model.record_game(
        their_shots, ship_cells, we_won,
        record_placement=bool(ship_cells),
    )
    model.record_moves(move_count)
    try:
        memory.save()
    except Exception as e:
        emitter.emit(EventType.ERROR, ErrorEvent(
            context="memory save", message=str(e), recoverable=True,
        ))

    if bandit_strategy is not None:
        bandit_store.bandit.update(opponent_id, bandit_strategy, move_count,
                                   won=we_won, ships_lost=ships_lost)
        try:
            bandit_store.save()
        except Exception as e:
            emitter.emit(EventType.ERROR, ErrorEvent(
                context="bandit save", message=str(e), recoverable=True,
            ))

    lessons = feedback.generate(opponent_id, model, {
        "won":            we_won,
        "moves":          move_count,
        "avg_ms":         avg_ms,
        "strategy_used":  bandit_strategy or "probability",
        "baseline_moves": baseline,
        "ships_lost":     ships_lost,
        "hits_received":  hits_received,
    })
    for lesson in lessons:
        feedback.store.add(lesson)
        emitter.emit(EventType.PATTERN_DETECTED, PatternDetectedEvent(
            opponent_id=opponent_id,
            pattern_type=lesson.lesson_type,
            games_confirmed=lesson.games_basis,
            detail=lesson.summary,
        ))

    if model.is_fixed_placement(min_games=5):
        emitter.emit(EventType.PATTERN_DETECTED, PatternDetectedEvent(
            opponent_id=opponent_id,
            pattern_type="fixed_placement",
            games_confirmed=model.games_played,
            detail="ships always in same positions — will exploit next game",
        ))
    if model.is_fixed_firing(min_games=5):
        emitter.emit(EventType.PATTERN_DETECTED, PatternDetectedEvent(
            opponent_id=opponent_id,
            pattern_type="fixed_firing",
            games_confirmed=model.games_played,
            detail="fires in fixed sequence — placement now avoids hot squares",
        ))

    emitter.emit(EventType.MEMORY_UPDATED, MemoryUpdatedEvent(
        opponent_id=opponent_id,
        games_played=model.games_played,
        fixed_placement=model.is_fixed_placement(),
        fixed_firing=model.is_fixed_firing(),
        win_rate=model.wins / model.games_played if model.games_played else 0,
    ))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url",         default=os.environ.get("ENGINE_SERVER_URL", "https://aegis-n8at.onrender.com"))
    parser.add_argument("--competition", default="mock-competition")
    parser.add_argument("--memory",      default="data/memory.json")
    parser.add_argument("--lessons",     default="data/lessons.json")
    parser.add_argument("--bandit",      default="data/bandit.json")
    parser.add_argument("--log",         default="data/game_log.jsonl")
    parser.add_argument("--rounds",      type=int, default=1)
    parser.add_argument("--battle-id",   default=None, help="UUID linking this run to a battle session")
    args = parser.parse_args()

    # Ensure data directory exists
    os.makedirs(os.path.dirname(args.memory) or ".", exist_ok=True)

    display      = Display()
    client       = Client(base_url=args.url, competition_id=args.competition)
    memory       = Memory(path=args.memory)
    feedback     = FeedbackEngine(FeedbackStore(path=args.lessons))
    bandit_store = BanditStore(path=args.bandit)

    logger = GameLogger(path=args.log)
    logger.open()

    emitter = EventEmitter()
    for event_type, handler in make_display_subscriber(display).items():
        emitter.on(event_type, handler)
    metrics, metric_handlers = make_metrics_subscriber()
    for event_type, handler in metric_handlers.items():
        emitter.on(event_type, handler)
    for event_type, handler in make_log_subscriber(logger).items():
        emitter.on(event_type, handler)

    existing = memory.summary()
    if existing:
        print("\n  Loaded memory:")
        for row in existing:
            print(f"    {row}")

    prior_lessons = feedback.store.summary()
    if prior_lessons:
        print("\n  Loaded lessons:")
        for row in prior_lessons:
            print(f"    {row}")

    bandit_summary = bandit_store.summary()
    if bandit_summary:
        print("\n  Bandit state (win rates per strategy):")
        for row in bandit_summary:
            print(row)

    # ── Fetch competition rules ────────────────────────────────────────────────
    try:
        rules = client.get_rules()
    except Exception as e:
        print(f"  Warning: could not fetch rules ({e}) — using defaults")
        rules = {}

    board_rules = rules.get("boardRules", {})
    board_size  = board_rules.get("gridRows", 10)

    # Real API uses "class"/"length" — not "name"/"size"
    ship_classes = [
        (c["class"], c["length"])
        for c in board_rules.get("shipClasses", [])
    ]
    if not ship_classes:
        ship_classes = _DEFAULT_SHIP_CLASSES

    # allowAdjacency=False means Phase 2 (adjacent ships) is illegal → must skip it
    allow_adjacency = board_rules.get("allowAdjacency", True)

    turn_timeout   = rules.get("turnTimeoutSeconds", 10)
    opponent_roster = rules.get("opponentRoster", [])
    num_opponents   = len(opponent_roster)

    emitter.emit(EventType.REGISTERED, RegisteredEvent(
        player_id=args.competition,
        turn_timeout=turn_timeout,
        num_opponents=num_opponents,
    ))

    # ── Play rounds ────────────────────────────────────────────────────────────
    total_wins  = 0
    total_games = 0

    for round_num in range(1, args.rounds + 1):
        wins, losses, server_score = play_attempt(
            client, memory, emitter, feedback, bandit_store,
            attempt_num=round_num,
            board_size=board_size,
            ship_classes=ship_classes,
            turn_timeout=turn_timeout,
            allow_adjacency=allow_adjacency,
        )
        total_wins  += wins
        total_games += wins + losses
        if server_score is not None:
            metrics["server_score"] = server_score

    display.summary(total_wins, total_games)

    try:
        board = client.leaderboard()
        if board:
            display.leaderboard(board, args.competition)
    except Exception:
        pass  # don't let leaderboard crash the run

    print_metrics_summary(metrics)

    # Report to Supabase dashboard (silently skipped if env vars not set)
    from engine.agent.reporter import report_run
    report_run(metrics, attempt_num=args.rounds,
               battle_id=getattr(args, 'battle_id', None),
               log_file=args.log)

    logger.close()
    print(f"  Log written to: {args.log}")


if __name__ == "__main__":
    main()
