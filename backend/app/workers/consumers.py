"""Kafka consumers + periodic jobs, run as one worker process.

- notification-service and analytics-service are separate consumer GROUPS
  over the same topic: each group gets every event once (pub/sub fan-out);
  replicas within a group would compete for partitions (competing consumers).
- Both are idempotent via processed_events (insert-or-skip on PK) — Kafka
  is at-least-once, so replays MUST be harmless. Kill this process
  mid-stream, restart it, and nothing duplicates: that's the demo.
- The scheduler loop handles offer broadening for errands nobody accepted and
  expiry of errands past their deadline.

Run: python -m app.workers.consumers
"""

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

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
from app.modules.campus.models import Campus
from app.modules.errands.models import Errand, ErrandEvent
from app.modules.fraud import service as fraud
from app.modules.ledger import service as ledger
from app.modules.notifications import service as notifications
from app.modules.outbox.models import ProcessedEvent
from app.modules.runners import service as runners_service

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
    """Money moves ONLY here, only on ORDER_COMPLETED, and only once.

    Two gates make a Kafka redelivery harmless: processed_events at the consumer
    level, and a unique (errand, user, entry_type) in the ledger itself. Either
    alone would do; both means a bug in one is not a payout bug.

    Reimbursement is drawn from the runner's JUDGED claims, never from the
    amount they asked for. A claim flagged as above the campus reference pays
    out at the reference and the excess stays in escrow for admin review — so
    inflating a price delays money rather than producing it.
    """
    if event["event_type"] != "ORDER_COMPLETED":
        return
    payload = event["payload"]
    if not payload.get("runner_id"):
        return
    runner_id = uuid.UUID(payload["runner_id"])
    errand_id = uuid.UUID(payload["errand_id"])
    reward = Decimal(str(payload["reward"]))

    eligible, withheld = await fraud.eligible_reimbursement(db, errand_id)
    if eligible == 0 and withheld == 0:
        # No claims filed (a non-catalog run, or a runner who skipped the
        # step): fall back to the amount the requester agreed to up front.
        eligible = Decimal(str(payload.get("collect_amount", 0) or 0))

    try:
        await ledger.release_hold(
            db,
            errand_id=errand_id,
            runner_id=runner_id,
            reward=reward,
            reimbursement=eligible,
            withheld=withheld,
            memo=f"Delivery reward for {payload['title']}",
        )
    except ledger.LedgerError:
        logger.exception("settlement failed for errand %s", errand_id)
        raise

    body = f"₹{reward:.0f} reward"
    if eligible > 0:
        body += f" + ₹{eligible:.0f} reimbursed"
    body += f" for {payload['title']}."
    if withheld > 0:
        body += (
            f" ₹{withheld:.0f} is held pending review — your reported price was "
            "above the campus reference."
        )

    await notifications.create_and_push(
        db,
        redis_client,
        runner_id,
        "SETTLEMENT",
        "Paid out 💰" if withheld == 0 else "Paid out — part held",
        body,
        {"errand_id": payload["errand_id"], "withheld": float(withheld)},
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

SCHEDULER_INTERVAL = 30
BROADEN_AFTER_SECONDS = 60
BROADEN_RADIUS_M = 8000
BROADEN_FANOUT = 10
EXPIRE_AFTER_SECONDS = 600  # 10 min with no runner → give up and apologise


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
            payload = {
                "type": "offer",
                "errand_id": str(errand.id),
                "title": errand.title,
                "category": errand.category,
                "reward": float(errand.reward),
            }
            count = 0
            for runner_id, distance_m in nearby:
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


# Reference prices move on the order of days, not seconds — re-estimating
# every enforcer tick would be wasted work. Once an hour is plenty.
REFERENCE_REFRESH_INTERVAL = 3600


async def refresh_reference_prices() -> None:
    """Re-estimate every campus's reference prices from recent honest claims.

    The estimator only ever moves a price INSIDE its admin-approved band; when
    the evidence points outside, it files a proposal instead. So this job can
    run unattended without any risk of it widening its own bounds.
    """
    async with SessionLocal() as db:
        campus_ids = list(await db.scalars(select(Campus.id)))
        for campus_id in campus_ids:
            try:
                count = await fraud.refresh_all_references(db, campus_id)
                await db.commit()
                logger.info("refreshed %d reference price(s) for campus %s", count, campus_id)
            except Exception:
                await db.rollback()
                logger.exception("reference refresh failed for campus %s", campus_id)


async def scheduler() -> None:
    logger.info("scheduler up (interval %ss)", SCHEDULER_INTERVAL)
    last_reference_refresh = 0.0
    while True:
        try:
            await broaden_stale_offers()
        except Exception:
            logger.exception("offer broadening sweep failed")
        try:
            await expire_stale_open_errands()
        except Exception:
            logger.exception("errand expiry sweep failed")

        now = asyncio.get_running_loop().time()
        if now - last_reference_refresh >= REFERENCE_REFRESH_INTERVAL:
            last_reference_refresh = now
            try:
                await refresh_reference_prices()
            except Exception:
                logger.exception("reference price refresh failed")

        await asyncio.sleep(SCHEDULER_INTERVAL)


async def main() -> None:
    await asyncio.gather(
        run_consumer("notification-service"),
        run_consumer("analytics-service"),
        run_consumer("settlement-service"),
        scheduler(),
    )


if __name__ == "__main__":
    asyncio.run(main())
