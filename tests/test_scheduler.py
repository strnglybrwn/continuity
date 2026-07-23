from unittest.mock import MagicMock

import pytest

from app.scheduler import run_heartbeat_evaluation
from app.services.heartbeat_event_service import HeartbeatPendingMetrics
from app.services.heartbeat_service import HeartbeatEvaluationResult


def test_run_heartbeat_evaluation_uses_dedicated_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock()
    expected = HeartbeatEvaluationResult(
        evaluated=12,
        changed=3,
    )

    session_factory = MagicMock(return_value=session)
    evaluation = MagicMock(return_value=expected)

    monkeypatch.setattr(
        "app.scheduler.SessionLocal",
        session_factory,
    )
    monkeypatch.setattr(
        "app.scheduler.evaluate_due_heartbeats",
        evaluation,
    )
    metrics_lookup = MagicMock(
        return_value=HeartbeatPendingMetrics(
            pending_total=0,
            pending_reminder_due_total=0,
            oldest_pending_occurred_at=None,
            oldest_pending_age_seconds=None,
            stale_pending_alert=False,
            stale_reminder_due_total=0,
        )
    )
    monkeypatch.setattr(
        "app.scheduler.get_pending_heartbeat_event_metrics",
        metrics_lookup,
    )

    result = run_heartbeat_evaluation()

    assert result == expected
    session_factory.assert_called_once_with()
    evaluation.assert_called_once_with(session)
    metrics_lookup.assert_called_once()
    session.rollback.assert_not_called()
    session.close.assert_called_once_with()


def test_run_heartbeat_evaluation_rolls_back_after_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock()
    session_factory = MagicMock(return_value=session)
    evaluation = MagicMock(
        side_effect=RuntimeError("database unavailable"),
    )

    monkeypatch.setattr(
        "app.scheduler.SessionLocal",
        session_factory,
    )
    monkeypatch.setattr(
        "app.scheduler.evaluate_due_heartbeats",
        evaluation,
    )
    monkeypatch.setattr(
        "app.scheduler.get_pending_heartbeat_event_metrics",
        MagicMock(),
    )

    with pytest.raises(
        RuntimeError,
        match="database unavailable",
    ):
        run_heartbeat_evaluation()

    session.rollback.assert_called_once_with()
    session.close.assert_called_once_with()


def test_run_heartbeat_evaluation_logs_when_stale_events_detected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock()
    session_factory = MagicMock(return_value=session)
    evaluation = MagicMock(
        return_value=HeartbeatEvaluationResult(
            evaluated=1,
            changed=0,
        )
    )
    metrics_lookup = MagicMock(
        return_value=HeartbeatPendingMetrics(
            pending_total=3,
            pending_reminder_due_total=2,
            oldest_pending_occurred_at=None,
            oldest_pending_age_seconds=7200,
            stale_pending_alert=True,
            stale_reminder_due_total=1,
        )
    )
    logger = MagicMock()

    monkeypatch.setattr(
        "app.scheduler.SessionLocal",
        session_factory,
    )
    monkeypatch.setattr(
        "app.scheduler.evaluate_due_heartbeats",
        evaluation,
    )
    monkeypatch.setattr(
        "app.scheduler.get_pending_heartbeat_event_metrics",
        metrics_lookup,
    )
    monkeypatch.setattr(
        "app.scheduler.logger",
        logger,
    )

    run_heartbeat_evaluation()

    logger.warning.assert_called_once()
