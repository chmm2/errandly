"""Kafka consumers + periodic jobs, run as one worker process.

- notification-service and analytics-service are separate consumer GROUPS
  over the same topic: each group gets every event once (pub/sub fan-out);
  replicas within a group would compete for partitions (competing consumers).
- Both are idempotent via processed_events (insert-or-skip on PK) — Kafka
  is at-least-once, so replays MUST be harmless. Kill this process
  mid-stream, restart it, and nothing duplicates: that's the demo.
- The scheduler loop handles timetable enforcement (auto-block runners when
  class starts) and offer broadening for errands nobody accepted.

Run: python -m app.workers.consumers
"""

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

from aiokafka import AIOKafkaConsumer
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

import app.models  # noqa: F401 — register ALL mappers (workers skip the API's import graph)
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.redis import redis_client
from app.core.resilience import retry_with_backoff
from app.modules.analytics.models import DailyStat
from app.modules.errands.models import Errand, ErrandEvent
from app.modules.ledger.models import LedgerEntry
from app.modules.notifications import service as notifications
from app.modules.outbox.models import ProcessedEvent
from app.modules.runners import service as runners_service
from app.modules.runners.models import RunnerProfile
from app.modules.timetable import service as timetable

logging.basicConfig(level=logging.INFO, format="%(asctime)s worker %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def already_processed(db: AsyncSession, consumer: str, event_id: uuid.UUID) -> bool:
    """Idempotency gate: try to claim the event id; a conflict means a
    previous (possibly crashed-mid-work) run already handled it."""
    result = await db.execute(
        pg_insert(ProcessedEvent)
        .values(consumer=consumer, event_id=event_id)
        .on_conflict_do_nothing()
    )
    return result.rowcount == 0


# ---------------------------------------------------------------- notification

NOTIFY_TEMPLATES = {
    "ORDER_ACCEPTED": ("requester_id", "Runner assigned 🤝", "{title} — a runner is on it."),
    "ORDER_PICKED_UP": ("requester_id", "Picked up 📦", "{title} is on its way to you."),
    "ORDER_DELIVERED": ("requester_id", "Delivered 🎉", "{title} has arrived — confirm handoff."),
    "ORDER_COMPLETED": ("runner_id", "Run completed ✅", "{title} confirmed by the requester."),
    "ORDER_CANCELLED": ("runner_id", "Errand cancelled 🚫", "{title} was cancelled."),
}


async def handle_notification(db: AsyncSession, event: dict) -> None:
    template = NOTIFY_TEMPLATES.get(event["event_type"])
    if template is None:
        return
    target_field, title, body_tpl = template
    target = event["payload"].get(target_field)
    if not target:
        return
    await notifications.create_and_push(
        db,
        redis_client,
        uuid.UUID(target),
        event["event_type"],
        title,
        body_tpl.format(title=event["payload"]["title"]),
        {"errand_id": event["payload"]["errand_id"]},
    )


# ------------------------------------------------------------------- analytics

STAT_COLUMNS = {
    "ORDER_CREATED": "orders_created",
    "ORDER_COMPLETED": "orders_completed",
    "ORDER_CANCELLED": "orders_cancelled",
}


async def handle_analytics(db: AsyncSession, event: dict) -> None:
    column = STAT_COLUMNS.get(event["event_type"])
    if column is None:
        return
    day = datetime.fromisoformat(event["occurred_at"]).date()
    values = {
        "campus_id": uuid.UUID(event["payload"]["campus_id"]),
        "stat_date": day,
        column: 1,
    }
    if event["event_type"] == "ORDER_COMPLETED":
        values["reward_total"] = event["payload"]["reward"]
    stmt = pg_insert(DailyStat).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["campus_id", "stat_date"],
        set_={
            column: getattr(DailyStat, column) + 1,
            **(
                {"reward_total": DailyStat.reward_total + values["reward_total"]}
                if "reward_total" in values
                else {}
            ),
        },
    )
    await db.execute(stmt)


# ------------------------------------------------------------------ settlement

async def handle_settlement(db: AsyncSession, event: dict) -> None:
    """Money moves ONLY here, only on ORDER_COMPLETED, and only once — the
    processed_events gate makes a Kafka redelivery pay nobody twice."""
    if event["event_type"] != "ORDER_COMPLETED":
        return
    payload = event["payload"]
    if not payload.get("runner_id"):
        return
    runner_id = uuid.UUID(payload["runner_id"])
    errand_id = uuid.UUID(payload["errand_id"])
    db.add(
        LedgerEntry(
            user_id=runner_id, errand_id=errand_id,
            entry_type="REWARD", amount=payload["reward"],
        )
    )
    if payload.get("collect_amount", 0) > 0:
        db.add(
            LedgerEntry(
                user_id=runner_id, errand_id=errand_id,
                entry_type="REIMBURSEMENT", amount=payload["collect_amount"],
            )
        )
    await notifications.create_and_push(
        db,
        redis_client,
        runner_id,
        "SETTLEMENT",
        "Paid out 💰",
        f"₹{payload['reward']:.0f} reward"
        + (
            f" + ₹{payload['collect_amount']:.0f} reimbursed"
            if payload.get("collect_amount", 0) > 0
            else ""
        )
        + f" for {payload['title']}.",
        {"errand_id": payload["errand_id"]},
    )


# ------------------------------------------------------------------- consumers

HANDLERS = {
    "notification-service": handle_notification,
    "analytics-service": handle_analytics,
    "settlement-service": handle_settlement,
}


async def run_consumer(group: str) -> None:
    handler = HANDLERS[group]
    consumer = AIOKafkaConsumer(
        settings.kafka_orders_topic,
        bootstrap_servers=settings.kafka_bootstrap,
        group_id=group,
        enable_auto_commit=True,
        auto_offset_reset="earliest",
    )
    await retry_with_backoff(consumer.start, attempts=8, base_delay=1, max_delay=10)
    logger.info("%s consuming %s", group, settings.kafka_orders_topic)
    try:
        async for message in consumer:
            try:
                event = json.loads(message.value)
                async with SessionLocal() as db:
                    if await already_processed(db, group, uuid.UUID(event["event_id"])):
                        await db.commit()  # keep the dedupe claim
                        logger.info("%s skipped duplicate %s", group, event["event_id"])
                        continue
                    await handler(db, event)
                    await db.commit()
                logger.info("%s handled %s %s", group, event["event_type"], event["event_id"])
            except Exception:
                logger.exception("%s failed on offset %s", group, message.offset)
    finally:
        await consumer.stop()


# ------------------------------------------------------------------- scheduler

ENFORCER_INTERVAL = 30
BROADEN_AFTER_SECONDS = 60
BROADEN_RADIUS_M = 8000
BROADEN_FANOUT = 10
EXPIRE_AFTER_SECONDS = 600  # 10 min with no runner → give up and apologise


async def enforce_timetable() -> None:
    """Auto-block: flip runners offline the moment their class starts."""
    async with SessionLocal() as db:
        available = list(
            await db.scalars(select(RunnerProfile).where(RunnerProfile.is_available.is_(True)))
        )
        blocked = await timetable.in_class_user_ids(db, [p.user_id for p in available])
        for profile in available:
            if profile.user_id not in blocked:
                continue
            profile.is_available = False
            await redis_client.zrem(
                runners_service.geo_key(profile.campus_id), str(profile.user_id)
            )
            await notifications.create_and_push(
                db,
                redis_client,
                profile.user_id,
                "TIMETABLE_BLOCK",
                "Class time — runner mode off 📚",
                "Your timetable says you're in class, so we took you offline.",
            )
            logger.info("enforcer: blocked runner %s (in class)", profile.user_id)
        await db.commit()


async def broaden_stale_offers() -> None:
    """Offer escalation: errands still OPEN after a while get re-offered to
    a wider radius (the accept/timeout → broaden retry loop)."""
    from app.modules.errands import service as errands_service  # avoid import cycle

    async with SessionLocal() as db:
        cutoff = datetime.now(UTC).timestamp() - BROADEN_AFTER_SECONDS
        stale = list(
            await db.scalars(
                select(Errand).where(
                    Errand.status == "OPEN",
                    Errand.deleted_at.is_(None),
                    Errand.created_at < datetime.fromtimestamp(cutoff, tz=UTC),
                )
            )
        )
        for errand in stale:
            # broaden at most once — check the audit trail
            prior = await db.scalar(
                select(ErrandEvent.id).where(
                    ErrandEvent.errand_id == errand.id,
                    ErrandEvent.event_type == "OFFER_BROADENED",
                )
            )
            if prior:
                continue
            nearby = await runners_service.nearest_available_runners(
                redis_client,
                errand.campus_id,
                lat=float(errand.drop_lat),
                lng=float(errand.drop_lng),
                radius_m=BROADEN_RADIUS_M,
                limit=BROADEN_FANOUT,
                exclude=errand.requester_id,
            )
            in_class = await timetable.in_class_user_ids(db, [r for r, _ in nearby])
            payload = {
                "type": "offer",
                "errand_id": str(errand.id),
                "title": errand.title,
                "category": errand.category,
                "reward": float(errand.reward),
            }
            count = 0
            for runner_id, distance_m in nearby:
                if runner_id in in_class:
                    continue
                payload["distance_m"] = round(distance_m)
                await redis_client.publish(
                    f"{errands_service.OFFER_CHANNEL_PREFIX}{runner_id}", json.dumps(payload)
                )
                count += 1
            db.add(
                ErrandEvent(
                    errand_id=errand.id,
                    actor_id=None,
                    event_type="OFFER_BROADENED",
                    payload={"radius_m": BROADEN_RADIUS_M, "runners": count},
                )
            )
            logger.info("broadened offer for %s to %d runner(s)", errand.id, count)
        await db.commit()


async def expire_stale_open_errands() -> None:
    """Past the poster's chosen deadline with no runner → OPEN goes to EXPIRED
    and the requester is told. Row is locked so this never races an accept that
    lands in the same instant (SKIP LOCKED = don't fight an in-flight accept)."""
    from sqlalchemy import func

    from app.modules.errands import service as errands_service  # avoid import cycle

    async with SessionLocal() as db:
        now = datetime.now(UTC)
        # Fall back to the legacy fixed window for any row without a deadline.
        deadline = func.coalesce(
            Errand.expires_at,
            Errand.created_at + timedelta(seconds=EXPIRE_AFTER_SECONDS),
        )
        stale = list(
            await db.scalars(
                select(Errand)
                .where(
                    Errand.status == "OPEN",
                    Errand.deleted_at.is_(None),
                    deadline < now,
                )
                .with_for_update(skip_locked=True)
            )
        )
        for errand in stale:
            errands_service.expire_errand(db, errand)
            await notifications.create_and_push(
                db, redis_client, errand.requester_id,
                "ERRAND_EXPIRED", "No runner found 😔",
                f"Nobody picked up “{errand.title}” in time. "
                "You can post it again, maybe with a higher reward.",
                {"errand_id": str(errand.id)},
            )
            logger.info("expired errand %s (no runner in %ds)", errand.id, EXPIRE_AFTER_SECONDS)
        await db.commit()
        for errand in stale:
            await errands_service.publish_status(redis_client, errand)


async def scheduler() -> None:
    logger.info("scheduler up (interval %ss)", ENFORCER_INTERVAL)
    while True:
        try:
            await enforce_timetable()
        except Exception:
            logger.exception("timetable enforcer sweep failed")
        try:
            await broaden_stale_offers()
        except Exception:
            logger.exception("offer broadening sweep failed")
        try:
            await expire_stale_open_errands()
        except Exception:
            logger.exception("errand expiry sweep failed")
        await asyncio.sleep(ENFORCER_INTERVAL)


async def main() -> None:
    await asyncio.gather(
        run_consumer("notification-service"),
        run_consumer("analytics-service"),
        run_consumer("settlement-service"),
        scheduler(),
    )


if __name__ == "__main__":
    asyncio.run(main())
