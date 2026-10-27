"""Everything an admin needs to judge one flag.

A flag on its own is a conclusion. A reviewer deciding whether to uphold it
needs the evidence behind it and the history around it: what this item
usually costs, how this runner has priced before, which errands actually moved
money round a group, who left a runner's ratings. This module gathers that
from the source tables, so it holds even for a flag whose stored details are
thin, and it phrases the gist in plain sentences so the decision does not
depend on the reviewer decoding a rule name.

Read-only. Nothing here changes a flag, a hold or a reputation.
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta
from statistics import median

from sqlalchemy import String, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.modules.errands.models import Errand, ErrandItem, Rating
from app.modules.fraud import collusion
from app.modules.fraud import service as fraud
from app.modules.fraud.models import FraudFlag, ReferencePrice, RunnerPriceClaim, UserStrike
from app.modules.ledger.models import EscrowHold
from app.modules.social.models import Friendship
from app.modules.vendors.models import Vendor

# How far back the history panels reach. Longer than the 30-day strike window
# on purpose: a reviewer judging one claim wants to see the habit, not only
# the part of it that still counts toward a sanction.
HISTORY_DAYS = 90

RULE_KIND = {
    "CLAIM_ABOVE_REFERENCE": "price",
    "PERSISTENT_NEAR_THRESHOLD": "pattern",
    "PAYOUT_EXCEEDS_HOLD": "payout",
    "COLLUSION_RING": "ring",
    "RATING_FARMING": "ratings",
}

RULE_TITLE = {
    "CLAIM_ABOVE_REFERENCE": "Price reported above the usual price",
    "PERSISTENT_NEAR_THRESHOLD": "Always reporting just under the limit",
    "PAYOUT_EXCEEDS_HOLD": "Payout bigger than the money locked",
    "COLLUSION_RING": "Money going round a friend group",
    "RATING_FARMING": "Rating built mostly by friends",
}

# What each button actually does, per rule, in the words a reviewer needs.
DECISIONS = {
    "price": {
        "dismiss": "Runner was honest",
        "dismiss_effect": "Pays the runner the held amount and counts this price as normal again.",
        "uphold": "Overcharged",
        "uphold_effect": (
            "Returns the held amount to the requester and keeps the flag on the runner's record."
        ),
    },
    "pattern": {
        "dismiss": "Normal variation",
        "dismiss_effect": "Their prices count toward the usual price again. Nothing else changes.",
        "uphold": "Testing the limit",
        "uphold_effect": (
            "Their prices stay out of the usual-price calculation. No money is involved."
        ),
    },
    "payout": {
        "dismiss": "Pay the runner",
        "dismiss_effect": "Accepts the runner's report and releases the payment.",
        "uphold": "Don't pay the extra",
        "uphold_effect": (
            "Refuses the amount above what was locked and keeps the flag on the runner's record."
        ),
    },
    "ring": {
        "dismiss": "Genuine friends",
        "dismiss_effect": "Clears every member. They are offered each other's errands again.",
        "uphold": "Collusion ring",
        "uphold_effect": (
            "Keeps them from being offered each other's errands and lowers them in the queue."
        ),
    },
    "ratings": {
        "dismiss": "Genuinely well liked",
        "dismiss_effect": "Clears the flag. Their rating is unchanged.",
        "uphold": "Inflated ratings",
        "uphold_effect": (
            "Records the judgement. Friends' ratings already count for less, "
            "so nothing else changes."
        ),
    },
}


# ------------------------------------------------------------------ helpers


def _num(x) -> float | None:
    return None if x is None else float(x)


def _rs(x) -> str:
    """Rupees as a person would say them: whole when whole."""
    if x is None:
        return "₹?"
    v = float(x)
    return f"₹{v:,.0f}" if abs(v - round(v)) < 0.005 else f"₹{v:,.2f}"


def _pct(x) -> str:
    return f"{round(float(x) * 100)}%"


def _now() -> datetime:
    return datetime.now(UTC)


async def _names(db: AsyncSession, ids) -> dict[uuid.UUID, str]:
    ids = [i for i in set(ids) if i is not None]
    if not ids:
        return {}
    rows = await db.execute(select(User.id, User.display_name).where(User.id.in_(ids)))
    return {i: n for i, n in rows}


async def _store_names(db: AsyncSession, keys) -> dict[str, str]:
    """Readable names for store keys: the vendor's name, or the typed label."""
    keys = {k for k in keys if k}
    vendor_ids = []
    for k in keys:
        if k.startswith("vendor:"):
            try:
                vendor_ids.append(uuid.UUID(k[len("vendor:") :]))
            except ValueError:
                pass
    vendors = {}
    if vendor_ids:
        rows = await db.execute(select(Vendor.id, Vendor.name).where(Vendor.id.in_(vendor_ids)))
        vendors = {f"vendor:{i}": n for i, n in rows}
    out = {}
    for k in keys:
        if k in vendors:
            out[k] = vendors[k]
        elif k.startswith("label:"):
            out[k] = k[len("label:") :].title()
        else:
            out[k] = "A campus shop"
    return out


async def _subject(db: AsyncSession, user_id: uuid.UUID) -> dict:
    user = await db.get(User, user_id)
    runs = await db.scalar(
        select(func.count())
        .select_from(Errand)
        .where(Errand.runner_id == user_id, Errand.status == "COMPLETED")
    )
    posted = await db.scalar(
        select(func.count()).select_from(Errand).where(Errand.requester_id == user_id)
    )
    return {
        "id": str(user_id),
        "name": user.display_name if user else "Unknown student",
        "email": user.email if user else None,
        "joined": user.created_at if user else None,
        "rating": _num(user.effective_reputation) if user else None,
        "rating_count": user.rating_count if user else 0,
        "account_status": user.account_status if user else None,
        "runs_completed": runs or 0,
        "errands_posted": posted or 0,
    }


async def _record(db: AsyncSession, flag: FraudFlag) -> dict:
    """This person's history with the fraud system, so one flag is read in context."""
    since = _now() - timedelta(days=HISTORY_DAYS)
    flags = list(
        await db.scalars(
            select(FraudFlag)
            .where(FraudFlag.user_id == flag.user_id, FraudFlag.created_at >= since)
            .order_by(FraudFlag.created_at.desc())
            .limit(40)
        )
    )
    strikes = list(
        await db.scalars(
            select(UserStrike)
            .where(UserStrike.user_id == flag.user_id)
            .order_by(UserStrike.created_at.desc())
        )
    )
    decided = Counter(
        s
        for (s,) in await db.execute(
            select(FraudFlag.status).where(
                FraudFlag.user_id == flag.user_id, FraudFlag.status != "OPEN"
            )
        )
    )
    in_window = await fraud.count_recent_flags(db, flag.user_id)
    next_at = next((t for t in fraud.STRIKE_THRESHOLDS if t > in_window), None)
    return {
        "flags": [
            {
                "id": str(f.id),
                "kind": RULE_KIND.get(f.rule, "other"),
                "title": RULE_TITLE.get(f.rule, f.rule),
                "status": f.status,
                "created_at": f.created_at,
                "reviewed_at": f.reviewed_at,
                "is_this": f.id == flag.id,
            }
            for f in flags
        ],
        "strikes": [
            {
                "action": s.action,
                "level": s.level,
                "reason": s.reason,
                "created_at": s.created_at,
                "expires_at": s.expires_at,
                "lifted_at": s.lifted_at,
            }
            for s in strikes
        ],
        "upheld_before": decided.get("UPHELD", 0),
        "dismissed_before": decided.get("DISMISSED", 0),
        "price_flags_in_window": in_window,
        "window_days": fraud.PATTERN_WINDOW_DAYS,
        "next_action_at": next_at,
    }


async def _errand(db: AsyncSession, errand_id: uuid.UUID | None) -> dict | None:
    if errand_id is None:
        return None
    errand = await db.get(Errand, errand_id)
    if errand is None:
        return None
    hold = await db.scalar(select(EscrowHold).where(EscrowHold.errand_id == errand_id))
    names = await _names(db, [errand.requester_id, errand.runner_id])
    return {
        "id": str(errand.id),
        "title": errand.title,
        "category": errand.category,
        "pickup": errand.pickup_label,
        "requester": names.get(errand.requester_id, "Unknown"),
        "runner": names.get(errand.runner_id) if errand.runner_id else None,
        "status": errand.status,
        "reward": _num(errand.reward),
        "created_at": errand.created_at,
        "completed_at": errand.completed_at,
        "hold": (
            {
                "amount": _num(hold.amount),
                "released": _num(hold.released_amount),
                "remaining": _num(hold.amount) - (_num(hold.released_amount) or 0.0),
                "status": hold.status,
            }
            if hold
            else None
        ),
    }


# ------------------------------------------------------------- per rule


async def _price_case(db: AsyncSession, flag: FraudFlag, name: str) -> dict:
    d = flag.details or {}
    claim = await db.get(RunnerPriceClaim, flag.claim_id) if flag.claim_id else None
    if claim is None:
        # A flag whose claim was deleted still deserves a readable card.
        return {
            "story": [
                f"{name} reported {_rs(d.get('claimed'))} for {d.get('item') or 'an item'}, "
                f"against a usual price of {_rs(d.get('reference'))}.",
                "The original price report is no longer available, so there is no history to show.",
            ],
            "evidence": {"claimed_unit": d.get("claimed"), "reference": d.get("reference")},
            "history": None,
        }

    since = _now() - timedelta(days=HISTORY_DAYS)
    ref_row = await db.scalar(
        select(ReferencePrice).where(
            ReferencePrice.campus_id == claim.campus_id,
            ReferencePrice.item_key == claim.item_key,
        )
    )
    item = ref_row.display_name if ref_row else claim.raw_name
    unit = float(claim.claimed_unit_price)
    qty = claim.quantity
    ref = _num(claim.reference_snapshot)
    allowance = _num(claim.threshold_snapshot)
    line = (ref or 0) + (allowance or 0) if ref is not None else None
    claimed_total = unit * qty
    eligible = float(claim.eligible_amount)
    withheld = max(claimed_total - eligible, 0.0)

    rows = (
        await db.execute(
            select(RunnerPriceClaim, User.display_name)
            .join(User, User.id == RunnerPriceClaim.runner_id)
            .where(
                RunnerPriceClaim.campus_id == claim.campus_id,
                RunnerPriceClaim.item_key == claim.item_key,
                RunnerPriceClaim.created_at >= since,
            )
            .order_by(RunnerPriceClaim.created_at.desc())
            .limit(80)
        )
    ).all()
    mine = list(
        await db.scalars(
            select(RunnerPriceClaim)
            .where(
                RunnerPriceClaim.runner_id == flag.user_id,
                RunnerPriceClaim.created_at >= since,
            )
            .order_by(RunnerPriceClaim.created_at.desc())
            .limit(40)
        )
    )
    stores = await _store_names(
        db, [c.store_key for c, _ in rows] + [claim.store_key] + [c.store_key for c in mine]
    )

    item_claims = [
        {
            "at": c.created_at,
            "runner": runner,
            "is_subject": c.runner_id == flag.user_id,
            "is_this": c.id == claim.id,
            "store": stores.get(c.store_key),
            "unit": float(c.claimed_unit_price),
            "reference": _num(c.reference_snapshot),
            "verdict": c.verdict,
        }
        for c, runner in rows
    ]
    honest = [x["unit"] for x in item_claims if x["verdict"] != "FLAGGED"]
    stats = {
        "count": len(item_claims),
        "runners": len({c.runner_id for c, _ in rows}),
        "median_honest": median(honest) if honest else None,
        "lowest": min((x["unit"] for x in item_claims), default=None),
        "highest": max((x["unit"] for x in item_claims), default=None),
        "flagged": sum(1 for x in item_claims if x["verdict"] == "FLAGGED"),
        "reference_now": _num(ref_row.reference_price) if ref_row else None,
        "band": [_num(ref_row.band_min), _num(ref_row.band_max)] if ref_row else None,
    }
    verdicts = Counter(c.verdict for c in mine)
    store = stores.get(claim.store_key)
    store_reports = d.get("store_reports")

    story = [
        f"{name} reported paying {_rs(unit)} for each {item}"
        + (f", {qty} of them" if qty > 1 else "")
        + (f", at {store}." if store else "."),
    ]
    if ref is not None and line is not None:
        story.append(
            f"Students usually pay about {_rs(ref)} for it. "
            f"Anything up to {_rs(line)} is paid in full."
        )
        story.append(
            f"{_rs(unit)} is {_rs(unit - line)} past that line, so they were paid "
            f"{_rs(eligible)} and {_rs(withheld)} is held until you decide."
        )
    if store_reports is not None and store_reports < fraud.STORE_MIN_RUNNERS:
        who = (
            "Nobody had priced this item at this shop before"
            if store_reports == 0
            else f"Only {store_reports} runner{'s have' if store_reports != 1 else ' has'} "
            "priced this item at this shop"
        )
        story.append(
            f"{who}, so it was checked against the campus-wide price. "
            "If this shop is genuinely dearer, that would explain it."
        )
    if stats["count"] > 1 and stats["median_honest"] is not None:
        story.append(
            f"In the last {HISTORY_DAYS} days, {stats['runners']} runners reported this item "
            f"{stats['count']} times. Most paid about {_rs(stats['median_honest'])}."
        )

    return {
        "story": story,
        "evidence": {
            "item": item,
            "quantity": qty,
            "claimed_unit": unit,
            "reference": ref,
            "allowance": allowance,
            "line": line,
            "over_by": unit - line if line is not None else None,
            "eligible": eligible,
            "withheld": withheld,
            "store": store,
            "store_reports": store_reports,
        },
        "history": {
            "item_claims": item_claims,
            "item_stats": stats,
            "runner_claims": [
                {
                    "at": c.created_at,
                    "item": c.raw_name,
                    "unit": float(c.claimed_unit_price),
                    "reference": _num(c.reference_snapshot),
                    "verdict": c.verdict,
                    "is_this": c.id == claim.id,
                }
                for c in mine
            ],
            "runner_verdicts": dict(verdicts),
        },
    }


async def _pattern_case(db: AsyncSession, flag: FraudFlag, name: str) -> dict:
    d = flag.details or {}
    window = int(d.get("window_days") or fraud.PATTERN_WINDOW_DAYS)
    end = flag.created_at + timedelta(minutes=5)
    start = flag.created_at - timedelta(days=window)
    share = float(fraud.NEAR_THRESHOLD_SHARE)

    def judged(q):
        return q.where(
            RunnerPriceClaim.created_at >= start,
            RunnerPriceClaim.created_at <= end,
            RunnerPriceClaim.threshold_snapshot.is_not(None),
            RunnerPriceClaim.threshold_snapshot > 0,
            RunnerPriceClaim.verdict != "FLAGGED",
        )

    mine = list(
        await db.scalars(
            judged(
                select(RunnerPriceClaim).where(RunnerPriceClaim.runner_id == flag.user_id)
            ).order_by(RunnerPriceClaim.created_at)
        )
    )
    claims = []
    for c in mine:
        allowance = float(c.threshold_snapshot)
        over = float(c.delta_abs or 0)
        claims.append(
            {
                "at": c.created_at,
                "item": c.raw_name,
                "unit": float(c.claimed_unit_price),
                "reference": _num(c.reference_snapshot),
                "allowance": allowance,
                "over": over,
                "used": max(0.0, over / allowance) if allowance else 0.0,
                "near": over >= allowance * share,
            }
        )

    others = (
        await db.execute(
            judged(
                select(RunnerPriceClaim.delta_abs, RunnerPriceClaim.threshold_snapshot).where(
                    RunnerPriceClaim.runner_id != flag.user_id
                )
            )
        )
    ).all()
    campus_near = (
        sum(1 for o, t in others if float(o or 0) >= float(t) * share) / len(others)
        if others
        else None
    )
    near = sum(1 for c in claims if c["near"])
    avg_over = (
        sum(c["over"] for c in claims if c["near"]) / near if near else d.get("avg_rupees_over")
    )

    story = [
        f"{near or d.get('near_line_claims', 0)} of {len(claims) or d.get('judged_claims', 0)} "
        f"price reports {name} made in {window} days landed just under the limit.",
        "Each one was allowed on its own, so nothing was held.",
    ]
    if avg_over is not None:
        story.append(f"Each time they reported about {_rs(avg_over)} more than the usual price.")
    if campus_near is not None:
        story.append(
            f"Across campus, only {_pct(campus_near)} of other runners' reports land that close "
            "to the limit. Real prices scatter. Always landing just under the limit looks like "
            "testing it."
        )
    return {
        "story": story,
        "evidence": {
            "near": near,
            "judged": len(claims),
            "share_needed": float(fraud.NEAR_THRESHOLD_MIN_RATIO),
            "near_mark": share,
            "window_days": window,
            "avg_over": avg_over,
            "campus_near_share": campus_near,
        },
        "history": {"claims": claims},
    }


async def _payout_case(db: AsyncSession, flag: FraudFlag, name: str, errand: dict | None) -> dict:
    d = flag.details or {}
    lines = []
    ordered = []
    if flag.errand_id:
        lines = [
            {
                "item": c.raw_name,
                "quantity": c.quantity,
                "unit": float(c.claimed_unit_price),
                "reference": _num(c.reference_snapshot),
                "verdict": c.verdict,
                "eligible": float(c.eligible_amount),
            }
            for c in await db.scalars(
                select(RunnerPriceClaim).where(RunnerPriceClaim.errand_id == flag.errand_id)
            )
        ]
        ordered = [
            {
                "item": i.name_snapshot,
                "quantity": i.quantity,
                "unit": _num(i.unit_price_snapshot),
            }
            for i in await db.scalars(
                select(ErrandItem).where(ErrandItem.errand_id == flag.errand_id)
            )
        ]
    previous = await db.scalar(
        select(func.count())
        .select_from(FraudFlag)
        .where(
            FraudFlag.user_id == flag.user_id,
            FraudFlag.rule == "PAYOUT_EXCEEDS_HOLD",
            FraudFlag.id != flag.id,
        )
    )
    requester = errand["requester"] if errand else "The requester"
    title = f"“{errand['title']}”" if errand else "this errand"
    story = [
        f"{requester} locked {_rs(d.get('held'))} for {title}.",
        f"{name} reported spending enough that paying them back needs {_rs(d.get('payable'))}, "
        f"including the {_rs(d.get('reward'))} reward.",
        f"That is {_rs(d.get('gap'))} more than was ever locked, so nothing has been paid yet. "
        "Both students were told it is being reviewed.",
    ]
    if previous:
        story.append(
            f"This runner has had {previous} other payout{'s' if previous != 1 else ''} "
            "go over the locked amount before."
        )
    return {
        "story": story,
        "evidence": {
            "held": d.get("held"),
            "payable": d.get("payable"),
            "gap": d.get("gap"),
            "reward": d.get("reward"),
        },
        "history": {"reported_lines": lines, "ordered_items": ordered, "previous": previous or 0},
    }


async def _ring_case(db: AsyncSession, flag: FraudFlag) -> dict:
    d = flag.details or {}
    members: list[uuid.UUID] = []
    for m in d.get("members") or []:
        try:
            members.append(uuid.UUID(str(m)))
        except ValueError:
            continue
    names = await _names(db, members)
    since = _now() - timedelta(days=collusion.MONEY_WINDOW_DAYS)
    done_at = func.coalesce(Errand.completed_at, Errand.updated_at)

    errands = (
        list(
            await db.scalars(
                select(Errand)
                .where(
                    Errand.requester_id.in_(members),
                    Errand.runner_id.in_(members),
                    Errand.status == "COMPLETED",
                    done_at >= since,
                )
                .order_by(done_at)
            )
        )
        if members
        else []
    )

    def value(e: Errand) -> float:
        return float(e.reward or 0) + float(e.amount_spent or 0)

    occurrences = [
        {
            "at": e.completed_at or e.updated_at,
            "from": names.get(e.requester_id, "?"),
            "to": names.get(e.runner_id, "?"),
            "title": e.title,
            "value": value(e),
        }
        for e in errands
    ]
    legs_map: dict[tuple, dict] = {}
    for e in errands:
        key = (e.requester_id, e.runner_id)
        leg = legs_map.setdefault(
            key,
            {
                "from": names.get(e.requester_id, "?"),
                "to": names.get(e.runner_id, "?"),
                "errands": 0,
                "value": 0.0,
                "first": e.completed_at or e.updated_at,
                "last": e.completed_at or e.updated_at,
            },
        )
        leg["errands"] += 1
        leg["value"] += value(e)
        leg["last"] = e.completed_at or e.updated_at
    legs = []
    for leg in legs_map.values():
        leg["counts"] = leg["errands"] >= collusion.MIN_RING_LAPS and (
            leg["value"] >= collusion.MIN_RING_LEG_VALUE
            or leg["errands"] >= collusion.MIN_RING_LEG_TXNS
        )
        legs.append(leg)
    legs.sort(key=lambda x: -x["value"])

    pairs = []
    if members:
        for f in await db.scalars(
            select(Friendship).where(
                Friendship.user_lo.in_(members), Friendship.user_hi.in_(members)
            )
        ):
            pairs.append(
                {
                    "a": names.get(f.user_lo, "?"),
                    "b": names.get(f.user_hi, "?"),
                    "status": f.status,
                    "since": f.responded_at or f.created_at,
                }
            )

    outside = []
    for m in members:
        inside_runs = sum(1 for e in errands if e.runner_id == m)
        outside_runs = await db.scalar(
            select(func.count())
            .select_from(Errand)
            .where(
                Errand.runner_id == m,
                Errand.status == "COMPLETED",
                Errand.requester_id.not_in(members),
                done_at >= since,
            )
        )
        outside.append(
            {"name": names.get(m, "?"), "inside": inside_runs, "outside": outside_runs or 0}
        )

    who = [names.get(m, "?") for m in members]
    total = sum(o["value"] for o in occurrences)
    possible_pairs = len(members) * (len(members) - 1) // 2
    friends = sum(1 for p in pairs if p["status"] == "ACCEPTED")
    policy = d.get("policy")
    laps = d.get("laps") or (min((x["errands"] for x in legs), default=0) if legs else 0)

    story = []
    if who:
        if possible_pairs and friends == possible_pairs:
            story.append(f"{_join(who)} are all friends with each other.")
        else:
            story.append(f"{_join(who)}: {friends} of {possible_pairs} possible pairs are friends.")
    if occurrences:
        story.append(
            f"In the last {collusion.MONEY_WINDOW_DAYS} days they did {len(occurrences)} errands "
            f"for each other, worth about {_rs(total)}."
        )
        story.append(
            f"The money went round the group and came back, at least {laps} "
            f"time{'s' if laps != 1 else ''}."
        )
    else:
        story.append(
            "No completed errands between these members were found in the last "
            f"{collusion.MONEY_WINDOW_DAYS} days, so there is little evidence behind this flag."
        )
    if policy:
        story.append(
            f"Our matcher sends friends' errands to friends, which on its own would explain about "
            f"{_pct(policy['expected_share'])} of their errands going to each other. "
            f"The real figure was {_pct(policy['observed_share'])}."
        )
        story.append(
            f"That gap scores z = {policy['z']}. Below 3 would have been cleared automatically."
        )
    elif occurrences:
        story.append(
            "There were too few offer rounds to check whether our matcher caused this, "
            "so it came straight to you."
        )
    out_total = sum(o["outside"] for o in outside)
    if outside:
        story.append(
            f"Between them they also ran {out_total} errands for people outside the group."
        )
    story.append("No money is held. This is about the group, not one errand.")

    return {
        "story": story,
        "evidence": {
            "members": who,
            "total_value": d.get("total_value", total),
            "laps": laps,
            "min_leg_value": d.get("min_leg_value"),
            "closure": d.get("closure"),
            "policy": policy,
            "semantic": d.get("semantic"),
            "leg_rule": {
                "min_errands": collusion.MIN_RING_LAPS,
                "min_value": collusion.MIN_RING_LEG_VALUE,
                "or_errands": collusion.MIN_RING_LEG_TXNS,
            },
        },
        "history": {
            "legs": legs,
            "occurrences": occurrences,
            "friendships": pairs,
            "outside": outside,
            "window_days": collusion.MONEY_WINDOW_DAYS,
        },
    }


async def _ratings_case(db: AsyncSession, flag: FraudFlag, name: str) -> dict:
    d = flag.details or {}
    ratings = list(
        await db.scalars(
            select(Rating)
            .where(Rating.ratee_id == flag.user_id)
            .order_by(Rating.created_at.desc())
            .limit(100)
        )
    )
    friend_rows = await db.scalars(
        select(Friendship).where(
            Friendship.status == "ACCEPTED",
            or_(Friendship.user_lo == flag.user_id, Friendship.user_hi == flag.user_id),
        )
    )
    friends = {f.user_hi if f.user_lo == flag.user_id else f.user_lo for f in friend_rows}
    names = await _names(db, [r.rater_id for r in ratings])
    rows = [
        {
            "at": r.created_at,
            "rater": names.get(r.rater_id, "?"),
            "stars": r.stars,
            "from_friend": r.rater_id in friends,
            "comment": (r.comment or "")[:140] or None,
        }
        for r in ratings
    ]
    inside = [r for r in rows if r["from_friend"]]
    outside = [r for r in rows if not r["from_friend"]]

    def mean(rs):
        return round(sum(r["stars"] for r in rs) / len(rs), 2) if rs else None

    last_penalty = await db.scalar(
        select(func.max(UserStrike.created_at)).where(
            UserStrike.user_id == flag.user_id,
            UserStrike.action.in_(("REPUTATION_PENALTY", "WARNING")),
        )
    )
    in_n = d.get("in_cluster", len(inside))
    out_n = d.get("out_cluster", len(outside))
    mean_in = d.get("mean_in", mean(inside))
    mean_out = d.get("mean_out", mean(outside))

    story = (
        [f"{in_n} of {in_n + out_n} ratings for {name} came from their own friends."]
        if in_n + out_n
        else [f"No ratings for {name} were found, so there is little evidence behind this flag."]
    )
    if mean_in is not None and mean_out is not None:
        story.append(
            f"Friends give them {mean_in:.1f} stars on average. Everyone else gives {mean_out:.1f}."
        )
    elif mean_in is not None and not out_n:
        story.append("Nobody outside their friend group has ever rated them.")
    for reason in d.get("reasons") or []:
        # The averages above already say this one in plainer words.
        if mean_in is not None and mean_out is not None and "higher than strangers" in reason:
            continue
        story.append(reason[:1].upper() + reason[1:] + ".")
    story.append(
        "Their rating already counts friends' votes for less, "
        "so nothing else happens automatically."
    )
    return {
        "story": story,
        "evidence": {
            "in_cluster": in_n,
            "out_cluster": out_n,
            "mean_in": mean_in,
            "mean_out": mean_out,
            "post_penalty_burst": d.get("post_penalty_burst"),
            "last_penalty": last_penalty,
            "reviews": d.get("reviews"),
        },
        "history": {"ratings": rows},
    }


def _join(names: list[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


# ---------------------------------------------------------------- public


def subject_label(flag: FraudFlag, name: str | None) -> str | None:
    """Who the queue names: the person, or for a ring the whole group."""
    names = (flag.details or {}).get("names")
    if flag.rule == "COLLUSION_RING" and names:
        return _join([n.split(" ")[0] for n in names])
    return name


def headline(flag: FraudFlag) -> str:
    """One line for the queue, from the stored details alone."""
    d = flag.details or {}
    rule = flag.rule
    if rule == "CLAIM_ABOVE_REFERENCE":
        item = (d.get("item") or "item").title()
        return f"{item}: {_rs(d.get('claimed'))} vs usual {_rs(d.get('reference'))}"
    if rule == "PERSISTENT_NEAR_THRESHOLD":
        near, judged = d.get("near_line_claims", "?"), d.get("judged_claims", "?")
        return f"{near} of {judged} reports just under the limit"
    if rule == "PAYOUT_EXCEEDS_HOLD":
        return f"Needs {_rs(d.get('payable'))}, only {_rs(d.get('held'))} locked"
    if rule == "COLLUSION_RING":
        size = d.get("size") or len(d.get("members") or [])
        value = d.get("total_value")
        return f"Group of {size}" + (f", {_rs(value)} went round" if value else "")
    if rule == "RATING_FARMING":
        i, o = d.get("in_cluster"), d.get("out_cluster")
        if i is not None and o is not None:
            return f"{i} of {i + o} ratings from friends"
        return "Ratings mostly from friends"
    return rule.replace("_", " ").title()


async def build_case(db: AsyncSession, flag: FraudFlag) -> dict:
    kind = RULE_KIND.get(flag.rule, "other")
    subject = await _subject(db, flag.user_id)
    errand = await _errand(db, flag.errand_id)
    name = subject["name"]

    if kind == "price":
        body = await _price_case(db, flag, name)
    elif kind == "pattern":
        body = await _pattern_case(db, flag, name)
    elif kind == "payout":
        body = await _payout_case(db, flag, name, errand)
    elif kind == "ring":
        body = await _ring_case(db, flag)
    elif kind == "ratings":
        body = await _ratings_case(db, flag, name)
    else:
        body = {"story": [f"Flag type {flag.rule}."], "evidence": flag.details, "history": None}

    return {
        "flag_id": str(flag.id),
        "kind": kind,
        "rule": flag.rule,
        "title": RULE_TITLE.get(flag.rule, flag.rule),
        "status": flag.status,
        "severity": flag.severity,
        "created_at": flag.created_at,
        "subject": subject,
        "errand": errand,
        "story": body["story"],
        "evidence": body["evidence"],
        "history": body["history"],
        "record": await _record(db, flag),
        "decision": DECISIONS.get(kind),
    }


async def overview(db: AsyncSession) -> dict:
    """The numbers across the top of the console."""
    by_rule = dict(
        (
            await db.execute(
                select(FraudFlag.rule, func.count())
                .where(FraudFlag.status == "OPEN")
                .group_by(FraudFlag.rule)
            )
        ).all()
    )
    people = await db.scalar(
        select(func.count(func.distinct(FraudFlag.user_id))).where(FraudFlag.status == "OPEN")
    )
    withheld = await db.scalar(
        select(
            func.coalesce(
                func.sum(
                    RunnerPriceClaim.claimed_unit_price * RunnerPriceClaim.quantity
                    - RunnerPriceClaim.eligible_amount
                ),
                0,
            )
        )
        .select_from(FraudFlag)
        .join(RunnerPriceClaim, RunnerPriceClaim.id == FraudFlag.claim_id)
        .where(FraudFlag.status == "OPEN", FraudFlag.rule == "CLAIM_ABOVE_REFERENCE")
    )
    frozen = await db.scalar(
        select(func.coalesce(func.sum(EscrowHold.amount - EscrowHold.released_amount), 0)).where(
            EscrowHold.status == "PENDING_REVIEW"
        )
    )
    latest = await db.scalar(
        select(func.max(FraudFlag.created_at)).where(FraudFlag.status == "OPEN")
    )
    # A ring is written as one flag per member but reviewed as one case.
    if by_rule.get("COLLUSION_RING"):
        by_rule["COLLUSION_RING"] = await db.scalar(
            select(
                func.count(
                    func.distinct(
                        func.coalesce(
                            FraudFlag.details["signature"].astext, func.cast(FraudFlag.id, String)
                        )
                    )
                )
            ).where(FraudFlag.status == "OPEN", FraudFlag.rule == "COLLUSION_RING")
        )
    by_kind: Counter = Counter()
    for rule, n in by_rule.items():
        by_kind[RULE_KIND.get(rule, "other")] += n
    return {
        "open": sum(by_rule.values()),
        "by_kind": dict(by_kind),
        "people": people or 0,
        "withheld": float(withheld or 0),
        "frozen": float(frozen or 0),
        "latest_at": latest,
    }
