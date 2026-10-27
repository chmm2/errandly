"""Give the admin console realistic cases to review.

A fresh database has no history, so a demo of the fraud console has nothing to
show behind a flag. This builds two months of believable campus activity and
then lets the REAL detectors find what is in it:

  * Xavier, Yash and Zoya run vague errands for each other and rate each other
    five stars - a collusion ring, plus a rating-farming case for Zoya.
  * Asha, Bala and Chetan are honest friends who help each other a little and
    work with plenty of other people - they must NOT be flagged.
  * Ravi reports prices that always land just under the limit.
  * Everyone else reports normal Chicken Puff prices at Darling Canteen, which
    becomes the price history a reviewer compares a new claim against.

Nothing is flagged by hand. Completed errands go through the same Neo4j
projection the Kafka consumer uses, prices go through the same judge, and the
flags come from the same sweeps the scheduler runs.

Run:  docker compose exec backend python -m app.demo_cases
Safe to run twice: it stops if the demo students already exist.

All demo students sign in with password123.
"""

import asyncio
import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from geoalchemy2 import WKTElement
from sqlalchemy import select

import app.models  # noqa: F401 - register every mapper
from app.core.database import SessionLocal
from app.modules.auth.models import User
from app.modules.campus.models import Campus
from app.modules.errands.models import Errand, Rating
from app.modules.fraud import service as fraud
from app.modules.fraud.models import RunnerPriceClaim
from app.modules.fraud.normalize import normalize
from app.modules.social.models import Friendship
from app.modules.social.projection import handle_social, refresh_graph_metrics
from app.seed import DEFAULT_CAMPUS, _ensure_user, seed

STUDENTS = {
    "xavier": ("23BCE0101", "Xavier Thomas"),
    "yash": ("23BCE0102", "Yash Mehta"),
    "zoya": ("23BCE0103", "Zoya Khan"),
    "asha": ("23BCE0111", "Asha Nair"),
    "bala": ("23BCE0112", "Bala Krishnan"),
    "chetan": ("23BCE0113", "Chetan Rao"),
    "ravi": ("23BCE0121", "Ravi Kumar"),
    "meera": ("23BCE0122", "Meera Iyer"),
    "dev": ("23BCE0123", "Dev Sharma"),
    "kiran": ("23BCE0124", "Kiran Das"),
    "nisha": ("23BCE0125", "Nisha Pillai"),
}

VAGUE = ["misc", "item", "stuff from shop", "misc ₹200", "things", "item pickup"]
NORMAL = [
    ("FOOD", "Food Court", "Samosas from the food court"),
    ("FOOD", "Night Canteen", "Maggi from the night canteen"),
    ("STATIONERY", "Technology Tower", "Printout from Technology Tower"),
    ("PARCEL", "Main Gate", "Parcel from the main gate"),
    ("PHARMACY", "Health Centre", "Medicines from the health centre"),
    ("GROCERY", "Campus Store", "Notebook and pens"),
    ("FOOD", "Darling Canteen", "Cold coffee from Darling"),
]

rng = random.Random(7)
NOW = datetime.now(UTC)


def _at(days_ago: float) -> datetime:
    return NOW - timedelta(days=days_ago, hours=rng.randint(0, 9), minutes=rng.randint(0, 59))


async def _friends(db, a: User, b: User, days_ago: int) -> None:
    lo, hi = sorted((a.id, b.id))
    when = NOW - timedelta(days=days_ago)
    db.add(
        Friendship(
            user_lo=lo,
            user_hi=hi,
            requested_by=a.id,
            status="ACCEPTED",
            created_at=when,
            responded_at=when,
        )
    )
    await handle_social(
        db,
        {
            "event_type": "FriendshipAccepted",
            "payload": {"user_a": str(a.id), "user_b": str(b.id), "at": when.isoformat()},
        },
    )


async def _errand(
    db,
    campus_id,
    req: User,
    run: User,
    *,
    title,
    category="FOOD",
    pickup="Food Court",
    reward=30,
    days_ago=10.0,
    stars=None,
    comment=None,
) -> Errand:
    """A completed errand, projected into the graph exactly as settlement would."""
    t = _at(days_ago)
    done = t + timedelta(minutes=rng.randint(25, 50))
    lat, lng = 12.9692 + rng.uniform(-0.004, 0.004), 79.1559 + rng.uniform(-0.004, 0.004)
    e = Errand(
        campus_id=campus_id,
        requester_id=req.id,
        runner_id=run.id,
        category=category,
        title=title,
        pickup_label=pickup,
        drop_point=WKTElement(f"POINT({lng} {lat})", srid=4326),
        drop_lat=lat,
        drop_lng=lng,
        drop_label="Men's Hostel Block A",
        reward=reward,
        status="COMPLETED",
        created_at=t,
        updated_at=done,
        accepted_at=t + timedelta(minutes=2),
        delivered_at=done - timedelta(minutes=3),
        completed_at=done,
    )
    db.add(e)
    await db.flush()
    await handle_social(
        db,
        {
            "event_type": "ORDER_COMPLETED",
            "payload": {
                "requester_id": str(req.id),
                "runner_id": str(run.id),
                "errand_id": str(e.id),
                "reward": reward,
                "collect_amount": 0,
                "at": done.isoformat(),
            },
        },
    )
    if stars:
        db.add(
            Rating(
                errand_id=e.id,
                rater_id=req.id,
                ratee_id=run.id,
                stars=stars,
                comment=comment,
                created_at=done + timedelta(minutes=5),
            )
        )
    return e


async def _claim(db, errand: Errand, runner: User, name: str, unit: float, qty: int = 2) -> None:
    """A price report, judged by the same function the claim endpoint uses."""
    key = normalize(name)
    ref = await fraud.get_reference(db, errand.campus_id, key)
    j = fraud.judge(Decimal(str(unit)), qty, ref)
    db.add(
        RunnerPriceClaim(
            errand_id=errand.id,
            runner_id=runner.id,
            campus_id=errand.campus_id,
            raw_name=name,
            item_key=key,
            store_key=fraud.store_key_for(errand),
            claimed_unit_price=Decimal(str(unit)),
            quantity=qty,
            reference_snapshot=ref.reference_price if ref else None,
            threshold_snapshot=j.threshold,
            delta_pct=j.delta_pct,
            delta_abs=j.delta_abs,
            verdict=j.verdict,
            eligible_amount=j.eligible,
            created_at=errand.completed_at - timedelta(minutes=10),
        )
    )


async def build() -> None:
    await seed()
    async with SessionLocal() as db:
        campus = await db.scalar(select(Campus).where(Campus.name == DEFAULT_CAMPUS))
        if await db.scalar(select(User).where(User.email == "xavier.thomas@vitstudent.ac.in")):
            print("Demo cases already exist. Nothing to do.")
            return

        u: dict[str, User] = {}
        for key, (sid, name) in STUDENTS.items():
            email = name.lower().replace(" ", ".") + "@vitstudent.ac.in"
            u[key] = await _ensure_user(db, campus.id, email=email, name=name, student_id=sid)
        u["priya"] = await db.scalar(
            select(User).where(User.email == "priya.runner@vitstudent.ac.in")
        )
        u["test"] = await db.scalar(
            select(User).where(User.email == "test.student@vitstudent.ac.in")
        )
        cid = campus.id

        # Friendships. Both trios are fully connected, so the graph alone
        # cannot tell the honest group from the ring.
        for a, b in [
            ("xavier", "yash"),
            ("yash", "zoya"),
            ("xavier", "zoya"),
            ("asha", "bala"),
            ("bala", "chetan"),
            ("asha", "chetan"),
            ("chetan", "meera"),
            ("zoya", "dev"),
            ("priya", "test"),
        ]:
            await _friends(db, u[a], u[b], days_ago=rng.randint(70, 120))

        # The ring: money round and round, vague titles, five stars every time.
        for req, run, n in [("xavier", "yash", 9), ("yash", "zoya", 8), ("zoya", "xavier", 9)]:
            for i in range(n):
                await _errand(
                    db,
                    cid,
                    u[req],
                    u[run],
                    title=rng.choice(VAGUE),
                    reward=rng.choice([90, 100, 110]),
                    days_ago=55 - i * 6 + rng.random(),
                    stars=5,
                )
        # A little outside work, so they don't look like they never meet anyone.
        for req, run, stars in [
            ("ravi", "zoya", 3),
            ("kiran", "zoya", 3),
            ("nisha", "zoya", 3),
            ("ravi", "xavier", 4),
            ("kiran", "yash", 4),
        ]:
            cat, pickup, title = rng.choice(NORMAL)
            await _errand(
                db,
                cid,
                u[req],
                u[run],
                title=title,
                category=cat,
                pickup=pickup,
                reward=30,
                days_ago=rng.uniform(3, 50),
                stars=stars,
                comment="Took a while." if stars == 3 else None,
            )

        # The honest group: a few small favours inside, lots of work outside.
        for req, run, n in [("asha", "bala", 3), ("bala", "chetan", 2), ("chetan", "asha", 2)]:
            for _ in range(n):
                cat, pickup, title = rng.choice(NORMAL)
                await _errand(
                    db,
                    cid,
                    u[req],
                    u[run],
                    title=title,
                    category=cat,
                    pickup=pickup,
                    reward=rng.choice([20, 25, 30]),
                    days_ago=rng.uniform(2, 58),
                    stars=5,
                )
        others = ["ravi", "meera", "dev", "kiran", "nisha", "test", "priya"]
        for run in ["asha", "bala", "chetan"]:
            for _ in range(5):
                cat, pickup, title = rng.choice(NORMAL)
                await _errand(
                    db,
                    cid,
                    u[rng.choice(others)],
                    u[run],
                    title=title,
                    category=cat,
                    pickup=pickup,
                    reward=rng.choice([20, 25, 30, 40]),
                    days_ago=rng.uniform(1, 58),
                    stars=rng.choice([4, 5, 5]),
                )

        # Normal Chicken Puff prices at Darling Canteen: the history a reviewer
        # compares a new claim against.
        runners = ["asha", "bala", "chetan", "meera", "dev", "kiran", "nisha", "priya"]
        requesters = ["test", "ravi", "meera", "dev", "nisha", "kiran"]
        for i, price in enumerate([20, 20, 22, 20, 18, 21, 20, 22, 20, 19, 20, 23, 20, 21]):
            run = runners[i % len(runners)]
            req = next(r for r in requesters if r != run)
            e = await _errand(
                db,
                cid,
                u[req],
                u[run],
                title="Chicken puffs from Darling",
                category="GROCERY",
                pickup="Darling Canteen",
                reward=25,
                days_ago=60 - i * 4 + rng.random(),
                stars=rng.choice([4, 5]),
            )
            await _claim(db, e, u[run], "Chicken Puff", price)

        # Ravi: every price just under the limit. Legal each time, a habit overall.
        for i, (name, over) in enumerate(
            [
                ("Chicken Puff", 6.5),
                ("Samosa", 5),
                ("Chicken Puff", 7),
                ("Masala Tea", 4),
                ("Chicken Puff", 6.5),
            ]
        ):
            e = await _errand(
                db,
                cid,
                u[rng.choice(["test", "meera", "nisha"])],
                u["ravi"],
                title=f"{name} run",
                category="FOOD",
                pickup="Darling Canteen",
                reward=25,
                days_ago=22 - i * 4 + rng.random(),
                stars=4,
            )
            ref = await fraud.get_reference(db, cid, normalize(name))
            await _claim(db, e, u["ravi"], name, float(ref.reference_price) + over, qty=1)
        e = await _errand(
            db,
            cid,
            u["meera"],
            u["ravi"],
            title="Samosas for the lab",
            pickup="Food Court",
            reward=25,
            days_ago=9.5,
            stars=4,
        )
        await _claim(db, e, u["ravi"], "Samosa", 15, qty=2)
        await db.flush()

        # Now the real detectors.
        near = await fraud.evaluate_near_threshold(db, cid, u["ravi"])
        await db.commit()
        await refresh_graph_metrics()
        rings = await fraud.sweep_collusion_rings(db)
        farming = await fraud.sweep_rating_farming(db)
        await db.commit()

        print(f"Near-the-limit flag for Ravi: {'yes' if near else 'no'}")
        print(f"Ring flags raised: {len(rings)}")
        for f in rings:
            print("   ", (f.details or {}).get("names"))
        print(f"Rating-farming flags raised: {len(farming)}")
        print("Done. Every demo student signs in with password123.")


if __name__ == "__main__":
    asyncio.run(build())
