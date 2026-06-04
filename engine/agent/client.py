"""
HTTP client for the StarSling Battleship API.

Auth: Device Authorization Grant — each request requires a freshly minted
single-use JWT (one-time `jti` for replay protection).
Mock: _mint_token() returns a fake token. Swap in real @auth/agent-cli call
      when live by replacing _mint_token() only.
"""
import uuid
import requests


# ── Auth ───────────────────────────────────────────────────────────────────────

def _mint_token() -> str:
    """
    Mock single-use JWT. Replace with real @auth/agent-cli invocation when live.
    Real call: subprocess / SDK call that returns a fresh signed JWT per request.
    """
    return f"mock-jwt-{uuid.uuid4()}"


# ── Client ─────────────────────────────────────────────────────────────────────

class Client:
    def __init__(self,
                 base_url:       str = "https://aegis-n8at.onrender.com",
                 competition_id: str = "mock-competition"):
        self.base           = base_url.rstrip("/")
        self.competition_id = competition_id
        self.session        = requests.Session()

    def _headers(self) -> dict:
        """Mint a fresh single-use token for every request."""
        return {"Authorization": f"Bearer {_mint_token()}"}

    def _url(self, path: str) -> str:
        return f"{self.base}{path}"

    # ── Competition ───────────────────────────────────────────────────────────

    def get_rules(self) -> dict:
        """Fetch board rules, opponent roster, scoring constants, turn timeout."""
        r = self.session.get(
            self._url(f"/competitions/{self.competition_id}/rules"),
            headers=self._headers(),
        )
        r.raise_for_status()
        return r.json()

    # ── Attempt lifecycle ─────────────────────────────────────────────────────

    def start_attempt(self) -> dict:
        """
        Start a new Attempt against all 15 opponents.
        Returns initial game state with nextRequiredMove=PLACE_SHIPS.
        Raises 409 if an active Attempt already exists.
        """
        r = self.session.post(
            self._url(f"/competitions/{self.competition_id}/attempts"),
            headers=self._headers(),
        )
        r.raise_for_status()
        return r.json()

    def get_current(self) -> dict:
        """Read the active Attempt's current game state."""
        r = self.session.get(
            self._url(f"/competitions/{self.competition_id}/attempts/current"),
            headers=self._headers(),
        )
        r.raise_for_status()
        return r.json()

    def place_ships(self, placements: list[dict], http_timeout: float = 9.5) -> dict:
        """
        Submit fleet placement for the current game.
        placements: list of {shipClass, orientation, startRow, startCol}
        """
        r = self.session.post(
            self._url(f"/competitions/{self.competition_id}/attempts/current/placements"),
            json={"placements": placements},
            headers=self._headers(),
            timeout=http_timeout,
        )
        r.raise_for_status()
        return r.json()

    def fire_shot(self, row: int, col: int, http_timeout: float = 9.5) -> dict:
        """
        Fire a single shot at (row, col).
        Returns responseType: MOVE_REQUIRED | GAME_COMPLETED |
                              ATTEMPT_COMPLETED | ATTEMPT_DISQUALIFIED
        Note: ATTEMPT_DISQUALIFIED returns HTTP 200, not 4xx.
        """
        r = self.session.post(
            self._url(f"/competitions/{self.competition_id}/attempts/current/shots"),
            json={"row": int(row), "col": int(col)},
            headers=self._headers(),
            timeout=http_timeout,
        )
        r.raise_for_status()
        return r.json()

    def abandon(self) -> dict:
        """Voluntarily disqualify the active Attempt."""
        r = self.session.post(
            self._url(f"/competitions/{self.competition_id}/attempts/current/abandon"),
            headers=self._headers(),
        )
        r.raise_for_status()
        return r.json()

    def leaderboard(self) -> list:
        try:
            r = self.session.get(
                self._url(f"/competitions/{self.competition_id}/leaderboard"),
                headers=self._headers(),
            )
            r.raise_for_status()
            return r.json()
        except Exception:
            return []
