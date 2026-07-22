import asyncio
import logging

from app.persistence.database import SessionLocal
from app.services.heartbeat_service import (
    HeartbeatEvaluationResult,
    evaluate_due_heartbeats,
)

logger = logging.getLogger(__name__)


def run_heartbeat_evaluation() -> HeartbeatEvaluationResult:
    """Run one heartbeat evaluation using a dedicated database session."""
    session = SessionLocal()

    try:
        return evaluate_due_heartbeats(session)
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
