"""
Mock game server — FastAPI version.
Matches real StarSling challenge API shape exactly.

Response envelope structure mirrors real API (ADR 0009):
  MOVE_REQUIRED      -> { responseType, state: { ...game fields... } }
  GAME_COMPLETED     -> { responseType, gameOutcome, state, next: { responseType, state } }
  ATTEMPT_COMPLETED  -> { responseType, gameOutcome, state, result: {...} }
  ATTEMPT_DISQUALIFIED -> { responseType, reason, ranked, attemptId, context }

Run with:
  uvicorn backend.main:app --port 5001 --reload
"""
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.bots import BOTS, BOT_POOL, BOARD_SIZE, SHIP_CLASSES, SINK_BONUSES, pick_roster
from backend.game_engine import GameState

app = FastAPI(title="StarSling Mock Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

COMPETITION_ID = "mock-competition"
TURN_TIMEOUT   = 10

_attempts: dict[str, dict] = {}


# -- Request ID middleware -----------------------------------------------------

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    response = await call_next(request)
    response.headers["x-request-id"] = str(uuid.uuid4())
    return response


# -- Helpers -------------------------------------------------------------------

def _active_attempt() -> dict | None:
    for a in _attempts.values():
        if a["status"] == "active":
            return a
    return None


def _bot_info(bot) -> dict:
    return {
        "opponentId":    bot.id,
        "displayName":   bot.display_name,
        "opponentClass": bot.opponent_class,
        "baseScore":     bot.base_score,
    }


def _board_rules() -> dict:
    return {
        "gridRows":       BOARD_SIZE,
        "gridCols":       BOARD_SIZE,
        "shipClasses":    [{"class": c, "length": s} for c, s in SHIP_CLASSES],
        "allowAdjacency": True,
    }


def _scoring_constants() -> dict:
    return {
        "opponentBaseScoreOnWin":   15,
        "agentHitPoints":           1,
        "sinkBonusByClass":         dict(SINK_BONUSES),
        "perShipLossPenalty":       2,
        "classLossPenaltyByClass":  dict(SINK_BONUSES),
    }


def _game_state_fields(attempt: dict, bot) -> dict:
    game: GameState | None = attempt.get("game")
    snap = game.snapshot() if game else {}
    return {
        "competitionId":           COMPETITION_ID,
        "gameOrdinal":             attempt["game_idx"] + 1,
        "totalGames":              len(attempt.get("roster", BOTS)),
        "opponent":                _bot_info(bot),
        "nextRequiredMove":        "SUBMIT_SHOT" if attempt["ships_placed"] else "PLACE_SHIPS",
        "nextMoveDeadlineAt":      None,
        "board":                   _board_rules(),
        "yourFleet":               snap.get("yourFleet", []),
        "yourShots":               snap.get("yourShots", []),
        "incomingShots":           snap.get("incomingShots", []),
        "sunkOpponentShipClasses": snap.get("sunkOpponentShipClasses", []),
    }


def _move_required(attempt: dict, bot) -> dict:
    return {
        "responseType": "MOVE_REQUIRED",
        "state":        _game_state_fields(attempt, bot),
    }


def _attempt_result(attempt: dict) -> dict:
    total_score = sum(g["score"]        for g in attempt["completed_games"])
    wins        = sum(1 for g in attempt["completed_games"] if g["won"])
    losses      = len(attempt["completed_games"]) - wins
    hits        = sum(g["hits"]         for g in attempt["completed_games"])
    opp_sunk    = sum(g["oppShipsSunk"] for g in attempt["completed_games"])
    our_sunk    = sum(g["ourShipsSunk"] for g in attempt["completed_games"])
    return {
        "attemptId":         attempt["id"],
        "finalScore":        total_score,
        "wins":              wins,
        "losses":            losses,
        "hitDifferential":   hits - our_sunk,
        "opponentShipsSunk": opp_sunk,
        "agentShipsLost":    our_sunk,
        "isNewBest":         True,
        "completionMessage": f"Attempt complete — {wins}W / {losses}L  score: {total_score}",
    }


def _disqualified(attempt: dict, bot, last_move: str) -> dict:
    return {
        "responseType": "ATTEMPT_DISQUALIFIED",
        "reason":       "ILLEGAL_MOVE",
        "ranked":       False,
        "attemptId":    attempt["id"],
        "context":      {
            "gameOrdinal":      attempt["game_idx"] + 1,
            "lastRequiredMove": last_move,
            "opponentId":       bot.id,
        },
    }


def _check_competition(competition_id: str):
    if competition_id != COMPETITION_ID:
        return JSONResponse(
            status_code=404,
            content={"code": "COMPETITION_NOT_FOUND", "message": "Unknown competition"},
        )
    return None


def _no_active_attempt():
    return JSONResponse(
        status_code=404,
        content={"code": "NO_ACTIVE_ATTEMPT", "message": "No active attempt"},
    )


# -- Routes -------------------------------------------------------------------

@app.get("/competitions/{competition_id}/rules")
async def get_rules(competition_id: str):
    err = _check_competition(competition_id)
    if err:
        return err
    return {
        "competitionId":      COMPETITION_ID,
        "displayName":        "StarSling Intern Challenge (mock)",
        "boardRules":         _board_rules(),
        "opponentRoster":     [_bot_info(b) for b in BOT_POOL],
        "scoringConstants":   _scoring_constants(),
        "turnTimeoutSeconds": TURN_TIMEOUT,
        "completionMessage":  "Good luck!",
    }


@app.post("/competitions/{competition_id}/attempts")
async def start_attempt(competition_id: str):
    err = _check_competition(competition_id)
    if err:
        return err
    if _active_attempt():
        return JSONResponse(
            status_code=409,
            content={"code": "ACTIVE_ATTEMPT_EXISTS", "message": "Already have an active attempt"},
        )

    attempt_id = str(uuid.uuid4())[:8]
    roster = pick_roster()
    _attempts[attempt_id] = {
        "id":              attempt_id,
        "status":          "active",
        "game_idx":        0,
        "game":            None,
        "ships_placed":    False,
        "completed_games": [],
        "roster":          roster,
    }
    return _move_required(_attempts[attempt_id], roster[0])


@app.get("/competitions/{competition_id}/attempts/current")
async def get_current(competition_id: str):
    err = _check_competition(competition_id)
    if err:
        return err
    attempt = _active_attempt()
    if not attempt:
        return _no_active_attempt()
    return _move_required(attempt, attempt["roster"][attempt["game_idx"]])


@app.post("/competitions/{competition_id}/attempts/current/placements")
async def place_ships(competition_id: str, request: Request):
    err = _check_competition(competition_id)
    if err:
        return err
    attempt = _active_attempt()
    if not attempt:
        return _no_active_attempt()
    if attempt["ships_placed"]:
        return JSONResponse(
            status_code=409,
            content={"code": "SHIPS_ALREADY_PLACED", "message": "Fleet already placed"},
        )

    body = await request.json()
    placements = body.get("placements", [])
    bot = attempt["roster"][attempt["game_idx"]]

    if len(placements) != 5:
        return _disqualified(attempt, bot, "PLACE_SHIPS")

    attempt["game"]         = GameState(bot, placements)
    attempt["ships_placed"] = True
    return _move_required(attempt, bot)


@app.post("/competitions/{competition_id}/attempts/current/shots")
async def fire_shot(competition_id: str, request: Request):
    err = _check_competition(competition_id)
    if err:
        return err
    attempt = _active_attempt()
    if not attempt:
        return _no_active_attempt()
    bot = attempt["roster"][attempt["game_idx"]]

    if not attempt["ships_placed"]:
        return _disqualified(attempt, bot, "PLACE_SHIPS")

    body = await request.json()
    row  = body.get("row")
    col  = body.get("col")

    if row is None or col is None or not (0 <= row < BOARD_SIZE) or not (0 <= col < BOARD_SIZE):
        return _disqualified(attempt, bot, "SUBMIT_SHOT")

    game: GameState = attempt["game"]
    already_fired = {(s["row"], s["col"]) for s in game.player_shots}
    if (row, col) in already_fired:
        return _disqualified(attempt, bot, "SUBMIT_SHOT")

    game.player_fires(row, col)

    if game.status in ("won", "lost"):
        we_won     = game.status == "won"
        outcome    = "AGENT_WIN" if we_won else "OPPONENT_WIN"
        game.notify_game_end()
        game_score = game.game_score(bot, we_won)
        attempt["completed_games"].append(game_score)

        current_state = _game_state_fields(attempt, bot)
        next_game_idx = attempt["game_idx"] + 1

        roster = attempt["roster"]
        if next_game_idx >= len(roster):
            attempt["status"] = "completed"
            return {
                "responseType": "ATTEMPT_COMPLETED",
                "gameOutcome":  outcome,
                "state":        current_state,
                "result":       _attempt_result(attempt),
            }

        attempt["game_idx"]     = next_game_idx
        attempt["game"]         = None
        attempt["ships_placed"] = False
        next_bot = roster[next_game_idx]

        return {
            "responseType": "GAME_COMPLETED",
            "gameOutcome":  outcome,
            "state":        current_state,
            "next": {
                "responseType": "MOVE_REQUIRED",
                "state":        _game_state_fields(attempt, next_bot),
            },
        }

    return _move_required(attempt, bot)


@app.post("/competitions/{competition_id}/attempts/current/abandon")
async def abandon(competition_id: str):
    err = _check_competition(competition_id)
    if err:
        return err
    attempt = _active_attempt()
    if not attempt:
        return _no_active_attempt()
    attempt["status"] = "disqualified"
    return {
        "responseType": "ATTEMPT_DISQUALIFIED",
        "reason":       "ABANDONED",
        "ranked":       False,
        "attemptId":    attempt["id"],
        "context":      {},
    }


@app.get("/competitions/{competition_id}/leaderboard")
async def leaderboard(competition_id: str):
    err = _check_competition(competition_id)
    if err:
        return err
    completed = [a for a in _attempts.values() if a["status"] == "completed"]
    board = sorted(
        [{"attemptId": a["id"], "score": _attempt_result(a)["finalScore"]} for a in completed],
        key=lambda x: x["score"],
        reverse=True,
    )
    return board


@app.get("/health")
async def health():
    return {"status": "alive"}


# -- Dashboard API (reads from Supabase) ---------------------------------------

def _get_supabase():
    import os
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        return None
    from supabase import create_client
    return create_client(url, key)


@app.get("/api/runs")
async def get_runs(limit: int = 50):
    """Return recent runs for the dashboard."""
    sb = _get_supabase()
    if not sb:
        return {"error": "Supabase not configured", "data": []}
    result = sb.table("runs").select("*").order("created_at", desc=True).limit(limit).execute()
    return {"data": result.data}


@app.get("/api/runs/{run_id}/games")
async def get_run_games(run_id: int):
    """Return all games for a specific run."""
    sb = _get_supabase()
    if not sb:
        return {"error": "Supabase not configured", "data": []}
    result = sb.table("games").select("*").eq("run_id", run_id).execute()
    return {"data": result.data}


@app.get("/api/opponents")
async def get_opponents():
    """Return latest opponent states."""
    sb = _get_supabase()
    if not sb:
        return {"error": "Supabase not configured", "data": []}
    result = sb.table("opponents").select("*").order("opponent_id").execute()
    return {"data": result.data}


@app.get("/api/dashboard")
async def get_dashboard():
    """Aggregated dashboard data — single call for all cards."""
    sb = _get_supabase()
    if not sb:
        return {"error": "Supabase not configured"}

    # Latest run
    latest = sb.table("runs").select("*").order("created_at", desc=True).limit(1).execute()
    # Previous run (for deltas)
    prev = sb.table("runs").select("*").order("created_at", desc=True).limit(1).offset(1).execute()
    # All runs for leaderboard
    runs = sb.table("runs").select("*").order("total_score", desc=True).limit(10).execute()
    # Opponents
    opps = sb.table("opponents").select("*").order("opponent_id").execute()

    latest_run = latest.data[0] if latest.data else None
    prev_run = prev.data[0] if prev.data else None

    # Compute deltas
    deltas = {}
    if latest_run and prev_run:
        for key in ["total_score", "avg_moves", "ships_surviving", "hits_taken"]:
            lv = latest_run.get(key, 0) or 0
            pv = prev_run.get(key, 0) or 0
            deltas[key] = round(lv - pv, 2)

    opp_data = opps.data or []
    exploitable = sum(1 for o in opp_data if o.get("exploitable"))
    classifications = {}
    for o in opp_data:
        cls = o.get("classification") or "unknown"
        classifications[cls] = classifications.get(cls, 0) + 1

    return {
        "latest_run":       latest_run,
        "deltas":           deltas,
        "leaderboard":      runs.data,
        "opponents":        opp_data,
        "exploitable_count": exploitable,
        "classifications":  classifications,
    }


if __name__ == "__main__":
    import uvicorn
    print(f"\n  Mock StarSling server  ->  http://localhost:5001")
    print(f"  Competition ID         :  {COMPETITION_ID}\n")
    uvicorn.run(app, host="0.0.0.0", port=5001, log_level="warning")
