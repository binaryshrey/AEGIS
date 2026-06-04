"""
Game engine — manages state for a single Battleship game.
Uses row/col coordinates (0-indexed, 0–9).
Ship placement uses {shipClass, orientation, startRow, startCol} format.
yourFleet mirrors placement format + sunk flag (matches real API).
incomingShots includes outcome and sunkShipClass (matches real API).
"""
import random
from bots import BOARD_SIZE, SINK_BONUSES

SHIP_SIZES = {
    "CARRIER": 5, "BATTLESHIP": 4,
    "CRUISER": 3, "SUBMARINE": 3, "DESTROYER": 2,
}


class ShipState:
    def __init__(self, ship_class: str, cells: list[tuple]):
        self.ship_class = ship_class
        self.cells      = set(cells)
        self.remaining  = set(cells)

    @property
    def sunk(self) -> bool:
        return len(self.remaining) == 0

    def fire(self, cell: tuple) -> str | None:
        """Fire at cell. Returns 'HIT', 'SINK', or None (miss)."""
        if cell not in self.remaining:
            return None
        self.remaining.discard(cell)
        return "SINK" if self.sunk else "HIT"


def _expand_placements(placements: list[dict]) -> list[ShipState]:
    ships = []
    for p in placements:
        ship_class  = p["shipClass"]
        size        = SHIP_SIZES[ship_class]
        if p["orientation"] == "HORIZONTAL":
            cells = [(p["startRow"], p["startCol"] + i) for i in range(size)]
        else:
            cells = [(p["startRow"] + i, p["startCol"]) for i in range(size)]
        ships.append(ShipState(ship_class, cells))
    return ships


class GameState:
    def __init__(self, bot, player_placements: list[dict]):
        self.bot = bot
        self.turn = 0
        self.rng  = random.Random()
        bot.reset()

        # Store original placements so yourFleet mirrors them back (real API format)
        self._player_placements = player_placements

        # Bot fleet — from bot's own placement logic
        self.bot_fleet: list[ShipState] = [
            ShipState(ship_class, cells)
            for ship_class, cells in bot.get_ship_placement()
        ]

        # Player fleet — from submitted placements
        self.player_fleet: list[ShipState] = _expand_placements(player_placements)

        self.bot_shots_fired: set[tuple] = set()
        # yourShots: {row, col, outcome: MISS|HIT|SINK, sunkShipClass: str|null}
        self.player_shots:   list[dict] = []
        # incomingShots: {row, col, outcome: MISS|HIT|SINK, sunkShipClass: str|null}
        self.incoming_shots: list[dict] = []
        self.sunk_opponent_classes: list[str] = []

        self.status = "ongoing"  # ongoing | won | lost

    def player_fires(self, row: int, col: int) -> dict:
        """Player fires at (row, col). Resolves hit/miss + bot return shot."""
        cell = (row, col)

        # Resolve player shot against bot fleet
        outcome    = "MISS"
        sunk_class = None
        for ship in self.bot_fleet:
            result = ship.fire(cell)
            if result:
                outcome = result
                if result == "SINK":
                    sunk_class = ship.ship_class
                    self.sunk_opponent_classes.append(ship.ship_class)
                break

        self.player_shots.append({
            "row": row, "col": col,
            "outcome": outcome,
            "sunkShipClass": sunk_class,
        })

        # Check player win (no bot return shot if we just sank the last ship)
        if all(s.sunk for s in self.bot_fleet):
            self.status = "won"
            return self.snapshot()

        # Bot fires back — resolve against player fleet with outcome tracking
        bot_shot = self.bot.get_next_shot(self.turn, self.rng, self.bot_shots_fired)
        self.bot_shots_fired.add(bot_shot)

        bot_outcome    = "MISS"
        bot_sunk_class = None
        for ship in self.player_fleet:
            result = ship.fire(bot_shot)
            if result:
                bot_outcome = result
                if result == "SINK":
                    bot_sunk_class = ship.ship_class
                break

        # Notify bot of shot result (for ProbabilityBot's hunt logic)
        if hasattr(self.bot, 'notify_shot_result'):
            self.bot.notify_shot_result(bot_shot[0], bot_shot[1], bot_outcome)

        self.incoming_shots.append({
            "row": bot_shot[0], "col": bot_shot[1],
            "outcome": bot_outcome,
            "sunkShipClass": bot_sunk_class,
        })

        if all(s.sunk for s in self.player_fleet):
            self.status = "lost"

        self.turn += 1
        return self.snapshot()

    def snapshot(self) -> dict:
        """Current public game state — mirrors real API field names."""
        return {
            # yourFleet mirrors placement format + sunk (real API shape)
            "yourFleet": [
                {
                    "shipClass":   p["shipClass"],
                    "orientation": p["orientation"],
                    "startRow":    p["startRow"],
                    "startCol":    p["startCol"],
                    "sunk":        ship.sunk,
                }
                for p, ship in zip(self._player_placements, self.player_fleet)
            ],
            "yourShots":               list(self.player_shots),
            "incomingShots":           list(self.incoming_shots),
            "sunkOpponentShipClasses": list(self.sunk_opponent_classes),
            "status":                  self.status,
        }

    def notify_game_end(self):
        """Notify bot about player's shot pattern (for adaptive bots)."""
        shots = [(s["row"], s["col"]) for s in self.player_shots]
        self.bot.record_opponent_shots(shots)

    def game_score(self, bot, won: bool) -> dict:
        """Compute score for this completed game per real scoring rules."""
        score = 0
        hits  = 0
        for shot in self.player_shots:
            if shot["outcome"] in ("HIT", "SINK"):
                score += 1
                hits  += 1
            if shot["outcome"] == "SINK":
                score += SINK_BONUSES.get(shot["sunkShipClass"], 0)

        if won:
            score += bot.base_score

        our_ships_sunk = 0
        for ship in self.player_fleet:
            if ship.sunk:
                our_ships_sunk += 1
                score -= 2
                score -= SINK_BONUSES.get(ship.ship_class, 0)

        return {
            "score":        score,
            "won":          won,
            "hits":         hits,
            "oppShipsSunk": len(self.sunk_opponent_classes),
            "ourShipsSunk": our_ships_sunk,
        }
