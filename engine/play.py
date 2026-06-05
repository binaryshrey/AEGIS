"""
Prod entry point — play against the real competition server.

Usage:
  python -m engine.play              # prod (requires auth)
  python -m engine.play --connect    # first run: approve agent
  python -m engine.play --mock       # local dev with mock server
  python -m engine.play --rounds 5   # multiple attempts (self-improving)

Features:
  - Separate prod data dir (data/prod/) so mock and prod don't mix
  - Auto-retry on disqualification (up to 3 attempts per round)
  - Score tracking across attempts (data/prod/scores.jsonl)
  - JSONL logging compatible with dashboard SSE streaming
"""
import argparse
import json
import os
import sys
import time
import uuid

PROD_SERVER = "https://intern-battleship-game-server.vercel.app"
PROD_COMPETITION = "295cccc9137b5335cc581d67d655d6fa3b41dac6610dad0e7ed201625523ad8c"
MOCK_SERVER = "http://localhost:5001"

PROD_DATA_DIR = "data/prod"
MOCK_DATA_DIR = "data"
SCORES_FILE = "scores.jsonl"


def _ensure_prod_data_dir():
    """Create prod data directory if it doesn't exist."""
    os.makedirs(PROD_DATA_DIR, exist_ok=True)
    # Initialize empty files if they don't exist
    for f in ["memory.json", "bandit.json", "lessons.json"]:
        path = os.path.join(PROD_DATA_DIR, f)
        if not os.path.exists(path):
            with open(path, "w") as fh:
                if f.endswith(".json"):
                    fh.write("{}" if f != "lessons.json" else "[]")


def _record_score(score: int | None, wins: int, losses: int,
                  attempt_num: int, data_dir: str):
    """Append attempt result to scores.jsonl for tracking improvement."""
    path = os.path.join(data_dir, SCORES_FILE)
    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "attempt": attempt_num,
        "final_score": score,
        "wins": wins,
        "losses": losses,
        "total_games": wins + losses,
        "win_rate": round(wins / (wins + losses), 3) if (wins + losses) > 0 else 0,
    }
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"\n  Score recorded: {json.dumps(entry)}")


def _print_score_history(data_dir: str):
    """Print past scores for quick comparison."""
    path = os.path.join(data_dir, SCORES_FILE)
    if not os.path.exists(path):
        return
    lines = open(path).read().strip().split("\n")
    if not lines or not lines[0]:
        return
    print("\n  === Score History ===")
    print(f"  {'#':<4} {'Score':<8} {'W/L':<8} {'Win%':<8} {'Time'}")
    print(f"  {'─'*4} {'─'*8} {'─'*8} {'─'*8} {'─'*20}")
    for line in lines:
        try:
            e = json.loads(line)
            score = e.get("final_score", "?")
            wl = f"{e['wins']}/{e['losses']}"
            wr = f"{e['win_rate']*100:.0f}%"
            print(f"  {e['attempt']:<4} {str(score):<8} {wl:<8} {wr:<8} {e['timestamp']}")
        except Exception:
            pass
    print()


def _run_engine_subprocess(server: str, competition: str, auth_mode: str,
                           data_dir: str, log_path: str, battle_id: str) -> int:
    """
    Run engine.main as a fresh subprocess to avoid module-reload bugs.
    Returns the subprocess exit code.
    """
    import subprocess as sp

    # Resolve the project root (parent of engine/)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    cmd = [
        sys.executable, "-m", "engine.main",
        "--url", server,
        "--competition", competition,
        "--memory", os.path.join(data_dir, "memory.json"),
        "--lessons", os.path.join(data_dir, "lessons.json"),
        "--bandit", os.path.join(data_dir, "bandit.json"),
        "--log", log_path,
        "--rounds", "1",
        "--battle-id", battle_id,
    ]

    env = {**os.environ, "AEGIS_AUTH_MODE": auth_mode}
    result = sp.run(cmd, cwd=project_root, env=env)
    return result.returncode


def _run_with_retry(server: str, competition: str, auth_mode: str,
                    data_dir: str, args, attempt_num: int,
                    max_retries: int = 3) -> tuple[int, int, int | None]:
    """
    Run one attempt with auto-retry on disqualification.
    Returns (wins, losses, server_score).
    """
    battle_id = args.battle_id or str(uuid.uuid4())
    log_path = os.path.join(data_dir, "battles", f"{battle_id}.jsonl")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    for retry in range(max_retries):
        if retry > 0:
            print(f"\n  Retry {retry}/{max_retries-1} (previous attempt was disqualified)")
            battle_id = str(uuid.uuid4())
            log_path = os.path.join(data_dir, "battles", f"{battle_id}.jsonl")

        _run_engine_subprocess(server, competition, auth_mode, data_dir,
                               log_path, battle_id)

        # Check if the attempt completed successfully by reading the log
        if os.path.exists(log_path):
            last_line = ""
            with open(log_path) as f:
                for line in f:
                    if line.strip():
                        last_line = line.strip()
            if last_line:
                try:
                    event = json.loads(last_line)
                    if event.get("event") in ("run_ended", "attempt_ended"):
                        return _extract_results(log_path)
                except Exception:
                    pass

        print(f"  Attempt may have been disqualified. Retrying...")

    print(f"  All {max_retries} retries exhausted.")
    return 0, 0, None


def _extract_results(log_path: str) -> tuple[int, int, int | None]:
    """Extract wins, losses, and score from a completed JSONL log."""
    wins = 0
    losses = 0
    score = None
    with open(log_path) as f:
        for line in f:
            try:
                event = json.loads(line.strip())
                if event.get("event") == "attempt_ended":
                    data = event.get("data", {})
                    wins = data.get("wins", 0)
                    losses = data.get("losses", 0)
                    if data.get("server_score") is not None:
                        score = data["server_score"]
            except Exception:
                pass
    return wins, losses, score


def main():
    parser = argparse.ArgumentParser(description="AEGIS Battleships Agent")
    parser.add_argument("--connect", action="store_true",
                        help="First run: approve agent via device flow")
    parser.add_argument("--mock", action="store_true",
                        help="Use mock server instead of prod")
    parser.add_argument("--rounds", type=int, default=1,
                        help="Number of attempts to play (self-improving)")
    parser.add_argument("--battle-id", default=None)
    parser.add_argument("--no-retry", action="store_true",
                        help="Disable auto-retry on disqualification")
    parser.add_argument("--history", action="store_true",
                        help="Print score history and exit")
    args = parser.parse_args()

    # ── Auth: connect (first run only) ─────────────────────────────────────
    if args.connect:
        from engine.auth import connect
        connect(PROD_SERVER)
        print("\n  Agent approved. Now run without --connect to play.")
        return

    # ── Determine mode ─────────────────────────────────────────────────────
    if args.mock:
        data_dir = MOCK_DATA_DIR
    else:
        data_dir = PROD_DATA_DIR
        _ensure_prod_data_dir()

    # ── Score history ──────────────────────────────────────────────────────
    if args.history:
        _print_score_history(data_dir)
        return

    if args.mock:
        server = MOCK_SERVER
        competition = "mock-competition"
        auth_mode = "mock"
    else:
        server = PROD_SERVER
        competition = PROD_COMPETITION
        auth_mode = "prod"

        from engine.auth import get_agent_id
        if not get_agent_id():
            print("  No agent ID found. Run with --connect first:")
            print("    python -m engine.play --connect")
            sys.exit(1)

    # ── Play rounds ────────────────────────────────────────────────────────
    print(f"\n  === AEGIS Agent ===")
    print(f"  Mode:        {'MOCK' if args.mock else 'PROD'}")
    print(f"  Server:      {server}")
    print(f"  Data dir:    {data_dir}")
    print(f"  Rounds:      {args.rounds}")
    _print_score_history(data_dir)

    for round_num in range(1, args.rounds + 1):
        print(f"\n  ═══ Attempt {round_num}/{args.rounds} ═══")

        if args.no_retry:
            # Direct run without retry wrapper
            battle_id = args.battle_id or str(uuid.uuid4())
            log_path = os.path.join(data_dir, "battles", f"{battle_id}.jsonl")
            os.makedirs(os.path.dirname(log_path), exist_ok=True)

            _run_engine_subprocess(server, competition, auth_mode, data_dir,
                                   log_path, battle_id)
            wins, losses, score = _extract_results(log_path)
        else:
            wins, losses, score = _run_with_retry(
                server, competition, auth_mode, data_dir, args, round_num
            )

        _record_score(score, wins, losses, round_num, data_dir)

    # Final summary
    print("\n  ═══ Final Score History ═══")
    _print_score_history(data_dir)


if __name__ == "__main__":
    main()
