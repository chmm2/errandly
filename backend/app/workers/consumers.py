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
from app.core.graph import ensure_schema
from app.core.redis import redis_client
from app.core.resilience import retry_with_backoff
from app.modules.analytics.models import DailyStat
from app.modules.campus.models import Campus
from app.modules.errands.models import Errand, ErrandEvent
from app.modules.fraud import collusion
from app.modules.fraud import integrity as fraud_integrity
from app.modules.fraud import service as fraud
from app.modules.ledger import service as ledger
from app.modules.notifications import service as notifications
from app.modules.outbox.models import ProcessedEvent
from app.modules.runners import service as runners_service
from app.modules.social.projection import handle_social, refresh_graph_metrics

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

    # Imported here, as elsewhere in this module: the errands service pulls in
    # the router's dependency graph, and importing it at module scope makes the
    # worker import the web app.
    from app.modules.errands import service as errands_service

    eligible, withheld = await fraud.eligible_reimbursement(db, errand_id)
    if eligible == 0 and withheld == 0:
        # No itemised claims. Fall back to what the runner declared at pickup -
        # they were the one at the counter, and the whole point of holding
        # headroom is to cover a real price the estimate got wrong.
        declared = await errands_service.declared_spend(db, errand_id)
        if declared is not None:
            eligible = declared
        else:
            # Nothing declared at all - an errand from before the pickup step
            # required it. Reimburse the estimate rather than nothing.
            #
            # Read from the HOLD, not from this event. The event carries only
            # collect_amount, so a catalogue order - whose spend lives in
            # priced items - reimbursed ZERO and handed the whole basket back
            # to the requester as surplus, runner already out of pocket.
            eligible = await ledger.estimated_spend(db, errand_id)

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
    # Projects friendships (and, later, money flow) into Neo4j. Its own group,
    # so a graph outage stalls only this projection's offsets.
    "social-graph-service": handle_social,
}


async def run_consumer(group: str) -> None:
    handler = HANDLERS[group]
    if group == "social-graph-service":
        await ensure_schema()
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
BROADEN_FANOUT = 10

# (seconds_after_post, tier, max_hops, radius_m). Tier 1 goes out at post time
# from create_errand; these are the escalations.
SOCIAL_TIERS = [
    (45, 2, 4, 3000),      # widen the social circle, same radius
    (90, 3, None, 8000),   # open to strangers, wider radius
]
EXPIRE_AFTER_SECONDS = 600  # 10 min with no runner → give up and apologise


async def broaden_stale_offers() -> None:
    """Escalate offers that nobody has taken yet.

    Two dimensions widen together, on a timer:

        tier 1 (at post)  friends + friends-of-friends, 3km
        tier 2 (+45s)     out to SOCIAL_TIER_2_HOPS  — the wider circle
        tier 3 (+90s)     anyone nearby, 8km          — open to strangers

    The staging is the point. Every candidate in a tier is published to within
    milliseconds of the others, so social preference cannot come from ordering
    a simultaneous broadcast — it has to come from *when* each group is told.
    Giving people you know a 45-second head start is what makes an errand
    likelier to land with them, without ever letting it starve: by 90 seconds
    it is an ordinary open offer, well inside the poster's deadline.
    """

    async with SessionLocal() as db:
        now = datetime.now(UTC)
        stale = list(
            await db.scalars(
                select(Errand).where(
                    Errand.status == "OPEN",
                    Errand.deleted_at.is_(None),
                    Errand.created_at
                    < now - timedelta(seconds=SOCIAL_TIERS[0][0]),
                )
            )
        )
        for errand in stale:
            age = (now - errand.created_at).total_seconds()

            # Which tiers have already gone out for this errand? The audit trail
            # is the state, so a worker restart cannot re-offer a tier.
            done = {
                (row.payload or {}).get("social_tier")
                for row in await db.scalars(
                    select(ErrandEvent).where(
                        ErrandEvent.errand_id == errand.id,
                        ErrandEvent.event_type.in_(("OFFERED", "OFFER_BROADENED")),
                    )
                )
            }
            # An errand posted with no friends nearby already went out open
            # (tier 0); there is nothing left to widen to.
            if 0 in done:
                continue

            for after_s, tier, hops, radius_m in SOCIAL_TIERS:
                if age < after_s or tier in done:
                    continue
                count = await _offer_tier(db, errand, hops, radius_m)
                db.add(
                    ErrandEvent(
                        errand_id=errand.id,
                        actor_id=None,
                        event_type="OFFER_BROADENED",
                        payload={
                            "social_tier": tier,
                            "max_hops": hops,
                            "radius_m": radius_m,
                            "runners": count,
                        },
                    )
                )
                logger.info(
                    "errand %s → tier %d (hops<=%s, %dm): %d runner(s)",
                    errand.id,
                    tier,
                    hops if hops is not None else "any",
                    radius_m,
                    count,
                )
                break  # one tier per sweep, so each gets its own window
        await db.commit()


async def _offer_tier(db, errand, max_hops: int | None, radius_m: int) -> int:
    """Publish an offer for one escalation tier."""
    from app.modules.errands import service as errands_service

    nearby = await runners_service.nearest_available_runners(
        redis_client,
        errand.campus_id,
        lat=float(errand.drop_lat),
        lng=float(errand.drop_lng),
        radius_m=radius_m,
        limit=BROADEN_FANOUT,
        exclude=errand.requester_id,
    )
    # The escalation tiers gate exactly as the first offer does. Skipping it
    # here would leave the whole thing bypassable by waiting: a flagged runner
    # simply collects the broadened offer a tier later instead.
    co_ringed = await fraud_integrity.co_ringed_with(
        db, errand.requester_id, [rid for rid, _ in nearby]
    )
    if co_ringed:
        nearby = [(rid, dist) for rid, dist in nearby if rid not in co_ringed]

    candidate_ids = [rid for rid, _ in nearby]
    scores = await errands_service._safe_scores(errand.requester_id, candidate_ids)
    if max_hops is not None and scores is not None:
        nearby = [(r, d) for r, d in nearby if scores.get(r, {}).get("hops", 99) <= max_hops]
        candidate_ids = [rid for rid, _ in nearby]
    penalties = await fraud_integrity.penalties(db, candidate_ids)
    nearby = errands_service._rank_with_scores(nearby, scores, None, penalties)

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
        payload["connection"] = errands_service._connection_payload(scores, runner_id)
        await redis_client.publish(
            f"{errands_service.OFFER_CHANNEL_PREFIX}{runner_id}", json.dumps(payload)
        )
        count += 1
    return count


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

# 30s sweeps × 20 = graph metrics refresh every ~10 minutes.
METRICS_EVERY_N_SWEEPS = 20


async def sweep_rating_farming() -> None:
    """Look for runners whose reputation is carried by their own circle."""
    async with SessionLocal() as db:
        try:
            raised = await fraud.sweep_rating_farming(db)
            await db.commit()
            if raised:
                logger.info("rating farming: raised %d flag(s)", len(raised))
        except Exception:
            await db.rollback()
            raise


async def sweep_collusion_rings() -> None:
    """Look for closed money cycles among mutual friends and flag their members."""
    async with SessionLocal() as db:
        try:
            raised = await fraud.sweep_collusion_rings(db)
            await db.commit()
            if raised:
                logger.info("collusion: raised %d flag(s)", len(raised))
        except Exception:
            await db.rollback()
            raise


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
                # Same slow clock: unpriced names are a backlog to work
                # through, not an event to react to.
                proposed = await fraud.suggest_item_aliases(db, campus_id)
                await db.commit()
                if proposed:
                    logger.info("proposed %d item alias(es) for review", len(proposed))
            except Exception:
                await db.rollback()
                logger.exception("reference refresh failed for campus %s", campus_id)



async def scheduler() -> None:
    logger.info("scheduler up (interval %ss)", SCHEDULER_INTERVAL)
    last_reference_refresh = 0.0
    nonlocal_tick = [0]
    while True:
        try:
            await broaden_stale_offers()
        except Exception:
            logger.exception("offer broadening sweep failed")
        try:
            await expire_stale_open_errands()
        except Exception:
            logger.exception("errand expiry sweep failed")

        # Graph metrics are cheap on a campus-sized graph but not free, so they
        # run every Nth sweep rather than every one.
        nonlocal_tick[0] = (nonlocal_tick[0] + 1) % METRICS_EVERY_N_SWEEPS
        if nonlocal_tick[0] == 0:
            await refresh_graph_metrics()
            # Circulation reads the FRIEND and PAID edges the refresh above
            # just settled, so it follows it rather than running on its own
            # clock — a ring's closure and its money flow should describe the
            # same instant.
            await collusion.refresh_circulation()
            try:
                await sweep_collusion_rings()
            except Exception:
                logger.exception("collusion ring sweep failed")
            try:
                await sweep_rating_farming()
            except Exception:
                logger.exception("rating farming sweep failed")

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
        run_consumer("social-graph-service"),
        scheduler(),
    )


if __name__ == "__main__":
    asyncio.run(main())
