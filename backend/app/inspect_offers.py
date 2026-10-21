"""Read the offer log by hand.

    docker compose exec backend python -m app.inspect_offers
    docker compose exec backend python -m app.inspect_offers <user-id>

The sweep consumes this table automatically, but nothing surfaces it to a
person. That is fine for the detector and useless for anyone trying to
understand a decision after the fact — "why did Ujjwal get that errand?" has an
exact answer sitting in a JSONB column that no screen displays.

So this prints it: overall coverage, one worked round, and — given a user — what
the policy expected of them against what actually happened, which is the same
arithmetic sweep_collusion_rings runs.
"""

import asyncio
import sys
import uuid

from sqlalchemy import func, select

import app.models  # noqa: F401
from app.core.database import SessionLocal
from app.modules.auth.models import User
from app.modules.errands.models import OfferLog
from app.modules.fraud import policy


async def overview(db) -> None:
    total = await db.scalar(select(func.count()).select_from(OfferLog))
    explored = await db.scalar(
        select(func.count()).select_from(OfferLog).where(OfferLog.exploring)
    )
    taken = await db.scalar(
        select(func.count()).select_from(OfferLog)
        .where(OfferLog.accepted_runner_id.is_not(None))
    )
    print("OFFER LOG")
    print(f"  rounds recorded : {total}")
    print(f"  socially blind  : {explored}"
          f"   ({explored / total:.1%} of rounds)" if total else "")
    print(f"  someone accepted: {taken}")
    print(f"  usable for the policy check: {taken} "
          f"(need {policy.MIN_ROUNDS} per group)")


async def one_round(db) -> None:
    """Print a single round in full — the answer to 'why did they get it?'"""
    row = (
        await db.scalars(
            select(OfferLog)
            .where(OfferLog.accepted_runner_id.is_not(None))
            .order_by(OfferLog.created_at.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        print("\nno completed round yet")
        return

    names = {
        str(u.id): u.display_name
        for u in await db.scalars(
            select(User).where(
                User.id.in_([uuid.UUID(c["runner_id"]) for c in row.candidates])
            )
        )
    }
    print(f"\nMOST RECENT COMPLETED ROUND   (round {row.round_no}, "
          f"{'EXPLORING - no friend boost' if row.exploring else 'normal'})")
    print(f"  {'runner':<18}{'distance':>10}{'friend':>9}{'rating':>9}"
          f"{'penalty':>9}{'score':>10}   took it")
    for c in row.candidates:
        took = "  <-- yes" if c["runner_id"] == str(row.accepted_runner_id) else ""
        # The bonus terms as they were actually applied on this round.
        friend = -c["trust"] * 1500 if c.get("trust_applied", True) else 0.0
        rating = -(c["reputation"] - 3.5) * 800
        print(f"  {names.get(c['runner_id'], '?')[:17]:<18}"
              f"{c['distance_m']:>9.0f}m{friend:>9.0f}{rating:>9.0f}"
              f"{c['penalty']:>9.0f}{c['effective']:>10.1f}{took}")


async def for_user(db, user_id: uuid.UUID) -> None:
    """What the policy expected of this person's circle, against what happened."""
    user = await db.get(User, user_id)
    if user is None:
        print(f"\nno such user: {user_id}")
        return

    from app.modules.social.service import _friend_ids

    friends = await _friend_ids(db, user_id)
    group = [user_id, *friends]
    print(f"\nPOLICY CHECK for {user.display_name} and {len(friends)} friend(s)")

    excess = await policy.excess_for_group(db, group)
    if excess is None:
        print(f"  not enough history yet — needs {policy.MIN_ROUNDS} completed "
              f"rounds where one of them posted the errand")
        return

    print(f"  rounds looked at        : {excess.rounds} "
          f"({excess.explored_rounds} socially blind)")
    print(f"  the app EXPECTED        : {excess.expected:.1f} "
          f"({excess.expected_share:.0%} of rounds)")
    print(f"  what ACTUALLY happened  : {excess.observed} "
          f"({excess.observed_share:.0%})")
    print(f"  unexplained             : {excess.observed - excess.expected:+.1f}")
    print(f"  z                       : {excess.z:.2f}")
    print(f"  verdict                 : "
          f"{'explained by our own routing - no flag' if excess.explained else 'UNEXPLAINED - would continue to the ring check'}")


async def main() -> None:
    async with SessionLocal() as db:
        await overview(db)
        await one_round(db)
        if len(sys.argv) > 1:
            await for_user(db, uuid.UUID(sys.argv[1]))
        else:
            print("\n(pass a user id to run the policy check for their circle)")


if __name__ == "__main__":
    asyncio.run(main())
