"""
Thompson Sampling Bandit — strategy selection via Bayesian inference.

Reward signal: normalized move efficiency (not win/loss).

Why move-based reward:
  - Win/loss is useless when agent wins 100% of games
  - 17-move win is dramatically better than 52-move win
  - Normalizing to [0, 1] lets Beta distribution work correctly

Why Thompson Sampling over UCB:
  - UCB is frequentist — needs many samples to be reliable
  - Thompson is Bayesian — works well with 2-5 samples (our case)
  - Simpler to implement correctly
"""
import json
import os
import tempfile
import numpy as np
from dataclasses import dataclass, field, asdict


def _atomic_json_write(path: str, data) -> None:
    """Write JSON atomically: write to temp file, then rename."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _safe_json_load(path: str, default=None):
    """Load JSON with fallback on corrupt/missing files."""
    if not os.path.exists(path):
        return default
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"  [warning] Corrupt JSON in {path}: {e} — using default")
        backup = path + ".corrupt"
        try:
            os.replace(path, backup)
        except OSError:
            pass
        return default


STRATEGIES = ["probability", "hunt", "exploit"]

# Move thresholds for reward normalization
# 17 = theoretical minimum (all ship cells, no misses)
# 80 = rough upper bound for a reasonable game
_MIN_MOVES = 17
_MAX_MOVES = 80


def _moves_to_reward(moves: int) -> float:
    """
    Convert move count to [0, 1] reward.
    17 moves → 1.0 (perfect), 80+ moves → 0.0, linear between.
    """
    if moves <= _MIN_MOVES:
        return 1.0
    if moves >= _MAX_MOVES:
        return 0.0
    return 1.0 - (moves - _MIN_MOVES) / (_MAX_MOVES - _MIN_MOVES)


def composite_reward(won: bool, moves: int, ships_lost: int = 0) -> float:
    """
    Composite reward blending offense, defense, and outcome.
      0.5 * win + 0.3 * move_efficiency + 0.2 * survival
    Against weak bots: offense dominates (we always win).
    Against strong bots: survival and win matter.
    """
    win_r = 1.0 if won else 0.0
    move_r = _moves_to_reward(moves)
    survive_r = max(0.0, 1.0 - ships_lost / 5.0)  # 0 lost → 1.0, 5 lost → 0.0
    return 0.5 * win_r + 0.3 * move_r + 0.2 * survive_r


@dataclass
class ArmStats:
    """Accumulated reward for one strategy against one opponent."""
    strategy:  str
    wins:      int = 0      # pseudo-wins (accumulated reward)
    losses:    int = 0      # pseudo-losses (accumulated 1-reward)
    games:     int = 0      # actual games played
    total_moves: int = 0    # sum of moves across games (for avg computation)

    def sample(self) -> float:
        """
        Draw one sample from Beta(wins+1, losses+1).
        Higher sample = more promising strategy right now.
        """
        return float(np.random.beta(self.wins + 1, self.losses + 1))

    def update(self, moves: int, won: bool = True, ships_lost: int = 0):
        """
        Update with composite reward blending offense, defense, and outcome.
        A 17-move perfect win → reward ≈ 1.0.
        A loss with 5 ships sunk → reward ≈ 0.0.
        """
        reward = composite_reward(won, moves, ships_lost)
        # Scale to pseudo-counts (multiply by weight for stronger signal)
        self.wins += round(reward * 10)
        self.losses += round((1 - reward) * 10)
        self.games += 1
        self.total_moves += moves

    @property
    def total(self) -> int:
        return self.games

    @property
    def avg_moves(self) -> float:
        """Bayesian-smoothed average: pull toward prior until enough data."""
        prior_games = 5
        prior_mean = 50.0  # assume average game before we have evidence
        return (prior_games * prior_mean + self.total_moves) / (prior_games + self.games)

    @property
    def efficiency(self) -> float:
        """Average reward across games."""
        if self.games == 0:
            return 0.0
        return _moves_to_reward(self.avg_moves)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ArmStats":
        # Backward compat: old format had wins/losses as win/loss counts
        return cls(
            strategy=d["strategy"],
            wins=d.get("wins", 0),
            losses=d.get("losses", 0),
            games=d.get("games", 0),
            total_moves=d.get("total_moves", 0),
        )


class ThompsonBandit:
    """
    Per-opponent multi-armed bandit.
    Each opponent gets its own set of arms (one per strategy).
    """

    def __init__(self):
        # { opponent_id: { strategy: ArmStats } }
        self._arms: dict[str, dict[str, ArmStats]] = {}

    def _get_arms(self, opponent_id: str) -> dict[str, ArmStats]:
        if opponent_id not in self._arms:
            self._arms[opponent_id] = {
                s: ArmStats(strategy=s) for s in STRATEGIES
            }
        return self._arms[opponent_id]

    def select(self, opponent_id: str, available: list[str] = None,
               min_games: int = 3) -> str:
        """
        Sample from each arm's Beta distribution.
        Return the strategy with the highest sample — the one that
        looks most promising right now given what we know.

        available: restrict to a subset (e.g. ["probability", "hunt"]
                   when we don't have known placement yet)
        min_games: arms with fewer games than this are forced to explore
                   (sample from Uniform(0,1) instead of their Beta posterior)
                   to prevent 1 lucky game from locking in a strategy.
        """
        arms = self._get_arms(opponent_id)
        candidates = available or STRATEGIES

        # Force exploration for under-sampled arms: any arm with < min_games
        # gets a uniform random sample (wide exploration). Arms with enough
        # data use their Beta posterior (exploitation).
        under_sampled = [s for s in candidates if s in arms and arms[s].games < min_games]
        if under_sampled:
            # If ANY arm hasn't been tried enough, pick uniformly among
            # under-sampled arms to gather evidence before committing.
            return under_sampled[int(np.random.randint(len(under_sampled)))]

        samples = {s: arms[s].sample() for s in candidates if s in arms}
        return max(samples, key=samples.__getitem__)

    def update(self, opponent_id: str, strategy: str, moves: int,
               won: bool = True, ships_lost: int = 0):
        """Record the outcome of using a strategy against an opponent."""
        arms = self._get_arms(opponent_id)
        if strategy in arms:
            arms[strategy].update(moves, won=won, ships_lost=ships_lost)

    def stats(self, opponent_id: str) -> dict[str, dict]:
        """Return current arm stats for an opponent."""
        arms = self._get_arms(opponent_id)
        return {
            s: {
                "games": a.games,
                "avg_moves": round(a.avg_moves, 1),
                "efficiency": round(a.efficiency, 2),
                "pseudo_wins": a.wins,
                "pseudo_losses": a.losses,
            }
            for s, a in arms.items()
        }

    def best_strategy(self, opponent_id: str, min_games: int = 5) -> str:
        """Return the strategy with the best average efficiency.
        Requires min_games before trusting the estimate."""
        arms = self._get_arms(opponent_id)
        confident = {s: a for s, a in arms.items() if a.games >= min_games}
        if not confident:
            # Not enough data on any arm — fall back to any played arm
            played = {s: a for s, a in arms.items() if a.games > 0}
            if not played:
                return "probability"
            return min(played, key=lambda s: played[s].avg_moves)
        return min(confident, key=lambda s: confident[s].avg_moves)

    def to_dict(self) -> dict:
        return {
            opp: {s: arm.to_dict() for s, arm in arms.items()}
            for opp, arms in self._arms.items()
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ThompsonBandit":
        b = cls()
        for opp, arms in d.items():
            b._arms[opp] = {s: ArmStats.from_dict(a) for s, a in arms.items()}
        return b


class BanditStore:
    """Persists bandit state to disk — survives restarts."""

    def __init__(self, path: str = "data/bandit.json"):
        self.path = path
        self.bandit = ThompsonBandit()
        self._load()

    def _load(self):
        data = _safe_json_load(self.path, default={})
        if data:
            self.bandit = ThompsonBandit.from_dict(data)

    def save(self):
        _atomic_json_write(self.path, self.bandit.to_dict())

    def summary(self) -> list[str]:
        lines = []
        for opp in self.bandit._arms:
            parts = []
            for s, v in self.bandit.stats(opp).items():
                if v["games"] > 0:
                    parts.append(f"{s}:{v['games']}G avg={v['avg_moves']}mv eff={v['efficiency']:.0%}")
            if parts:
                lines.append(f"  {opp:<22} {' | '.join(parts)}")
        return lines
