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
    await client.post(f"/errands/{eid}/pickup", headers=runner)
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


# ------------------------------------------------------------------- timetable

async def test_timetable_overlap_rejected_by_db(client, make_user):
    _, headers = await make_user("Student")
    first = await client.post(
        "/timetable",
        json={"day_of_week": 2, "start_minute": 540, "end_minute": 600, "label": "CSE3001"},
        headers=headers,
    )
    assert first.status_code == 201, first.text

    overlap = await client.post(
        "/timetable",
        json={"day_of_week": 2, "start_minute": 570, "end_minute": 630, "label": "Clash"},
        headers=headers,
    )
    assert overlap.status_code == 409
    assert "overlaps" in overlap.json()["detail"]

    adjacent = await client.post(
        "/timetable",
        json={"day_of_week": 2, "start_minute": 600, "end_minute": 660, "label": "CSE3002"},
        headers=headers,
    )
    assert adjacent.status_code == 201, adjacent.text  # touching ≠ overlapping


async def test_cannot_go_online_during_class(client, make_user):
    from app.modules.timetable.service import _campus_now

    _, headers = await make_user("Busy Student")
    day, minute = _campus_now()
    start = max(0, minute - 10)
    end = min(1440, minute + 50)
    resp = await client.post(
        "/timetable",
        json={"day_of_week": day, "start_minute": start, "end_minute": end, "label": "MAT2002"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text

    blocked = await client.post(
        "/runners/me/availability", json={"is_available": True, **NEAR}, headers=headers
    )
    assert blocked.status_code == 409
    assert "MAT2002" in blocked.json()["detail"]


async def test_matching_skips_runner_in_class(client, make_user):
    from app.modules.timetable.service import _campus_now

    _, requester = await make_user("Requester")
    _, free_runner = await make_user("Free Runner")
    _, busy_runner = await make_user("Busy Runner")

    # both go online...
    for h in (free_runner, busy_runner):
        assert (
            await client.post(
                "/runners/me/availability", json={"is_available": True, **NEAR}, headers=h
            )
        ).status_code == 200

    # ...then class starts for one of them (slot added after going online —
    # the matching-time filter must still catch it)
    day, minute = _campus_now()
    await client.post(
        "/timetable",
        json={
            "day_of_week": day,
            "start_minute": max(0, minute - 5),
            "end_minute": min(1440, minute + 55),
            "label": "PHY1001",
        },
        headers=busy_runner,
    )

    errand = (await client.post("/errands", json=errand_payload(), headers=requester)).json()
    events = (await client.get(f"/errands/{errand['id']}/events", headers=requester)).json()
    offered = next(e for e in events if e["event_type"] == "OFFERED")
    assert offered["payload"]["runners"] == 1  # only the free runner


# ----------------------------------------------------------------- ws contract

async def test_notifications_endpoint_shape(client, make_user):
    _, headers = await make_user("Reader")
    resp = await client.get("/notifications", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["unread"] == 0
