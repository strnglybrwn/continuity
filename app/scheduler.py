import asyncio
import logging

from app.config import settings
from app.persistence.database import create_db_session as SessionLocal
from app.services.heartbeat_event_service import get_pending_heartbeat_event_metrics
from app.services.heartbeat_service import (
    HeartbeatEvaluationResult,
    evaluate_due_heartbeats,
)

logger = logging.getLogger(__name__)


def run_heartbeat_evaluation() -> HeartbeatEvaluationResult:
    """Run one heartbeat evaluation using a dedicated database session."""
    session = SessionLocal()

    try:
        result = evaluate_due_heartbeats(session)

        metrics = get_pending_heartbeat_event_metrics(
            session,
            stale_after_seconds=settings.heartbeat_pending_alert_seconds,
        )

        if metrics.stale_pending_alert:
            logger.warning(
                "Stale pending reminder events detected: stale=%d threshold_seconds=%d oldest_age_seconds=%s",
                metrics.stale_reminder_due_total,
                settings.heartbeat_pending_alert_seconds,
                metrics.oldest_pending_age_seconds,
            )

        return result
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


async def run_heartbeat_scheduler(
    interval_seconds: int,
) -> None:
    """Continuously evaluate heartbeat status at the configured interval."""
    while True:
        try:
            result = await asyncio.to_thread(
                run_heartbeat_evaluation,
            )

            logger.info(
                "Heartbeat evaluation completed: evaluated=%d changed=%d",
                result.evaluated,
                result.changed,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Heartbeat evaluation failed")

        await asyncio.sleep(interval_seconds)
