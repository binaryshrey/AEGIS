import numpy as np
import pytest
from engine.strategies.heatmap import Heatmap
from engine.strategies.targeting import Targeting
from engine.models.opponent import OpponentModel


@pytest.fixture
def h():
    return Heatmap(board_size=10)


# ── Frequency tracking ────────────────────────────────────────────────────────

def test_empty_heatmap_uniform(h):
    freq = h.frequency()
    assert freq.shape == (10, 10)
    # All equal when no games observed
    assert np.allclose(freq, freq[0][0])

def test_records_ship_cells(h):
    h.record([[0, 0], [0, 1], [0, 2]])
    assert h.counts[0][0] == 1
    assert h.counts[0][1] == 1
    assert h.counts[5][5] == 0

def test_frequency_is_fraction_of_games(h):
    h.record([[0, 0]])
    h.record([[0, 0]])
    h.record([[1, 1]])   # (0,0) in 2/3 games
    freq = h.frequency()
    assert abs(freq[0][0] - 2/3) < 1e-6
    assert abs(freq[1][1] - 1/3) < 1e-6

def test_frequency_max_is_one(h):
    for _ in range(5):
        h.record([[3, 4]])
    assert h.frequency()[3][4] == 1.0

def test_games_observed_increments(h):
    h.record([[0, 0]])
    h.record([[1, 1]])
    assert h.games_observed == 2


# ── Entropy ───────────────────────────────────────────────────────────────────

def test_deterministic_bot_has_high_stability():
    h = Heatmap(10)
    cells = [[0, i] for i in range(5)]   # always same placement
    for _ in range(10):
        h.record(cells)
    assert h.stability() > 0.8

def test_random_bot_has_high_entropy():
    np.random.seed(42)
    h = Heatmap(10)
    for _ in range(20):
        # Random cells each game
        xs = np.random.randint(0, 10, 17).tolist()
        ys = np.random.randint(0, 10, 17).tolist()
        h.record([[x, y] for x, y in zip(xs, ys)])
    assert h.entropy() > 0.45

def test_confidence_levels():
    # Deterministic — same cells every game → stability near 1.0
    h_det = Heatmap(10)
    for _ in range(10):
        h_det.record([[0, 0], [0, 1], [0, 2]])
    assert h_det.confidence() == "high"

    # No observations → stability=0.0 → low
    h_rand = Heatmap(10)
    assert h_rand.confidence() == "low"


# ── Hot cells ─────────────────────────────────────────────────────────────────

def test_hot_cells_above_threshold(h):
    for _ in range(8):
        h.record([[2, 3]])   # 8/8 games → frequency 1.0
    for _ in range(3):
        h.record([[5, 5]])   # 3/8... wait, needs to be out of total

    # Reset and test cleanly
    h2 = Heatmap(10)
    for _ in range(10):
        h2.record([[2, 3]])  # 100%
    for _ in range(4):
        h2.record([[5, 5]])  # 4/10 = 40% — below 0.5 threshold

    hot = h2.hot_cells(threshold=0.5)
    assert (2, 3) in hot
    assert (5, 5) not in hot

def test_hot_cells_sorted_by_frequency():
    # Each game records all three cells — control frequency by count per game
    h = Heatmap(10)
    for _ in range(10):
        h.record([[0, 0], [1, 1], [2, 2]])  # all 3 at 100%

    # Now verify sorting by overriding counts directly
    h.counts[0][0] = 10  # 100%
    h.counts[1][1] = 7   # 70%
    h.counts[2][2] = 6   # 60%
    h.games_observed = 10

    hot = h.hot_cells(threshold=0.5)
    assert (0, 0) in hot
    assert (1, 1) in hot
    assert hot[0] == (0, 0)  # highest first


# ── Boost matrix and targeting integration ────────────────────────────────────

def test_boost_matrix_shape(h):
    bm = h.boost_matrix()
    assert bm.shape == (10, 10)

def test_boost_matrix_high_freq_cell_gets_boosted():
    h = Heatmap(10)
    for _ in range(10):
        h.record([[3, 4]])
    bm = h.boost_matrix(weight=3.0)
    assert bm[3][4] > bm[0][0]   # high-freq cell > zero-freq cell

def test_boost_matrix_zero_freq_is_one(h):
    h.record([[0, 0]])
    bm = h.boost_matrix(weight=3.0)
    # Cell never seen → multiplier = 1.0 (no boost, no penalty)
    assert abs(bm[9][9] - 1.0) < 1e-6

def test_heatmap_applied_to_targeting():
    """Hot cells should be targeted earlier than cold cells."""
    np.random.seed(0)
    h = Heatmap(10)
    # Bot always has ships at column 0
    for _ in range(10):
        h.record([[i, 0] for i in range(5)])

    targeter = Targeting(10)
    targeter.apply_heatmap(h, weight=5.0)

    # Column 0 cells should have higher probability than column 9
    for row in range(5):
        assert targeter.prob[row][0] > targeter.prob[row][9]

def test_heatmap_from_model():
    model = OpponentModel("bot-test")
    # ≥9 cells so from_model doesn't filter it as partial data
    placement = [[0, 0], [0, 1], [0, 2], [0, 3], [0, 4],
                 [2, 0], [2, 1], [2, 2], [2, 3]]
    for _ in range(5):
        model.record_game([[5, 5]], placement, True)

    h = Heatmap.from_model(model, board_size=10)
    assert h.games_observed == 5
    assert h.frequency()[0][0] == 1.0

def test_flat_heatmap_no_effect_on_uniform_prob():
    """No observations → boost_matrix is all 1.0 → prob map unchanged."""
    h = Heatmap(10)   # no observations
    t1 = Targeting(10)
    t2 = Targeting(10)
    t2.apply_heatmap(h, weight=3.0)
    # boost_matrix returns all 1.0 when no games observed → no change
    assert np.allclose(t1.prob, t2.prob)
