import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.outbox.models import OutboxEvent


def emit(
    db: AsyncSession,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    event_type: str,
    payload: dict,
) -> None:
    """Stage a domain event in the outbox. No commit here — it rides the
    caller's transaction, which is the entire point of the pattern."""
    db.add(
        OutboxEvent(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
        )
    )
