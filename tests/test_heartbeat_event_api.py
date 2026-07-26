from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.domain.heartbeat import HeartbeatEventType, HeartbeatStatus
from app.domain.notification import (
    Notification,
    NotificationChannel,
    NotificationMessage,
    NotificationRecipient,
)
from app.main import app
from app.persistence.database import get_db_session
from app.persistence.models import Heartbeat, HeartbeatEvent
from app.services.heartbeat_event_service import (
    EscalationNotificationPreparationError,
    HeartbeatAttachmentSummary,
    HeartbeatPendingMetrics,
    OverdueNotificationPreparationError,
    ReminderNotificationPreparationError,
)


def test_list_pending_heartbeat_events_endpoint() -> None:
    heartbeat_id = uuid4()
    event_id = uuid4()
    occurred_at = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)

    heartbeat = Heartbeat(
        id=heartbeat_id,
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.ACTIVE,
        interval_days=30,
        reminder_days=7,
        next_due_at=datetime(2026, 8, 21, tzinfo=UTC),
    )

    event = HeartbeatEvent(
        id=event_id,
        heartbeat_id=heartbeat_id,
        event_type=HeartbeatEventType.REMINDER_DUE,
        occurred_at=occurred_at,
        created_at=occurred_at,
    )
    event.heartbeat = heartbeat

    session = MagicMock()
    query = session.query.return_value
    query.options.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
        event
    ]

    def override_database_session():
        yield session

    app.dependency_overrides[get_db_session] = override_database_session

    try:
        response = TestClient(app).get("/heartbeat-events/pending?limit=25")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": str(event_id),
            "heartbeat_id": str(heartbeat_id),
            "event_type": "reminder_due",
            "occurred_at": occurred_at.isoformat().replace(
                "+00:00",
                "Z",
            ),
            "delivered_at": None,
            "created_at": occurred_at.isoformat().replace(
                "+00:00",
                "Z",
            ),
            "owner_name": "Scott",
            "owner_email": "scott@example.com",
        }
    ]


def test_evaluate_due_heartbeat_events_endpoint() -> None:
    session = MagicMock()

    def override_database_session():
        yield session

    app.dependency_overrides[get_db_session] = override_database_session

    from app.api import heartbeat_events
    from app.services.heartbeat_service import HeartbeatEvaluationResult

    original = heartbeat_events.evaluate_due_heartbeats
    heartbeat_events.evaluate_due_heartbeats = MagicMock(
        return_value=HeartbeatEvaluationResult(
            evaluated=12,
            changed=3,
        )
    )

    try:
        response = TestClient(app).post("/heartbeat-events/evaluate-due")
    finally:
        heartbeat_events.evaluate_due_heartbeats = original
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "evaluated": 12,
        "changed": 3,
    }


def test_mark_heartbeat_event_delivered_endpoint() -> None:
    heartbeat_id = uuid4()
    event_id = uuid4()
    occurred_at = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)
    delivered_at = datetime(2026, 7, 22, 13, 0, tzinfo=UTC)

    event = HeartbeatEvent(
        id=event_id,
        heartbeat_id=heartbeat_id,
        event_type=HeartbeatEventType.OVERDUE,
        occurred_at=occurred_at,
        created_at=occurred_at,
    )

    session = MagicMock()
    session.get.return_value = event

    def refresh(instance: object) -> None:
        if isinstance(instance, HeartbeatEvent):
            instance.delivered_at = delivered_at

    session.refresh.side_effect = refresh

    def override_database_session():
        yield session

    app.dependency_overrides[get_db_session] = override_database_session

    try:
        response = TestClient(app).post(f"/heartbeat-events/{event_id}/delivered")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "id": str(event_id),
        "heartbeat_id": str(heartbeat_id),
        "event_type": "overdue",
        "occurred_at": occurred_at.isoformat().replace(
            "+00:00",
            "Z",
        ),
        "delivered_at": delivered_at.isoformat().replace(
            "+00:00",
            "Z",
        ),
        "created_at": occurred_at.isoformat().replace(
            "+00:00",
            "Z",
        ),
    }

    session.commit.assert_called_once()


def test_mark_heartbeat_event_delivered_endpoint_returns_404() -> None:
    event_id = uuid4()
    session = MagicMock()
    session.get.return_value = None

    def override_database_session():
        yield session

    app.dependency_overrides[get_db_session] = override_database_session

    try:
        response = TestClient(app).post(f"/heartbeat-events/{event_id}/delivered")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Heartbeat event not found"}
    session.commit.assert_not_called()


def test_prepare_heartbeat_event_reminder_endpoint() -> None:
    heartbeat_id = uuid4()
    event_id = uuid4()
    occurred_at = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)

    event = HeartbeatEvent(
        id=event_id,
        heartbeat_id=heartbeat_id,
        event_type=HeartbeatEventType.REMINDER_DUE,
        occurred_at=occurred_at,
        created_at=occurred_at,
    )

    notification = Notification(
        channel=NotificationChannel.EMAIL,
        recipient=NotificationRecipient(
            name="Scott",
            email="scott@example.com",
        ),
        message=NotificationMessage(
            template_name="heartbeat_reminder",
            template_version=1,
            subject="Continuity check-in reminder",
            text_body="text reminder",
            html_body="<p>html reminder</p>",
        ),
    )
    checkin_url = "https://continuity.boardmad.com/checkins/example-token"

    session = MagicMock()

    def override_database_session():
        yield session

    app.dependency_overrides[get_db_session] = override_database_session

    from app.api import heartbeat_events

    original = heartbeat_events.prepare_reminder_notification
    heartbeat_events.prepare_reminder_notification = MagicMock(
        return_value=(event, notification, checkin_url)
    )

    try:
        response = TestClient(app).post(f"/heartbeat-events/{event_id}/prepare-reminder")
    finally:
        heartbeat_events.prepare_reminder_notification = original
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "event_id": str(event_id),
        "heartbeat_id": str(heartbeat_id),
        "owner_name": "Scott",
        "owner_email": "scott@example.com",
        "subject": "Continuity check-in reminder",
        "text_body": "text reminder",
        "html_body": "<p>html reminder</p>",
        "checkin_url": checkin_url,
    }


def test_prepare_heartbeat_event_reminder_endpoint_returns_404() -> None:
    event_id = uuid4()
    session = MagicMock()

    def override_database_session():
        yield session

    app.dependency_overrides[get_db_session] = override_database_session

    from app.api import heartbeat_events

    original = heartbeat_events.prepare_reminder_notification
    heartbeat_events.prepare_reminder_notification = MagicMock(
        side_effect=ReminderNotificationPreparationError("Heartbeat event not found")
    )

    try:
        response = TestClient(app).post(f"/heartbeat-events/{event_id}/prepare-reminder")
    finally:
        heartbeat_events.prepare_reminder_notification = original
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Heartbeat event not found"}


def test_prepare_heartbeat_event_reminder_endpoint_returns_409() -> None:
    event_id = uuid4()
    session = MagicMock()

    def override_database_session():
        yield session

    app.dependency_overrides[get_db_session] = override_database_session

    from app.api import heartbeat_events

    original = heartbeat_events.prepare_reminder_notification
    heartbeat_events.prepare_reminder_notification = MagicMock(
        side_effect=ReminderNotificationPreparationError("Heartbeat event is already delivered")
    )

    try:
        response = TestClient(app).post(f"/heartbeat-events/{event_id}/prepare-reminder")
    finally:
        heartbeat_events.prepare_reminder_notification = original
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json() == {"detail": "Heartbeat event is already delivered"}


def test_pending_heartbeat_event_limit_is_validated() -> None:
    session = MagicMock()

    def override_database_session():
        yield session

    app.dependency_overrides[get_db_session] = override_database_session

    try:
        response = TestClient(app).get("/heartbeat-events/pending?limit=0")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_heartbeat_event_metrics_endpoint() -> None:
    session = MagicMock()

    def override_database_session():
        yield session

    app.dependency_overrides[get_db_session] = override_database_session

    from app.api import heartbeat_events

    original = heartbeat_events.get_pending_heartbeat_event_metrics
    heartbeat_events.get_pending_heartbeat_event_metrics = MagicMock(
        return_value=HeartbeatPendingMetrics(
            pending_total=4,
            pending_reminder_due_total=3,
            oldest_pending_occurred_at=datetime(2026, 7, 23, 10, 0, tzinfo=UTC),
            oldest_pending_age_seconds=900,
            stale_pending_alert=True,
            stale_reminder_due_total=1,
        )
    )

    try:
        response = TestClient(app).get("/heartbeat-events/metrics?stale_after_seconds=600")
    finally:
        heartbeat_events.get_pending_heartbeat_event_metrics = original
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "pending_total": 4,
        "pending_reminder_due_total": 3,
        "oldest_pending_occurred_at": "2026-07-23T10:00:00Z",
        "oldest_pending_age_seconds": 900,
        "stale_pending_alert": True,
        "stale_reminder_due_total": 1,
        "stale_after_seconds": 600,
        "pending_overdue_total": 0,
        "pending_escalation_due_total": 0,
        "stale_overdue_total": 0,
        "stale_escalation_due_total": 0,
    }


def test_heartbeat_event_metrics_threshold_is_validated() -> None:
    session = MagicMock()

    def override_database_session():
        yield session

    app.dependency_overrides[get_db_session] = override_database_session

    try:
        response = TestClient(app).get("/heartbeat-events/metrics?stale_after_seconds=0")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_prepare_heartbeat_event_overdue_endpoint() -> None:
    heartbeat_id = uuid4()
    event_id = uuid4()
    occurred_at = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)

    event = HeartbeatEvent(
        id=event_id,
        heartbeat_id=heartbeat_id,
        event_type=HeartbeatEventType.OVERDUE,
        occurred_at=occurred_at,
        created_at=occurred_at,
    )

    notification = Notification(
        channel=NotificationChannel.EMAIL,
        recipient=NotificationRecipient(
            name="Scott",
            email="scott@example.com",
        ),
        message=NotificationMessage(
            template_name="heartbeat_overdue_warning",
            template_version=1,
            subject="Continuity check-in overdue",
            text_body="text overdue",
            html_body="<p>html overdue</p>",
        ),
    )
    checkin_url = "https://continuity.boardmad.com/checkins/example-token"

    session = MagicMock()

    def override_database_session():
        yield session

    app.dependency_overrides[get_db_session] = override_database_session

    from app.api import heartbeat_events

    original = heartbeat_events.prepare_overdue_notification
    heartbeat_events.prepare_overdue_notification = MagicMock(
        return_value=(event, notification, checkin_url)
    )

    try:
        response = TestClient(app).post(f"/heartbeat-events/{event_id}/prepare-overdue")
    finally:
        heartbeat_events.prepare_overdue_notification = original
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "event_id": str(event_id),
        "heartbeat_id": str(heartbeat_id),
        "owner_name": "Scott",
        "owner_email": "scott@example.com",
        "subject": "Continuity check-in overdue",
        "text_body": "text overdue",
        "html_body": "<p>html overdue</p>",
        "checkin_url": checkin_url,
    }


def test_prepare_heartbeat_event_overdue_endpoint_returns_404() -> None:
    event_id = uuid4()
    session = MagicMock()

    def override_database_session():
        yield session

    app.dependency_overrides[get_db_session] = override_database_session

    from app.api import heartbeat_events

    original = heartbeat_events.prepare_overdue_notification
    heartbeat_events.prepare_overdue_notification = MagicMock(
        side_effect=OverdueNotificationPreparationError("Heartbeat event not found")
    )

    try:
        response = TestClient(app).post(f"/heartbeat-events/{event_id}/prepare-overdue")
    finally:
        heartbeat_events.prepare_overdue_notification = original
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Heartbeat event not found"}


def test_prepare_heartbeat_event_overdue_endpoint_returns_409() -> None:
    event_id = uuid4()
    session = MagicMock()

    def override_database_session():
        yield session

    app.dependency_overrides[get_db_session] = override_database_session

    from app.api import heartbeat_events

    original = heartbeat_events.prepare_overdue_notification
    heartbeat_events.prepare_overdue_notification = MagicMock(
        side_effect=OverdueNotificationPreparationError("Heartbeat event is already delivered")
    )

    try:
        response = TestClient(app).post(f"/heartbeat-events/{event_id}/prepare-overdue")
    finally:
        heartbeat_events.prepare_overdue_notification = original
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json() == {"detail": "Heartbeat event is already delivered"}


def test_prepare_heartbeat_event_escalation_endpoint() -> None:
    heartbeat_id = uuid4()
    event_id = uuid4()
    occurred_at = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)

    heartbeat = Heartbeat(
        id=heartbeat_id,
        owner_name="Scott",
        owner_email="scott@example.com",
        status=HeartbeatStatus.OVERDUE,
        interval_days=30,
        reminder_days=7,
        next_due_at=datetime(2026, 7, 1, tzinfo=UTC),
    )

    event = HeartbeatEvent(
        id=event_id,
        heartbeat_id=heartbeat_id,
        event_type=HeartbeatEventType.ESCALATION_DUE,
        occurred_at=occurred_at,
        created_at=occurred_at,
    )
    event.heartbeat = heartbeat

    notification = Notification(
        channel=NotificationChannel.EMAIL,
        recipient=NotificationRecipient(
            name="Jamie",
            email="jamie@example.com",
        ),
        message=NotificationMessage(
            template_name="escalation_notification",
            template_version=1,
            subject="Continuity escalation notice",
            text_body="text escalation",
            html_body="<p>html escalation</p>",
        ),
    )

    session = MagicMock()

    def override_database_session():
        yield session

    app.dependency_overrides[get_db_session] = override_database_session

    from app.api import heartbeat_events

    original = heartbeat_events.prepare_escalation_notification
    heartbeat_events.prepare_escalation_notification = MagicMock(
        return_value=(
            event,
            notification,
            [
                HeartbeatAttachmentSummary(
                    id=uuid4(),
                    filename="continuity-plan.pdf",
                    content_type="application/pdf",
                    size_bytes=2048,
                )
            ],
        )
    )

    try:
        response = TestClient(app).post(f"/heartbeat-events/{event_id}/prepare-escalation")
    finally:
        heartbeat_events.prepare_escalation_notification = original
        app.dependency_overrides.clear()

    assert response.status_code == 200
    attachment_id = response.json()["attachments"][0]["id"]
    assert response.json() == {
        "event_id": str(event_id),
        "heartbeat_id": str(heartbeat_id),
        "owner_name": "Scott",
        "escalation_contact_name": "Jamie",
        "escalation_contact_email": "jamie@example.com",
        "subject": "Continuity escalation notice",
        "text_body": "text escalation",
        "html_body": "<p>html escalation</p>",
        "attachments": [
            {
                "id": attachment_id,
                "filename": "continuity-plan.pdf",
                "content_type": "application/pdf",
                "size_bytes": 2048,
                "content_url_path": f"/heartbeat-events/attachments/{attachment_id}/content",
            }
        ],
    }


def test_prepare_heartbeat_event_escalation_endpoint_returns_404() -> None:
    event_id = uuid4()
    session = MagicMock()

    def override_database_session():
        yield session

    app.dependency_overrides[get_db_session] = override_database_session

    from app.api import heartbeat_events

    original = heartbeat_events.prepare_escalation_notification
    heartbeat_events.prepare_escalation_notification = MagicMock(
        side_effect=EscalationNotificationPreparationError("Heartbeat event not found")
    )

    try:
        response = TestClient(app).post(f"/heartbeat-events/{event_id}/prepare-escalation")
    finally:
        heartbeat_events.prepare_escalation_notification = original
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Heartbeat event not found"}


def test_prepare_heartbeat_event_escalation_endpoint_returns_409() -> None:
    event_id = uuid4()
    session = MagicMock()

    def override_database_session():
        yield session

    app.dependency_overrides[get_db_session] = override_database_session

    from app.api import heartbeat_events

    original = heartbeat_events.prepare_escalation_notification
    heartbeat_events.prepare_escalation_notification = MagicMock(
        side_effect=EscalationNotificationPreparationError("Heartbeat event is already delivered")
    )

    try:
        response = TestClient(app).post(f"/heartbeat-events/{event_id}/prepare-escalation")
    finally:
        heartbeat_events.prepare_escalation_notification = original
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json() == {"detail": "Heartbeat event is already delivered"}


def test_get_heartbeat_attachment_content_endpoint() -> None:
    attachment_id = uuid4()
    session = MagicMock()

    attachment = MagicMock()
    attachment.content_bytes = b"%PDF-1.7"
    attachment.content_type = "application/pdf"
    attachment.filename = "summary.pdf"
    attachment.size_bytes = 8

    from app.api import heartbeat_events

    original = heartbeat_events.get_attachment_content
    heartbeat_events.get_attachment_content = MagicMock(return_value=attachment)

    def override_database_session():
        yield session

    app.dependency_overrides[get_db_session] = override_database_session

    try:
        response = TestClient(app).get(f"/heartbeat-events/attachments/{attachment_id}/content")
    finally:
        heartbeat_events.get_attachment_content = original
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.content == b"%PDF-1.7"
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-length"] == "8"


def test_get_heartbeat_attachment_content_endpoint_returns_404() -> None:
    attachment_id = uuid4()
    session = MagicMock()

    from app.api import heartbeat_events

    original = heartbeat_events.get_attachment_content
    heartbeat_events.get_attachment_content = MagicMock(return_value=None)

    def override_database_session():
        yield session

    app.dependency_overrides[get_db_session] = override_database_session

    try:
        response = TestClient(app).get(f"/heartbeat-events/attachments/{attachment_id}/content")
    finally:
        heartbeat_events.get_attachment_content = original
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Heartbeat attachment not found"}
