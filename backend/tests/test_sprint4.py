import uuid

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.resilience import CircuitBreaker, CircuitOpenError, CircuitState
from app.modules.outbox.models import OutboxEvent
from app.workers.consumers import already_processed, handle_analytics, handle_notification

pytestmark = pytest.mark.asyncio(loop_scope="session")

NEAR = {"lat": 12.9692, "lng": 79.1559}


def errand_payload(**overrides) -> dict:
    payload = {
        "category": "FOOD",
        "title": "Sprint4 test errand",
        "pickup_label": "Canteen",
        "drop_lat": NEAR["lat"],
        "drop_lng": NEAR["lng"],
        "reward": 25,
    }
    payload.update(overrides)
    return payload


# ------------------------------------------------------------ outbox atomicity

async def test_outbox_row_written_with_every_transition(client, make_user):
    _, requester = await make_user("Requester")
    _, runner = await make_user("Runner")

    errand = (await client.post("/errands", json=errand_payload(), headers=requester)).json()
    eid = uuid.UUID(errand["id"])
    await client.post(f"/errands/{eid}/accept", headers=runner)
    await client.post(f"/errands/{eid}/pickup", json={"amount_spent": 0}, headers=runner)
    await client.post(f"/errands/{eid}/deliver", headers=runner)
    await client.post(f"/errands/{eid}/complete", headers=requester)

    async with SessionLocal() as db:
        rows = list(
            await db.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.aggregate_id == eid)
                .order_by(OutboxEvent.created_at)
            )
        )
    assert [r.event_type for r in rows] == [
        "ORDER_CREATED", "ORDER_ACCEPTED", "ORDER_PICKED_UP",
        "ORDER_DELIVERED", "ORDER_COMPLETED",
    ]
    # staged for the relay, not yet published by the API process itself
    assert all(r.payload["errand_id"] == str(eid) for r in rows)


# ------------------------------------------------------- consumer idempotency

def _fake_event(event_type: str, campus_id: str, requester_id: str, runner_id: str) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "aggregate_type": "errand",
        "aggregate_id": str(uuid.uuid4()),
        # Fixed HISTORICAL date: the live analytics consumer (running in the
        # workers container against this same dev DB) only writes today's
        # bucket, so this one is ours alone — no race.
        "occurred_at": "2026-01-05T12:00:00+00:00",
        "payload": {
            "errand_id": str(uuid.uuid4()),
            "campus_id": campus_id,
            "requester_id": requester_id,
            "runner_id": runner_id,
            "status": "ACCEPTED",
            "title": "Idempotency test",
            "category": "FOOD",
            "reward": 30.0,
        },
    }


async def test_consumer_replay_is_harmless(client, make_user, campus):
    """The kill-consumer-mid-stream demo: same event delivered twice →
    exactly one notification."""
    requester_id, _ = await make_user("Requester")
    runner_id, _ = await make_user("Runner")
    event = _fake_event("ORDER_ACCEPTED", str(campus), str(requester_id), str(runner_id))

    from app.modules.notifications.models import Notification

    async with SessionLocal() as db:
        assert not await already_processed(db, "notification-service", uuid.UUID(event["event_id"]))
        await handle_notification(db, event)
        await db.commit()

    # redelivery (as after a crash before offset commit)
    async with SessionLocal() as db:
        duplicate = await already_processed(
            db, "notification-service", uuid.UUID(event["event_id"])
        )
        assert duplicate is True  # dedupe gate catches it
        await db.commit()

    async with SessionLocal() as db:
        count = len(
            list(
                await db.scalars(
                    select(Notification).where(
                        Notification.user_id == requester_id,
                        Notification.data["errand_id"].astext
                        == event["payload"]["errand_id"],
                    )
                )
            )
        )
    assert count == 1


async def test_analytics_upsert_counts(client, make_user, campus):
    requester_id, _ = await make_user("Requester")
    runner_id, _ = await make_user("Runner")
    from app.modules.analytics.models import DailyStat

    e1 = _fake_event("ORDER_CREATED", str(campus), str(requester_id), str(runner_id))
    e2 = _fake_event("ORDER_CREATED", str(campus), str(requester_id), str(runner_id))
    async with SessionLocal() as db:
        before = await db.get(DailyStat, (campus, __import__("datetime").date(2026, 1, 5)))
        base = before.orders_created if before else 0
        await handle_analytics(db, e1)
        await handle_analytics(db, e2)
        await db.commit()

    async with SessionLocal() as db:
        stat = await db.get(DailyStat, (campus, __import__("datetime").date(2026, 1, 5)))
    assert stat is not None
    assert stat.orders_created == base + 2


# ------------------------------------------------------------- circuit breaker

async def test_circuit_breaker_opens_and_recovers():
    breaker = CircuitBreaker("test", failure_threshold=2, reset_timeout=0.05)

    async def boom():
        raise RuntimeError("dependency down")

    async def ok():
        return 42

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await breaker.call(boom)
    assert breaker.state is CircuitState.OPEN

    # while open: fail fast without calling through
    with pytest.raises(CircuitOpenError):
        await breaker.call(ok)

    import asyncio

    await asyncio.sleep(0.06)  # reset timeout elapses → half-open probe
    assert await breaker.call(ok) == 42
    assert breaker.state is CircuitState.CLOSED


# ----------------------------------------------------------------- ws contract

async def test_notifications_endpoint_shape(client, make_user):
    _, headers = await make_user("Reader")
    resp = await client.get("/notifications", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["unread"] == 0
