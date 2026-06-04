import pytest
from engine.models.opponent import OpponentModel
from engine.agent.feedback import FeedbackEngine, FeedbackStore, LessonType, Lesson

# Realistic 17-cell placement for fixed-placement tests
_FULL_PLACEMENT = [
    [0, 0], [0, 1], [0, 2], [0, 3], [0, 4],  # CARRIER (5)
    [2, 0], [2, 1], [2, 2], [2, 3],            # BATTLESHIP (4)
    [4, 0], [4, 1], [4, 2],                     # CRUISER (3)
    [6, 0], [6, 1], [6, 2],                     # SUBMARINE (3)
    [8, 0], [8, 1],                              # DESTROYER (2)
]


@pytest.fixture
def store(tmp_path):
    return FeedbackStore(path=str(tmp_path / "lessons.json"))

@pytest.fixture
def engine(store):
    return FeedbackEngine(store)

def _model_with_fixed_placement(games=5):
    m = OpponentModel("bot-test")
    for i in range(games):
        m.record_game([[5, 5]], _FULL_PLACEMENT, True)
        m.record_moves(50 + i)  # populate move_history for rolling avg
    return m

def _model_with_fixed_firing(games=5):
    m = OpponentModel("bot-test")
    firing = [[1, 1], [2, 2], [3, 3]]
    for _ in range(games):
        m.record_game(firing, [[9, 9]], True)
    return m


# ── Lesson generation ──────────────────────────────────────────────────────────

def test_generates_exploit_lesson_for_fixed_placement(engine):
    model = _model_with_fixed_placement()
    lessons = engine.generate("bot-test", model, {
        "won": True, "moves": 17, "avg_ms": 2.0,
        "strategy_used": "exploit", "baseline_moves": 87,
    })
    types = [l.lesson_type for l in lessons]
    assert LessonType.PLACEMENT_EXPLOIT.value in types

def test_exploit_lesson_calculates_gain(engine):
    model = _model_with_fixed_placement()
    lessons = engine.generate("bot-test", model, {
        "won": True, "moves": 17, "avg_ms": 2.0,
        "strategy_used": "exploit", "baseline_moves": 87,
    })
    exploit = next(l for l in lessons if l.lesson_type == LessonType.PLACEMENT_EXPLOIT.value)
    assert exploit.gain == 70  # 87 - 17

def test_generates_firing_dodge_lesson(engine):
    model = _model_with_fixed_firing()
    lessons = engine.generate("bot-test", model, {
        "won": True, "moves": 60, "avg_ms": 2.0,
        "strategy_used": "probability", "baseline_moves": None,
    })
    types = [l.lesson_type for l in lessons]
    assert LessonType.FIRING_DODGE.value in types

def test_no_strategy_lessons_generated(engine):
    """Strategy lessons are removed — bandit handles strategy selection via evidence."""
    model = _model_with_fixed_placement(games=3)
    lessons = engine.generate("bot-test", model, {
        "won": True, "moves": 30, "avg_ms": 2.0,
        "strategy_used": "probability", "baseline_moves": 60,
    })
    types = [l.lesson_type for l in lessons]
    # Only factual lessons: placement, firing, timing — no strategy opinions
    for t in types:
        assert t in (
            LessonType.PLACEMENT_EXPLOIT.value,
            LessonType.FIRING_DODGE.value,
            LessonType.TIMING_OK.value,
            LessonType.TIMING_RISK.value,
        )

def test_no_strategy_lessons_on_loss(engine):
    """Losses no longer generate strategy_failed lessons."""
    model = _model_with_fixed_placement(games=3)
    lessons = engine.generate("bot-test", model, {
        "won": False, "moves": 90, "avg_ms": 2.0,
        "strategy_used": "exploit", "baseline_moves": 60,
    })
    types = [l.lesson_type for l in lessons]
    assert "strategy_effective" not in types
    assert "strategy_failed" not in types

def test_generates_timing_ok_lesson_for_fast_moves(engine):
    model = OpponentModel("bot-test")
    lessons = engine.generate("bot-test", model, {
        "won": True, "moves": 50, "avg_ms": 2.0,
        "strategy_used": "probability", "baseline_moves": None,
    })
    types = [l.lesson_type for l in lessons]
    assert LessonType.TIMING_OK.value in types

def test_no_lessons_without_data(engine):
    model = OpponentModel("bot-test")  # 0 games
    lessons = engine.generate("bot-test", model, {
        "won": True, "moves": 50, "avg_ms": 2.0,
        "strategy_used": "probability", "baseline_moves": None,
    })
    exploit = [l for l in lessons if l.lesson_type == LessonType.PLACEMENT_EXPLOIT.value]
    assert len(exploit) == 0


# ── Store persistence ─────────────────────────────────────────────────────────

def test_lesson_persists_to_disk(tmp_path):
    store = FeedbackStore(path=str(tmp_path / "lessons.json"))
    lesson = Lesson(
        opponent_id="bot-01", lesson_type=LessonType.PLACEMENT_EXPLOIT.value,
        summary="test", detail="detail", metric_before=87.0, metric_after=17.0,
        gain=70.0, confidence=0.9, games_basis=3,
    )
    store.add(lesson)

    store2 = FeedbackStore(path=str(tmp_path / "lessons.json"))
    assert len(store2.lessons) == 1
    assert store2.lessons[0].gain == 70.0

def test_higher_confidence_replaces_lower(tmp_path):
    store = FeedbackStore(path=str(tmp_path / "lessons.json"))
    l1 = Lesson("bot-01", LessonType.PLACEMENT_EXPLOIT.value, "s", "d", None, None, None, 0.5, 2)
    l2 = Lesson("bot-01", LessonType.PLACEMENT_EXPLOIT.value, "s", "d", None, None, None, 0.9, 4)
    store.add(l1)
    store.add(l2)
    assert len(store.lessons) == 1
    assert store.lessons[0].confidence == 0.9

def test_newer_lesson_always_replaces_older(tmp_path):
    """Newer lessons always replace older ones (agent can unlearn stale data)."""
    store = FeedbackStore(path=str(tmp_path / "lessons.json"))
    l1 = Lesson("bot-01", LessonType.PLACEMENT_EXPLOIT.value, "s", "d", None, None, None, 0.9, 4)
    l2 = Lesson("bot-01", LessonType.PLACEMENT_EXPLOIT.value, "s", "d", None, None, None, 0.5, 2)
    store.add(l1)
    store.add(l2)
    assert store.lessons[0].confidence == 0.5  # newer replaces older

def test_dedup_by_opponent_and_type(tmp_path):
    """Same opponent + type → replaced. Different opponent → separate."""
    store = FeedbackStore(path=str(tmp_path / "lessons.json"))
    l1 = Lesson("bot-01", LessonType.PLACEMENT_EXPLOIT.value, "s", "d", None, None, None, 0.8, 3)
    l2 = Lesson("bot-02", LessonType.PLACEMENT_EXPLOIT.value, "s", "d", None, None, None, 0.9, 4)
    l3 = Lesson("bot-01", LessonType.FIRING_DODGE.value, "s", "d", None, None, None, 0.7, 3)
    store.add(l1)
    store.add(l2)
    store.add(l3)
    assert len(store.lessons) == 3  # all different keys
