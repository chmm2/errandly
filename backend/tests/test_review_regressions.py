"""Two scheduler and detector faults found by the paper's first evaluation.

1. An errand whose first offer went out unrestricted (tier 0, no friend nearby)
   was skipped by the escalation sweep and never widened. It now gets the
   radius widening of the last tier, and only that one.
2. The ring search returned at most 50 rings, so on a busy campus the rest
   stayed hidden until the larger ones aged out.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.core.database import SessionLocal
from app.modules.errands.models import Errand, ErrandEvent
from app.modules.fraud import collusion
from app.workers.consumers import SOCIAL_TIERS, broaden_stale_offers
from tests.test_collusion import _make_ring, _wipe_graph
from tests.test_offer_log import ERRAND_PAYLOAD, _available

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _tiers_sent(errand_id):
    async with SessionLocal() as db:
        rows = await db.scalars(
            select(ErrandEvent).where(
                ErrandEvent.errand_id == errand_id,
                ErrandEvent.event_type.in_(("OFFERED", "OFFER_BROADENED")),
            )
        )
        return [(r.event_type, (r.payload or {}).get("social_tier")) for r in rows]


async def test_an_errand_that_went_out_unrestricted_is_still_widened(client, make_user):
    _, requester = await make_user("Requester")
    _, runner = await make_user("Stranger Runner")
    await _available(client, runner)

    created = await client.post("/errands", json=ERRAND_PAYLOAD, headers=requester)
    assert created.status_code == 201, created.text
    errand_id = uuid.UUID(created.json()["id"])
    assert ("OFFERED", 0) in await _tiers_sent(errand_id), "no friend nearby: tier 0"

    # Age it past the last tier's threshold, then run the sweep.
    last_after = max(after for after, *_ in SOCIAL_TIERS)
    async with SessionLocal() as db:
        await db.execute(
            update(Errand)
            .where(Errand.id == errand_id)
            .values(created_at=datetime.now(UTC) - timedelta(seconds=last_after + 5))
        )
        await db.commit()
    await broaden_stale_offers()

    broadened = [t for kind, t in await _tiers_sent(errand_id) if kind == "OFFER_BROADENED"]
    open_tiers = [tier for _, tier, hops, _ in SOCIAL_TIERS if hops is None]
    assert broadened == open_tiers, "widened by radius only; no social tier re-sent"


async def test_the_ring_search_returns_every_ring():
    await _wipe_graph()
    for _ in range(55):
        await _make_ring([str(uuid.uuid4()) for _ in range(3)], laps=2, amount=200)
    rings = await collusion.find_rings()
    assert len(rings) == 55
