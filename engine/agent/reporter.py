"""
Supabase reporter — pushes run metrics to the dashboard database.

Reads SUPABASE_URL and SUPABASE_KEY from environment (or .env file).
If either is missing, reporting is silently skipped (local-only mode).
"""
import os
from pathlib import Path

# Load .env from backend/ directory
try:
    from dotenv import load_dotenv
    # Try relative to this file first
    _env_path = Path(__file__).resolve().parents[2] / "backend" / ".env"
    if not _env_path.exists():
        # Fallback: relative to cwd
        _env_path = Path.cwd() / "backend" / ".env"
    if _env_path.exists():
        load_dotenv(_env_path, override=True)
except Exception:
    pass

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        return None

    try:
        from supabase import create_client
        _client = create_client(url, key)
        return _client
    except Exception as e:
        print(f"  [reporter] Supabase init failed: {e}")
        return None


def report_run(metrics: dict, attempt_num: int = 1, battle_id: str = None):
    """
    Push a completed run's metrics to Supabase.
    Inserts into `runs` and `games` tables, upserts `opponents`.

    metrics: the dict from make_metrics_subscriber()
    battle_id: optional UUID linking this run to a battle session
    """
    sb = _get_client()
    if sb is None:
        print("  [reporter] Skipped — no Supabase credentials found")
        return

    try:
        _insert_run(sb, metrics, attempt_num, battle_id)
    except Exception as e:
        print(f"  [reporter] Failed to report run: {e}")


def _insert_run(sb, metrics: dict, attempt_num: int, battle_id: str = None):
    total_games = metrics.get("total_games", 0)
    if total_games == 0:
        return

    wins = metrics.get("wins", 0)
    losses = metrics.get("losses", 0)
    moves = metrics.get("moves_per_game", [])
    times = metrics.get("move_times_ms", [])
    improvements = metrics.get("improvements", [])

    # Compute aggregates
    avg_moves = sum(moves) / len(moves) if moves else 0
    avg_ms = sum(times) / len(times) if times else 0
    move_savings = sum(d for _, d in improvements)

    all_ships_lost = []
    all_hits = []
    for m in metrics.get("per_opponent", {}).values():
        all_ships_lost.extend(m.get("ships_lost", []))
        all_hits.extend(m.get("hits_received", []))
    ships_surviving = 5.0 - (sum(all_ships_lost) / len(all_ships_lost)) if all_ships_lost else 5.0
    hits_taken = sum(all_hits) / len(all_hits) if all_hits else 0

    # Use server's actual score if available, otherwise estimate
    total_score = metrics.get("server_score") or _estimate_score(metrics)

    # ── Insert run ────────────────────────────────────────────────────────────
    run_row = {
        "battle_id":        battle_id,
        "attempt_num":      attempt_num,
        "total_score":      total_score,
        "wins":             wins,
        "losses":           losses,
        "total_games":      total_games,
        "avg_moves":        round(avg_moves, 1),
        "avg_ms":           round(avg_ms, 1),
        "ships_surviving":  round(ships_surviving, 2),
        "hits_taken":       round(hits_taken, 1),
        "move_savings":     move_savings,
        "timeout_warnings": metrics.get("timeout_warnings", 0),
        "errors":           metrics.get("errors", 0),
        "status":           "complete",
    }
    result = sb.table("runs").insert(run_row).execute()
    run_id = result.data[0]["id"]

    # ── Insert games ──────────────────────────────────────────────────────────
    trust_map = metrics.get("trust_per_opponent", {})
    game_rows = []
    for opp, m in metrics.get("per_opponent", {}).items():
        for i in range(m["games"]):
            game_rows.append({
                "battle_id":     battle_id,
                "run_id":        run_id,
                "opponent_id":   opp,
                "won":           i < m["wins"],  # approximate: wins first, then losses
                "moves":         m["moves"][i] if i < len(m["moves"]) else 0,
                "ships_lost":    m["ships_lost"][i] if i < len(m.get("ships_lost", [])) else 0,
                "hits_received": m["hits_received"][i] if i < len(m.get("hits_received", [])) else 0,
                "trust":         round(trust_map.get(opp, 0), 3),
            })

    if game_rows:
        # Supabase batch insert (chunks of 100)
        for i in range(0, len(game_rows), 100):
            sb.table("games").insert(game_rows[i:i+100]).execute()

    # ── Upsert opponents ──────────────────────────────────────────────────────
    class_map = metrics.get("classification_per_opponent", {})
    stab_map = metrics.get("stability_per_opponent", {})
    for opp, m in metrics.get("per_opponent", {}).items():
        avg_m = sum(m["moves"]) / len(m["moves"]) if m["moves"] else 0
        best_m = min(m["moves"]) if m["moves"] else 0
        wr = m["wins"] / m["games"] if m["games"] else 0
        avg_sl = sum(m.get("ships_lost", [])) / len(m["ships_lost"]) if m.get("ships_lost") else 0
        avg_surv = 5.0 - avg_sl
        trust_val = trust_map.get(opp, 0)

        sb.table("opponents").upsert({
            "battle_id":      battle_id,
            "opponent_id":    opp,
            "classification": class_map.get(opp, "unknown"),
            "stability":      round(stab_map.get(opp, 0), 3),
            "games_played":   m["games"],
            "wins":           m["wins"],
            "win_rate":       round(wr, 3),
            "avg_moves":      round(avg_m, 1),
            "best_moves":     best_m,
            "avg_survival":   round(avg_surv, 2),
            "trust":          round(trust_val, 3),
            "exploitable":    trust_val >= 0.4,
        }, on_conflict="opponent_id").execute()

    print(f"  [reporter] Run #{run_id} reported to Supabase ({len(game_rows)} games)")


def _estimate_score(metrics: dict) -> int:
    """
    Approximate the competition score from metrics.
    Real score comes from server; this gives a reasonable dashboard estimate.
    Score = sum per game of: hit_points + sink_bonuses + base_score(if won) - loss_penalties
    """
    sink_bonus = {"CARRIER": 5, "BATTLESHIP": 4, "CRUISER": 3, "SUBMARINE": 3, "DESTROYER": 2}
    base_score_per_win = 15  # approximate average

    score = 0
    for opp, m in metrics.get("per_opponent", {}).items():
        for i in range(m["games"]):
            moves = m["moves"][i] if i < len(m["moves"]) else 50
            won = i < m["wins"]
            ships_lost = m["ships_lost"][i] if i < len(m.get("ships_lost", [])) else 0

            # Hits on opponent ships (17 total cells across 5 ships)
            if won:
                score += 17  # all hit points
                score += sum(sink_bonus.values())  # all sink bonuses
                score += base_score_per_win
            else:
                # Partial hits based on moves (rough estimate)
                score += min(moves, 17)

            # Loss penalties
            score -= ships_lost * 2
            # Approximate class loss penalty
            score -= ships_lost * 3

    return max(0, score)
