#!/usr/bin/env python3
"""
AEGIS Loss Taxonomy & Per-Opponent Analytics

Parses battle logs + memory.json to answer:
  1. WHY are we losing to each opponent?
  2. Which losses are close (targeting issue) vs blowouts (defensive collapse)?
  3. Which opponents are exploitable and which are brick walls?
  4. Opening-shot fingerprints: how consistent is each opponent's search pattern?

Usage:
    python scripts/analytics.py [--recent N]  # analyze last N battle files (default: all)
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

# ── Config ───────────────────────────────────────────────────────────────────

BATTLE_DIR = Path("data/prod/battles")
MEMORY_FILE = Path("data/prod/memory.json")
TOTAL_SHIP_CELLS = 17  # 5+4+3+3+2

SHIP_SIZES = {"CARRIER": 5, "BATTLESHIP": 4, "CRUISER": 3, "SUBMARINE": 3, "DESTROYER": 2}

# Scoring constants (from competition rules)
SINK_BONUS = {"CARRIER": 10, "BATTLESHIP": 8, "CRUISER": 7, "SUBMARINE": 6, "DESTROYER": 4}
BASE_WIN = 14
PER_SHIP_LOSS_PENALTY = -2


# ── Data extraction ──────────────────────────────────────────────────────────

def parse_battle_file(fpath: Path) -> list[dict]:
    """Extract per-game records from a battle log file."""
    games = []
    current_game = None
    our_hits = 0
    our_sinks = 0
    our_misses = 0
    strategy_used = None
    trust_info = None

    with open(fpath) as f:
        for line in f:
            ev = json.loads(line)
            etype = ev["event"]

            if etype == "game_started":
                d = ev["data"]
                current_game = d["game_num"]
                our_hits = 0
                our_sinks = 0
                our_misses = 0
                strategy_used = d.get("chosen_strategy")
                trust_info = d.get("strategy_reason", "")

            elif etype == "move" and ev["data"].get("game_num") == current_game:
                r = ev["data"]["result"]
                if r == "hit":
                    our_hits += 1
                elif r == "sunk":
                    our_sinks += 1
                else:
                    our_misses += 1

            elif etype == "game_ended" and ev["data"].get("game_num") == current_game:
                d = ev["data"]
                games.append({
                    "game_num": d["game_num"],
                    "opponent": d["opponent_id"],
                    "won": d["won"],
                    "total_moves": d["total_moves"],
                    "ships_lost": d["ships_lost"],
                    "hits_received": d["hits_received"],
                    "our_hits": our_hits,
                    "our_sinks": our_sinks,
                    "our_misses": our_misses,
                    "our_accuracy": (our_hits + our_sinks) / max(d["total_moves"], 1),
                    "strategy": strategy_used,
                    "trust_info": trust_info,
                    "file": fpath.name,
                })
                current_game = None

    return games


def load_memory() -> dict:
    """Load opponent memory data."""
    if not MEMORY_FILE.exists():
        return {}
    with open(MEMORY_FILE) as f:
        return json.load(f)


# ── Loss classification ──────────────────────────────────────────────────────

def classify_loss(game: dict) -> str:
    """
    Classify a loss:
      close_loss:          We hit 12+ of 17 cells — targeting was decent, just outpaced
      defensive_collapse:  hits_received >= 16 AND total_moves < 45 — found fast
      targeting_failure:   We hit < 8 cells — couldn't find their ships
      standard_loss:       Everything else
    """
    our_successful = game["our_hits"] + game["our_sinks"]
    moves = game["total_moves"]

    if our_successful >= 12:
        return "close_loss"
    elif moves < 45 and game["hits_received"] >= 15:
        return "defensive_collapse"
    elif our_successful < 8:
        return "targeting_failure"
    else:
        return "standard_loss"


# ── Opening-shot fingerprint ─────────────────────────────────────────────────

def opening_fingerprint(memory: dict, board_size: int = 10, window: int = 10):
    """
    For each opponent, compute:
      - Most common first 5 and first 10 shots
      - Consistency score (Jaccard of consecutive opening sets)
      - Row distribution of opening shots
    """
    fingerprints = {}

    for opp_id, opp_data in memory.items():
        seqs = opp_data.get("firing_sequences", [])
        if len(seqs) < 2:
            fingerprints[opp_id] = {"consistency": 0, "n_games": len(seqs),
                                     "row_dist": None, "top_rows": "n/a"}
            continue

        # Consistency: Jaccard of first-N shots between consecutive games
        similarities = []
        for i in range(1, len(seqs)):
            w = min(window, len(seqs[i - 1]), len(seqs[i]))
            if w < 3:
                continue
            prev = set(tuple(s) for s in seqs[i - 1][:w])
            curr = set(tuple(s) for s in seqs[i][:w])
            if prev or curr:
                similarities.append(len(prev & curr) / len(prev | curr))

        consistency = sum(similarities) / len(similarities) if similarities else 0

        # Row distribution of opening shots
        row_counts = [0] * board_size
        total = 0
        for seq in seqs:
            for shot in seq[:window]:
                r = int(shot[0])
                if 0 <= r < board_size:
                    row_counts[r] += 1
                    total += 1

        if total > 0:
            row_pcts = [round(c / total * 100, 1) for c in row_counts]
        else:
            row_pcts = [0] * board_size

        # Which rows get hit most in opening
        top_rows = sorted(range(board_size), key=lambda r: row_counts[r], reverse=True)[:3]

        fingerprints[opp_id] = {
            "consistency": round(consistency, 3),
            "n_games": len(seqs),
            "row_dist": row_pcts,
            "top_rows": ",".join(str(r) for r in top_rows),
            "top3_pct": round(sum(row_counts[r] for r in range(3)) / max(total, 1) * 100, 1),
            "bot3_pct": round(sum(row_counts[r] for r in range(7, 10)) / max(total, 1) * 100, 1),
        }

    return fingerprints


# ── Trust extraction ─────────────────────────────────────────────────────────

def extract_trust(trust_info: str) -> float | None:
    """Parse trust=X.XX from strategy_reason string."""
    if not trust_info:
        return None
    import re
    m = re.search(r'trust=([0-9.]+)', trust_info)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None


# ── Main analytics ───────────────────────────────────────────────────────────

def run_analytics(recent_n: int | None = None):
    if not BATTLE_DIR.exists():
        print(f"No battle directory at {BATTLE_DIR}")
        sys.exit(1)

    # Load battle files
    battle_files = sorted(BATTLE_DIR.glob("*.jsonl"))
    if recent_n:
        battle_files = battle_files[-recent_n:]

    print(f"Analyzing {len(battle_files)} battle files...\n")

    all_games = []
    for bf in battle_files:
        all_games.extend(parse_battle_file(bf))

    if not all_games:
        print("No game data found.")
        return

    memory = load_memory()
    fingerprints = opening_fingerprint(memory)

    # ── 1. Overall summary ───────────────────────────────────────────────
    wins = sum(1 for g in all_games if g["won"])
    losses = sum(1 for g in all_games if not g["won"])
    total = len(all_games)

    print("=" * 80)
    print(f"  AEGIS ANALYTICS — {total} games ({len(battle_files)} attempts)")
    print("=" * 80)
    print(f"  Overall: {wins}W / {losses}L ({wins/total*100:.1f}% WR)")

    win_moves = [g["total_moves"] for g in all_games if g["won"]]
    loss_moves = [g["total_moves"] for g in all_games if not g["won"]]
    if win_moves:
        print(f"  Avg moves — Wins: {sum(win_moves)/len(win_moves):.0f}  Losses: {sum(loss_moves)/len(loss_moves):.0f}")
    print()

    # ── 2. Loss taxonomy ────────────────────────────────────────────────
    loss_games = [g for g in all_games if not g["won"]]
    if loss_games:
        categories = defaultdict(list)
        for g in loss_games:
            cat = classify_loss(g)
            categories[cat].append(g)

        print("─" * 80)
        print("  LOSS TAXONOMY")
        print("─" * 80)
        for cat in ["close_loss", "standard_loss", "defensive_collapse", "targeting_failure"]:
            games = categories.get(cat, [])
            if not games:
                continue
            pct = len(games) / len(loss_games) * 100
            avg_moves = sum(g["total_moves"] for g in games) / len(games)
            avg_acc = sum(g["our_accuracy"] for g in games) / len(games)
            avg_hits = sum(g["our_hits"] + g["our_sinks"] for g in games) / len(games)

            label = {
                "close_loss": "CLOSE LOSS (targeting ok, outpaced)",
                "standard_loss": "STANDARD LOSS (moderate gap)",
                "defensive_collapse": "DEFENSIVE COLLAPSE (found fast)",
                "targeting_failure": "TARGETING FAILURE (can't find ships)",
            }[cat]

            print(f"\n  {label}")
            print(f"    Count: {len(games)} ({pct:.0f}% of losses)")
            print(f"    Avg moves: {avg_moves:.0f}  |  Avg accuracy: {avg_acc:.1%}  |  Avg our hits: {avg_hits:.0f}/17")

            # Show which opponents fall in this bucket
            opp_counts = defaultdict(int)
            for g in games:
                opp_counts[g["opponent"]] += 1
            top_opps = sorted(opp_counts.items(), key=lambda x: -x[1])[:5]
            print(f"    Opponents: {', '.join(f'{o}({n})' for o, n in top_opps)}")
        print()

    # ── 3. Per-opponent table ────────────────────────────────────────────
    opp_stats = defaultdict(lambda: {
        "wins": 0, "losses": 0, "games": 0,
        "total_moves_w": [], "total_moves_l": [],
        "our_hits_l": [], "ships_lost": [], "hits_recv": [],
        "accuracy_l": [], "trust_vals": [],
        "loss_cats": defaultdict(int),
    })

    for g in all_games:
        opp = g["opponent"]
        s = opp_stats[opp]
        s["games"] += 1
        if g["won"]:
            s["wins"] += 1
            s["total_moves_w"].append(g["total_moves"])
        else:
            s["losses"] += 1
            s["total_moves_l"].append(g["total_moves"])
            s["our_hits_l"].append(g["our_hits"] + g["our_sinks"])
            s["accuracy_l"].append(g["our_accuracy"])
            s["loss_cats"][classify_loss(g)] += 1
        s["ships_lost"].append(g["ships_lost"])
        s["hits_recv"].append(g["hits_received"])
        t = extract_trust(g.get("trust_info", ""))
        if t is not None:
            s["trust_vals"].append(t)

    print("─" * 80)
    print("  PER-OPPONENT ANALYTICS")
    print("─" * 80)
    print()
    hdr = f"{'Opponent':<28} {'WR':>5} {'AvgMv':>5} {'OurHit':>6} {'HitRcv':>6} {'ShpLst':>6} {'Acc':>5} {'Trust':>5} {'LossCat':>20} {'Open':>5}"
    print(f"  {hdr}")
    print(f"  {'─'*len(hdr)}")

    # Sort by win rate descending, then by our_hits descending (close losses first)
    sorted_opps = sorted(opp_stats.items(),
                         key=lambda x: (-x[1]["wins"]/max(x[1]["games"],1),
                                        -sum(x[1]["our_hits_l"])/max(len(x[1]["our_hits_l"]),1)))

    for opp, s in sorted_opps:
        wr = f"{s['wins']}/{s['games']}"
        avg_mv_l = f"{sum(s['total_moves_l'])/len(s['total_moves_l']):.0f}" if s["total_moves_l"] else "—"
        avg_hit_l = f"{sum(s['our_hits_l'])/len(s['our_hits_l']):.0f}" if s["our_hits_l"] else "—"
        avg_recv = f"{sum(s['hits_recv'])/len(s['hits_recv']):.0f}" if s["hits_recv"] else "—"
        avg_lost = f"{sum(s['ships_lost'])/len(s['ships_lost']):.1f}" if s["ships_lost"] else "—"
        avg_acc = f"{sum(s['accuracy_l'])/len(s['accuracy_l']):.0%}" if s["accuracy_l"] else "—"
        trust = f"{sum(s['trust_vals'])/len(s['trust_vals']):.2f}" if s["trust_vals"] else "—"

        # Dominant loss category
        if s["loss_cats"]:
            dom_cat = max(s["loss_cats"].items(), key=lambda x: x[1])
            loss_cat = f"{dom_cat[0][:12]}({dom_cat[1]})"
        else:
            loss_cat = "—"

        fp = fingerprints.get(opp, {})
        opencon = f"{fp.get('consistency', 0):.2f}" if fp else "—"

        print(f"  {opp:<28} {wr:>5} {avg_mv_l:>5} {avg_hit_l:>6} {avg_recv:>6} {avg_lost:>6} {avg_acc:>5} {trust:>5} {loss_cat:>20} {opencon:>5}")

    print()

    # ── 4. Opening-shot fingerprints ─────────────────────────────────────
    print("─" * 80)
    print("  OPENING-SHOT FINGERPRINTS (first 10 shots per game)")
    print("─" * 80)
    print()
    print(f"  {'Opponent':<28} {'Cons':>5} {'Games':>5} {'TopRows':>8} {'Top3%':>6} {'Bot3%':>6} {'Row distribution (0→9)'}")
    print(f"  {'─'*95}")

    for opp in sorted(fingerprints, key=lambda o: -fingerprints[o]["consistency"]):
        fp = fingerprints[opp]
        cons = f"{fp['consistency']:.2f}"
        ng = str(fp["n_games"])
        tr = fp["top_rows"]
        t3 = f"{fp.get('top3_pct', 0):.0f}%"
        b3 = f"{fp.get('bot3_pct', 0):.0f}%"
        rd = fp.get("row_dist")
        rd_str = " ".join(f"{v:4.0f}" for v in rd) if rd else "—"
        print(f"  {opp:<28} {cons:>5} {ng:>5} {tr:>8} {t3:>6} {b3:>6}  [{rd_str}]")

    print()

    # ── 5. Exploitation value estimate ───────────────────────────────────
    print("─" * 80)
    print("  EXPLOITATION VALUE (who to invest in)")
    print("─" * 80)
    print()
    print(f"  {'Opponent':<28} {'WR':>5} {'CloseLoss':>10} {'AvgMargin':>10} {'OpenCons':>9} {'Priority'}")
    print(f"  {'─'*80}")

    for opp, s in sorted_opps:
        wr_pct = s["wins"] / max(s["games"], 1)
        close = s["loss_cats"].get("close_loss", 0)
        total_losses = s["losses"]
        margin = (17 - sum(s["our_hits_l"]) / len(s["our_hits_l"])) if s["our_hits_l"] else 17
        fp = fingerprints.get(opp, {})
        cons = fp.get("consistency", 0)

        # Priority scoring:
        # High priority = close losses + consistent opening (exploitable)
        # Low priority = already winning or totally outclassed
        if wr_pct >= 0.8:
            priority = "SOLVED"
        elif close >= 2 or margin < 5:
            priority = "HIGH" if cons > 0.3 else "MEDIUM"
        elif cons > 0.5:
            priority = "MEDIUM"
        elif margin > 12:
            priority = "LOW (outclassed)"
        else:
            priority = "LOW"

        close_str = f"{close}/{total_losses}" if total_losses else "—"
        margin_str = f"{margin:.1f} cells"

        print(f"  {opp:<28} {s['wins']}/{s['games']:>2} {close_str:>10} {margin_str:>10} {cons:>9.2f}  {priority}")

    print()

    # ── 6. Per-attempt evolution: does trust help? ─────────────────────
    print("─" * 80)
    print("  PER-ATTEMPT EVOLUTION — Does accumulated memory help?")
    print("─" * 80)
    print()

    # Group games by battle file (= attempt)
    by_file = defaultdict(list)
    for g in all_games:
        by_file[g["file"]].append(g)

    # For each attempt, extract trust from strategy_reason
    print(f"  {'File (attempt)':<42} {'W/L':>5} {'AvgTrust':>9} {'MaxGames':>9} {'AvgMoves':>9} {'AvgHits':>8}")
    print(f"  {'─'*90}")

    attempt_rows = []
    for fname in sorted(by_file.keys()):
        games = by_file[fname]
        w = sum(1 for g in games if g["won"])
        l = sum(1 for g in games if not g["won"])
        avg_mv = sum(g["total_moves"] for g in games) / len(games)

        # Extract trust and games_played from strategy_reason
        trusts = []
        max_gp = 0
        for g in games:
            t = extract_trust(g.get("trust_info", ""))
            if t is not None:
                trusts.append(t)
            sr = g.get("trust_info", "")
            for part in sr.split():
                if part.startswith("games="):
                    try:
                        gp = int(part.split("=")[1].rstrip(")"))
                        max_gp = max(max_gp, gp)
                    except ValueError:
                        pass

        avg_trust = sum(trusts) / len(trusts) if trusts else 0
        avg_hits_l = sum(g["our_hits"] + g["our_sinks"] for g in games if not g["won"])
        n_losses = sum(1 for g in games if not g["won"])
        avg_h = avg_hits_l / n_losses if n_losses else 0

        print(f"  {fname:<42} {w:>2}/{l:<2} {avg_trust:>9.2f} {max_gp:>9} {avg_mv:>9.0f} {avg_h:>8.0f}")
        attempt_rows.append({"file": fname, "wins": w, "avg_trust": avg_trust, "max_gp": max_gp})

    # Correlation: trust vs wins
    if attempt_rows:
        hi_trust = [r for r in attempt_rows if r["avg_trust"] > 0.1]
        lo_trust = [r for r in attempt_rows if r["avg_trust"] <= 0.1]
        if hi_trust and lo_trust:
            avg_w_hi = sum(r["wins"] for r in hi_trust) / len(hi_trust)
            avg_w_lo = sum(r["wins"] for r in lo_trust) / len(lo_trust)
            print(f"\n  Trust correlation: High-trust attempts avg {avg_w_hi:.1f} wins, low-trust avg {avg_w_lo:.1f} wins")
    print()

    # ── 7. THE FINDING: trust=0 in recent runs ─────────────────────────
    recent_files = sorted(by_file.keys())[-4:]
    recent_games_counts = set()
    for fname in recent_files:
        for g in by_file[fname]:
            sr = g.get("trust_info", "")
            for part in sr.split():
                if part.startswith("games="):
                    try:
                        recent_games_counts.add(int(part.split("=")[1].rstrip(")")))
                    except ValueError:
                        pass
    if recent_games_counts and max(recent_games_counts) <= 2:
        print("─" * 80)
        print("  !! CRITICAL FINDING: MEMORY NOT PERSISTING BETWEEN ATTEMPTS !!")
        print("─" * 80)
        print(f"  Last 4 runs show games_played values: {sorted(recent_games_counts)}")
        print("  Agent is playing BLIND — no trust, no heatmaps, no exploits.")
        print("  Memory accumulates within multi-round runs but resets on new deployments.")
        print("  Fix: ensure --memory points to a persistent path, or increase --rounds.")
        print()

    # ── 8. Critical insight: move economy ────────────────────────────────
    print("─" * 80)
    print("  MOVE ECONOMY — The 20-move gap")
    print("─" * 80)
    print()
    if win_moves and loss_moves:
        avg_w = sum(win_moves) / len(win_moves)
        avg_l = sum(loss_moves) / len(loss_moves)
        gap = avg_l - avg_w
        print(f"  Avg win:  {avg_w:.0f} moves")
        print(f"  Avg loss: {avg_l:.0f} moves")
        print(f"  Gap:      {gap:.0f} moves — each extra move = 1 more opponent shot on us")
        print()

        # Move distribution for losses
        buckets = {"<40": 0, "40-49": 0, "50-59": 0, "60-69": 0, "70+": 0}
        for m in loss_moves:
            if m < 40:
                buckets["<40"] += 1
            elif m < 50:
                buckets["40-49"] += 1
            elif m < 60:
                buckets["50-59"] += 1
            elif m < 70:
                buckets["60-69"] += 1
            else:
                buckets["70+"] += 1
        print(f"  Loss move distribution:")
        for b, c in buckets.items():
            bar = "█" * c
            print(f"    {b:>5}: {c:>3} {bar}")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AEGIS Analytics")
    parser.add_argument("--recent", type=int, default=None,
                        help="Only analyze last N battle files")
    args = parser.parse_args()

    os.chdir(Path(__file__).resolve().parent.parent)
    run_analytics(args.recent)
