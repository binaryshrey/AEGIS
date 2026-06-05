"""
HTTP client for the Battleship API.

Auth modes:
  - mock (default): fake UUID token for local dev
  - prod: shells out to @auth/agent-cli for fresh single-use JWTs

Toggle via Client(auth_mode="prod") or AEGIS_AUTH_MODE=prod env var.
"""
import os
import time
import uuid
import requests


# ── Auth ───────────────────────────────────────────────────────────────────────

def _mint_mock_token() -> str:
    """Mock single-use JWT for local dev."""
    return f"mock-jwt-{uuid.uuid4()}"


def _mint_prod_token() -> str:
    """Shell out to @auth/agent-cli for a real single-use JWT."""
    from engine.auth import sign_jwt
    return sign_jwt()


# ── Validation ─────────────────────────────────────────────────────────────────

_SHIP_SIZES = {
    "CARRIER": 5, "BATTLESHIP": 4, "CRUISER": 3,
    "SUBMARINE": 3, "DESTROYER": 2,
}


def _validate_fleet(placements: list[dict], board_size: int = 10) -> None:
    """
    Validate fleet placement locally before sending.
    Raises ValueError on any illegal layout to prevent instant DQ.
    """
    required = {"CARRIER", "BATTLESHIP", "CRUISER", "SUBMARINE", "DESTROYER"}
    seen_classes = set()
    occupied = set()

    for p in placements:
        cls = p["shipClass"]
        if cls not in required:
            raise ValueError(f"Unknown ship class: {cls}")
        if cls in seen_classes:
            raise ValueError(f"Duplicate ship class: {cls}")
        seen_classes.add(cls)

        length = _SHIP_SIZES[cls]
        orient = p["orientation"]
        r, c = int(p["startRow"]), int(p["startCol"])

        if orient == "HORIZONTAL":
            if c + length > board_size:
                raise ValueError(f"{cls} at ({r},{c}) H extends past board")
            cells = {(r, c + i) for i in range(length)}
        elif orient == "VERTICAL":
            if r + length > board_size:
                raise ValueError(f"{cls} at ({r},{c}) V extends past board")
            cells = {(r + i, c) for i in range(length)}
        else:
            raise ValueError(f"Invalid orientation: {orient}")

        if r < 0 or c < 0 or r >= board_size or c >= board_size:
            raise ValueError(f"{cls} start ({r},{c}) out of bounds")

        overlap = cells & occupied
        if overlap:
            raise ValueError(f"{cls} overlaps at {overlap}")
        occupied |= cells

    missing = required - seen_classes
    if missing:
        raise ValueError(f"Missing ship classes: {missing}")


def _validate_shot(row: int, col: int, board_size: int = 10,
                   prior_shots: list[dict] | None = None) -> None:
    """
    Validate shot locally before sending.
    Raises ValueError on illegal shot to prevent instant DQ.
    """
    if row < 0 or row >= board_size or col < 0 or col >= board_size:
        raise ValueError(f"Shot ({row},{col}) out of bounds [0,{board_size})")

    if prior_shots:
        for s in prior_shots:
            if int(s["row"]) == row and int(s["col"]) == col:
                raise ValueError(f"Duplicate shot at ({row},{col})")


# ── Retry helper ──────────────────────────────────────────────────────────────

_TRANSIENT_CODES = {429, 500, 502, 503, 504}
_MAX_RETRIES = 2
_RETRY_BACKOFF = 0.5  # seconds


def _request_with_retry(session: requests.Session, method: str, url: str,
                        headers_factory=None,
                        retries: int = _MAX_RETRIES, **kwargs) -> requests.Response:
    """
    Execute an HTTP request with retry on transient errors (429, 5xx).
    Does NOT retry on 4xx client errors (except 429) — those are our fault.

    headers_factory: callable that returns fresh headers (with new JWT)
                     on each retry. Required because JWTs are single-use
                     (each jti can only be used once).
    """
    last_err = None
    for attempt in range(retries + 1):
        # Mint fresh headers (fresh JWT) on every attempt
        if headers_factory:
            kwargs["headers"] = headers_factory()
        try:
            r = session.request(method, url, **kwargs)
            if r.status_code not in _TRANSIENT_CODES or attempt == retries:
                return r
            # Transient error — wait and retry
            time.sleep(_RETRY_BACKOFF * (attempt + 1))
            last_err = requests.HTTPError(response=r)
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            last_err = e
            if attempt == retries:
                raise
            time.sleep(_RETRY_BACKOFF * (attempt + 1))
    raise last_err


# ── Client ─────────────────────────────────────────────────────────────────────

# Default timeout for non-move requests (rules, start, get_current, abandon).
# Move requests (place_ships, fire_shot) use the caller-specified http_timeout.
_DEFAULT_TIMEOUT = 15.0


class Client:
    def __init__(self,
                 base_url: str = "https://aegis-n8at.onrender.com",
                 competition_id: str = "mock-competition",
                 auth_mode: str | None = None):
        self.base = base_url.rstrip("/")
        self.competition_id = competition_id
        self.session = requests.Session()

        # Determine auth mode: explicit arg > env var > mock
        mode = auth_mode or os.environ.get("AEGIS_AUTH_MODE", "mock")
        self._mint_token = _mint_prod_token if mode == "prod" else _mint_mock_token

        # Track shots for local validation (reset per game)
        self._current_shots: list[dict] = []
        self._board_size: int = 10

    def _headers(self, with_json: bool = False) -> dict:
        """Mint a fresh single-use token for every request."""
        h = {"Authorization": f"Bearer {self._mint_token()}"}
        if with_json:
            h["Content-Type"] = "application/json"
        return h

    def _url(self, path: str) -> str:
        return f"{self.base}{path}"

    def reset_game_state(self) -> None:
        """Reset per-game tracking (call on new game)."""
        self._current_shots = []

    # ── Competition ───────────────────────────────────────────────────────────

    def get_rules(self) -> dict:
        r = _request_with_retry(
            self.session, "GET",
            self._url(f"/competitions/{self.competition_id}/rules"),
            headers_factory=self._headers,
            timeout=_DEFAULT_TIMEOUT,
        )
        r.raise_for_status()
        rules = r.json()
        self._board_size = rules.get("boardRules", {}).get("gridRows", 10)
        return rules

    # ── Attempt lifecycle ─────────────────────────────────────────────────────

    def start_attempt(self) -> dict:
        """
        Start a new Attempt. NO body — do NOT set Content-Type.
        Returns MOVE_REQUIRED with nextRequiredMove=PLACE_SHIPS.
        """
        self._current_shots = []
        r = _request_with_retry(
            self.session, "POST",
            self._url(f"/competitions/{self.competition_id}/attempts"),
            headers_factory=self._headers,  # no Content-Type
            timeout=_DEFAULT_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()

    def get_current(self) -> dict:
        r = _request_with_retry(
            self.session, "GET",
            self._url(f"/competitions/{self.competition_id}/attempts/current"),
            headers_factory=self._headers,
            timeout=_DEFAULT_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()

    def place_ships(self, placements: list[dict], http_timeout: float = 9.5) -> dict:
        # Validate locally first
        _validate_fleet(placements, self._board_size)
        self._current_shots = []  # new game

        r = _request_with_retry(
            self.session, "POST",
            self._url(f"/competitions/{self.competition_id}/attempts/current/placements"),
            json={"placements": placements},
            headers_factory=self._headers,
            timeout=http_timeout,
        )
        r.raise_for_status()
        return r.json()

    def fire_shot(self, row: int, col: int, http_timeout: float = 9.5) -> dict:
        row, col = int(row), int(col)

        # Validate locally first
        _validate_shot(row, col, self._board_size, self._current_shots)

        r = self.session.post(
            self._url(f"/competitions/{self.competition_id}/attempts/current/shots"),
            json={"row": row, "col": col},
            headers=self._headers(),
            timeout=http_timeout,
        )
        r.raise_for_status()

        # Track for dedup validation
        self._current_shots.append({"row": row, "col": col})
        return r.json()

    def abandon(self) -> dict:
        """Abandon active Attempt. NO body — do NOT set Content-Type."""
        r = _request_with_retry(
            self.session, "POST",
            self._url(f"/competitions/{self.competition_id}/attempts/current/abandon"),
            headers_factory=self._headers,  # no Content-Type
            timeout=_DEFAULT_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()

    def leaderboard(self) -> list:
        try:
            r = _request_with_retry(
                self.session, "GET",
                self._url(f"/competitions/{self.competition_id}/leaderboard"),
                headers_factory=self._headers,
                timeout=_DEFAULT_TIMEOUT,
            )
            r.raise_for_status()
            data = r.json()
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("entries", data.get("leaderboard", []))
            return []
        except Exception:
            return []
