"""Outbox relay: the second half of the transactional-outbox pattern.

Polls unpublished outbox rows (FOR UPDATE SKIP LOCKED — several relay
replicas could run side by side without double-claiming) and publishes them
to Kafka. Marks rows published only after the broker acks, so a crash
between publish and mark re-sends the event: at-least-once delivery, which
is exactly why consumers dedupe.

Run: python -m app.workers.relay
"""

import asyncio
import json
import logging
from datetime import UTC, datetime

from aiokafka import AIOKafkaProducer
from sqlalchemy import select

import app.models  # noqa: F401 — register ALL mappers (workers skip the API's import graph)
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.resilience import CircuitBreaker, CircuitOpenError, retry_with_backoff
from app.modules.outbox.models import OutboxEvent

logging.basicConfig(level=logging.INFO, format="%(asctime)s relay %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

POLL_INTERVAL = 1.0
BATCH_SIZE = 50

kafka_breaker = CircuitBreaker("kafka-producer", failure_threshold=5, reset_timeout=15)


async def publish_batch(producer: AIOKafkaProducer) -> int:
    """Claim a batch of unpublished rows and push them to Kafka."""
    async with SessionLocal() as db:
        rows = list(
            await db.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.published_at.is_(None))
                .order_by(OutboxEvent.created_at)
                .limit(BATCH_SIZE)
                .with_for_update(skip_locked=True)
            )
        )
        if not rows:
            return 0

        for event in rows:
            message = json.dumps(
                {
                    "event_id": str(event.id),
                    "event_type": event.event_type,
                    "aggregate_type": event.aggregate_type,
                    "aggregate_id": str(event.aggregate_id),
                    "payload": event.payload,
                    "occurred_at": event.created_at.isoformat(),
                }
            ).encode()

            async def send(msg=message, key=str(event.aggregate_id).encode()):
                # Key by aggregate id → all events of one errand land in one
                # partition → consumers see them in order.
                await producer.send_and_wait(settings.kafka_orders_topic, msg, key=key)

            event.attempts += 1
            await kafka_breaker.call(
                lambda s=send: retry_with_backoff(s, attempts=3, base_delay=0.3)
            )
            event.published_at = datetime.now(UTC)

        await db.commit()
        logger.info("published %d event(s)", len(rows))
        return len(rows)


async def main() -> None:
    producer = AIOKafkaProducer(bootstrap_servers=settings.kafka_bootstrap)
    await retry_with_backoff(producer.start, attempts=8, base_delay=1, max_delay=10)
    logger.info("relay up — bootstrap %s, topic %s",
                settings.kafka_bootstrap, settings.kafka_orders_topic)
    try:
        while True:
            try:
                published = await publish_batch(producer)
            except CircuitOpenError:
                logger.warning("kafka breaker open — backing off")
                published = 0
            except Exception:
                logger.exception("publish batch failed")
                published = 0
            if published < BATCH_SIZE:
                await asyncio.sleep(POLL_INTERVAL)
    finally:
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(main())
