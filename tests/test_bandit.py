import pytest
import numpy as np
from engine.agent.bandit import ArmStats, ThompsonBandit, BanditStore, STRATEGIES, _moves_to_reward


# ── Reward function ──────────────────────────────────────────────────────────

def test_perfect_game_gives_max_reward():
    assert _moves_to_reward(17) == 1.0

def test_terrible_game_gives_zero_reward():
    assert _moves_to_reward(80) == 0.0
    assert _moves_to_reward(100) == 0.0

def test_mid_game_gives_partial_reward():
    r = _moves_to_reward(48)  # midpoint between 17 and 80
    assert 0.3 < r < 0.7


# ── ArmStats ──────────────────────────────────────────────────────────────────

def test_arm_starts_uniform():
    arm = ArmStats("probability")
    assert arm.wins == 0
    assert arm.losses == 0
    assert arm.games == 0

def test_arm_updates_with_moves():
    arm = ArmStats("hunt")
    arm.update(moves=17)   # perfect game → high reward
    arm.update(moves=80)   # terrible game → zero reward
    assert arm.games == 2
    assert arm.wins > 0     # at least some pseudo-wins from the 17-move game
    assert arm.losses > 0   # at least some pseudo-losses from the 80-move game

def test_efficient_arm_has_high_pseudo_wins():
    arm = ArmStats("exploit")
    for _ in range(5):
        arm.update(moves=17)
    assert arm.wins > arm.losses  # 17-move games should produce high reward

def test_inefficient_arm_has_high_pseudo_losses():
    arm = ArmStats("hunt")
    for _ in range(5):
        arm.update(moves=70, won=False, ships_lost=4)
    assert arm.losses > arm.wins

def test_avg_moves_bayesian_smoothed():
    """Bayesian smoothing pulls avg toward prior (50) with few samples."""
    arm = ArmStats("probability")
    arm.update(moves=20)
    arm.update(moves=30)
    # Raw avg would be 25.0, but smoothed: (5*50 + 50) / (5+2) ≈ 42.86
    assert arm.avg_moves > 25.0  # pulled toward prior
    assert arm.avg_moves < 50.0  # but below prior (actual data is lower)

def test_efficiency_zero_with_no_data():
    assert ArmStats("probability").efficiency == 0.0

def test_sample_returns_value_in_range():
    arm = ArmStats("hunt")
    for _ in range(100):
        s = arm.sample()
        assert 0.0 <= s <= 1.0

def test_sample_biases_toward_efficient_strategy():
    """Arm with 17-move games should sample higher than arm with 70-move games."""
    np.random.seed(42)
    good = ArmStats("hunt")
    bad  = ArmStats("probability")
    for _ in range(20):
        good.update(moves=17)
    for _ in range(20):
        bad.update(moves=70)
    good_avg = sum(good.sample() for _ in range(1000)) / 1000
    bad_avg  = sum(bad.sample()  for _ in range(1000)) / 1000
    assert good_avg > bad_avg


# ── ThompsonBandit ────────────────────────────────────────────────────────────

def test_select_returns_valid_strategy():
    bandit = ThompsonBandit()
    strategy = bandit.select("bot-01")
    assert strategy in STRATEGIES

def test_select_respects_available_filter():
    bandit = ThompsonBandit()
    for _ in range(100):
        result = bandit.select("bot-01", available=["hunt", "probability"])
        assert result in ["hunt", "probability"]
        assert result != "exploit"

def test_update_records_outcome():
    bandit = ThompsonBandit()
    bandit.update("bot-01", "hunt", moves=20)
    bandit.update("bot-01", "hunt", moves=30)
    stats = bandit.stats("bot-01")
    assert stats["hunt"]["games"] == 2
    assert 25.0 < stats["hunt"]["avg_moves"] < 50.0  # Bayesian smoothed

def test_converges_to_best_strategy():
    """After enough data, bandit should select the strategy with lowest move count."""
    np.random.seed(0)
    bandit = ThompsonBandit()
    # Make exploit clearly the best (17 moves = perfect)
    for _ in range(15):
        bandit.update("bot-01", "exploit", moves=17)
    for _ in range(15):
        bandit.update("bot-01", "hunt", moves=70)
    for _ in range(15):
        bandit.update("bot-01", "probability", moves=70)

    # Run 100 selections — exploit should dominate
    counts = {"exploit": 0, "hunt": 0, "probability": 0}
    for _ in range(100):
        counts[bandit.select("bot-01")] += 1
    assert counts["exploit"] > 80

def test_explores_with_no_data():
    """Without data, should try all strategies over many selections."""
    np.random.seed(1)
    bandit = ThompsonBandit()
    counts = {"exploit": 0, "hunt": 0, "probability": 0}
    for _ in range(300):
        counts[bandit.select("bot-01")] += 1
    # All strategies should get some exploration
    for s in STRATEGIES:
        assert counts[s] > 10

def test_best_strategy_returns_lowest_moves():
    bandit = ThompsonBandit()
    for _ in range(10):
        bandit.update("bot-01", "exploit", moves=17)
    for _ in range(10):
        bandit.update("bot-01", "hunt", moves=50)
    assert bandit.best_strategy("bot-01") == "exploit"

def test_separate_arms_per_opponent():
    bandit = ThompsonBandit()
    for _ in range(10):
        bandit.update("bot-01", "hunt", moves=17)
    for _ in range(10):
        bandit.update("bot-02", "hunt", moves=70)
    # With 10 games, smoothing is mild: bot-01 (17mv) should be well below bot-02 (70mv)
    assert bandit.stats("bot-01")["hunt"]["avg_moves"] < 35.0
    assert bandit.stats("bot-02")["hunt"]["avg_moves"] > 55.0


# ── Persistence ───────────────────────────────────────────────────────────────

def test_bandit_persists_to_disk(tmp_path):
    store = BanditStore(path=str(tmp_path / "bandit.json"))
    store.bandit.update("bot-01", "exploit", moves=17)
    store.save()

    store2 = BanditStore(path=str(tmp_path / "bandit.json"))
    assert store2.bandit.stats("bot-01")["exploit"]["games"] == 1

def test_bandit_compounds_across_loads(tmp_path):
    path = str(tmp_path / "bandit.json")

    s1 = BanditStore(path=path)
    s1.bandit.update("bot-01", "hunt", moves=20)
    s1.save()

    s2 = BanditStore(path=path)
    s2.bandit.update("bot-01", "hunt", moves=30)
    s2.save()

    s3 = BanditStore(path=path)
    assert s3.bandit.stats("bot-01")["hunt"]["games"] == 2
    assert 25.0 < s3.bandit.stats("bot-01")["hunt"]["avg_moves"] < 50.0  # smoothed
