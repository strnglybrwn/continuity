from unittest.mock import MagicMock

import pytest

from app.scheduler import run_heartbeat_evaluation
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

    result = run_heartbeat_evaluation()

    assert result == expected
    session_factory.assert_called_once_with()
    evaluation.assert_called_once_with(session)
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

    with pytest.raises(
        RuntimeError,
        match="database unavailable",
    ):
        run_heartbeat_evaluation()

    session.rollback.assert_called_once_with()
    session.close.assert_called_once_with()
