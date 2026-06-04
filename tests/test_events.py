import pytest
from engine.agent.events import (
    EventEmitter, EventType,
    MoveMadeEvent, GameEndedEvent, PatternDetectedEvent,
    make_metrics_subscriber,
)


def test_handler_called_on_emit():
    received = []
    emitter = EventEmitter()
    emitter.on(EventType.MOVE_MADE, lambda e: received.append(e))

    event = MoveMadeEvent(1, 0, (3, 4), "hit", 2.0, "probability", "low")
    emitter.emit(EventType.MOVE_MADE, event)

    assert len(received) == 1
    assert received[0].result == "hit"


def test_multiple_handlers_on_same_event():
    log = []
    emitter = EventEmitter()
    emitter.on(EventType.MOVE_MADE, lambda e: log.append("handler-1"))
    emitter.on(EventType.MOVE_MADE, lambda e: log.append("handler-2"))

    emitter.emit(EventType.MOVE_MADE, MoveMadeEvent(1, 0, (0, 0), "miss", 1.0, "probability", "low"))

    assert log == ["handler-1", "handler-2"]


def test_unsubscribe_removes_handler():
    log = []
    handler = lambda e: log.append("called")
    emitter = EventEmitter()
    emitter.on(EventType.MOVE_MADE, handler)
    emitter.off(EventType.MOVE_MADE, handler)

    emitter.emit(EventType.MOVE_MADE, MoveMadeEvent(1, 0, (0, 0), "miss", 1.0, "probability", "low"))
    assert log == []


def test_handler_error_does_not_crash_emitter():
    received = []
    emitter = EventEmitter()
    emitter.on(EventType.MOVE_MADE, lambda e: (_ for _ in ()).throw(RuntimeError("boom")))
    emitter.on(EventType.MOVE_MADE, lambda e: received.append("ok"))

    # Should not raise — bad handler is isolated
    emitter.emit(EventType.MOVE_MADE, MoveMadeEvent(1, 0, (0, 0), "miss", 1.0, "probability", "low"))
    assert "ok" in received


def test_emitter_chaining():
    log = []
    emitter = (
        EventEmitter()
        .on(EventType.GAME_ENDED, lambda e: log.append("end"))
        .on(EventType.PATTERN_DETECTED, lambda e: log.append("pattern"))
    )

    emitter.emit(EventType.GAME_ENDED, GameEndedEvent(1, "bot-01", True, 17, 2.0, 87))
    emitter.emit(EventType.PATTERN_DETECTED, PatternDetectedEvent("bot-01", "fixed_placement", 2, "detail"))

    assert log == ["end", "pattern"]


def test_metrics_subscriber_counts_games():
    metrics, handlers = make_metrics_subscriber()
    emitter = EventEmitter()
    for et, h in handlers.items():
        emitter.on(et, h)

    emitter.emit(EventType.GAME_ENDED, GameEndedEvent(1, "bot-01", True, 50, 2.0, None))
    emitter.emit(EventType.GAME_ENDED, GameEndedEvent(2, "bot-02", False, 80, 2.0, None))

    assert metrics["total_games"] == 2
    assert metrics["wins"] == 1
    assert metrics["losses"] == 1


def test_metrics_tracks_improvement():
    metrics, handlers = make_metrics_subscriber()
    emitter = EventEmitter()
    for et, h in handlers.items():
        emitter.on(et, h)

    # baseline was 87, now won in 17 → improvement of 70
    emitter.emit(EventType.GAME_ENDED, GameEndedEvent(1, "bot-01", True, 17, 1.5, 87))

    assert len(metrics["improvements"]) == 1
    assert metrics["improvements"][0] == ("bot-01", 70)


def test_metrics_tracks_move_times():
    metrics, handlers = make_metrics_subscriber()
    emitter = EventEmitter()
    for et, h in handlers.items():
        emitter.on(et, h)

    for ms in [1.5, 2.0, 1.8]:
        emitter.emit(EventType.MOVE_MADE, MoveMadeEvent(1, 0, (0, 0), "miss", ms, "probability", "low"))

    assert len(metrics["move_times_ms"]) == 3
    assert abs(sum(metrics["move_times_ms"]) / 3 - 1.767) < 0.01


def test_no_cross_event_contamination():
    """Handlers for one event type must not fire for another."""
    log = []
    emitter = EventEmitter()
    emitter.on(EventType.GAME_ENDED, lambda e: log.append("game_ended"))

    emitter.emit(EventType.MOVE_MADE, MoveMadeEvent(1, 0, (0, 0), "miss", 1.0, "probability", "low"))
    assert log == []
