import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
from app.modules.auth.dependencies import require_active_user, require_admin
from app.modules.auth.models import User
from app.modules.errands.models import Errand
from app.modules.fraud import search
from app.modules.fraud import service as fraud
from app.modules.fraud.models import (
    FraudFlag,
    ItemAlias,
    ReferencePrice,
    ReferencePriceProposal,
    UserStrike,
)
from app.modules.fraud.normalize import normalize
from app.modules.fraud.schemas import (
    ClaimOut,
    ClaimResult,
    ClaimSubmission,
    FlagOut,
    FlagReview,
    ItemAliasOut,
    ProposalOut,
    ReferencePriceIn,
    ReferencePriceOut,
    ReferencePriceUpdate,
    ReferenceSuggestion,
    StandingOut,
    StrikeOut,
)

router = APIRouter(prefix="/fraud", tags=["fraud"])


# ------------------------------------------------------------ runner-facing


@router.post("/errands/{errand_id}/claims", response_model=ClaimResult)
async def submit_claims(
    errand_id: uuid.UUID,
    data: ClaimSubmission,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """Report what you actually paid at the counter.

    Submitted before delivery, so the amount is judged while the errand is
    still live and the runner learns immediately if something will be withheld.
    """
    errand = await db.get(Errand, errand_id)
    if errand is None or errand.deleted_at is not None:
        raise HTTPException(404, "Errand not found.")

    lines = [(line.name, Decimal(str(line.unit_price)), line.quantity) for line in data.lines]
    try:
        claims = await fraud.submit_claims(
            db, redis, errand=errand, runner=user, lines=lines
        )
    except fraud.FraudError as e:
        raise HTTPException(e.status_code, e.message) from e

    await db.commit()
    for claim in claims:
        await db.refresh(claim)

    total_claimed = sum(
        Decimal(str(c.claimed_unit_price)) * c.quantity for c in claims
    )
    total_eligible = sum(Decimal(str(c.eligible_amount)) for c in claims)
    withheld = max(total_claimed - total_eligible, Decimal("0"))

    # The per-item report IS the declaration, so record its total on the errand
    # too. Without this the requester's receipt keeps showing the estimate while
    # settlement pays the claimed figure, and the two disagree on screen.
    errand.amount_spent = total_claimed
    await db.commit()

    flagged = [c for c in claims if c.verdict == "FLAGGED"]
    message = None
    if flagged:
        names = ", ".join(c.raw_name for c in flagged)
        message = (
            f"₹{withheld:.0f} is on hold: {names} came in above the campus reference "
            "price. You will be paid the reference amount now; an admin reviews the rest."
        )

    return ClaimResult(
        claims=[ClaimOut.model_validate(c) for c in claims],
        total_claimed=float(total_claimed),
        total_eligible=float(total_eligible),
        withheld=float(withheld),
        message=message,
    )


@router.get("/me/standing", response_model=StandingOut)
async def my_standing(
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Your own fraud record, and how close you are to the next consequence."""
    flags = await fraud.count_recent_flags(db, user.id)
    rows = await db.execute(
        select(UserStrike)
        .where(UserStrike.user_id == user.id)
        .order_by(UserStrike.created_at.desc())
    )
    strikes = list(rows.scalars())
    blocked_until = await fraud.active_runner_block(db, user.id)

    next_at = next((t for t in fraud.STRIKE_THRESHOLDS if t > flags), None)
    return StandingOut(
        flags_in_window=flags,
        strikes=[StrikeOut.model_validate(s) for s in strikes],
        blocked_until=blocked_until,
        next_action_at=next_at,
    )


# ------------------------------------------------------------- admin: prices


@router.get("/references", response_model=list[ReferencePriceOut])
async def list_references(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        select(ReferencePrice)
        .where(ReferencePrice.campus_id == admin.campus_id)
        .order_by(ReferencePrice.display_name)
    )
    return [ReferencePriceOut.model_validate(r) for r in rows.scalars()]


@router.get("/references/search", response_model=list[ReferenceSuggestion])
async def search_references(
    q: str = Query(default="", max_length=120),
    limit: int = Query(default=8, ge=1, le=20),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Type-ahead over the admin's non-MRP price list.

    Open to any verified student, unlike the rest of /references: a requester
    has to be able to find a priced item while building a shopping list, and
    the reference price is not a secret - it is the number the runner will be
    judged against, so showing it up front is the honest thing to do.

    Fuzzy on purpose. If a typo dropped the requester onto an unpriced
    free-text line, the order would silently escape the reference-price
    mechanism entirely, which is the one thing this table exists to prevent.
    """
    hits = await search.search_references(
        db, campus_id=user.campus_id, query=q, limit=limit
    )
    return [ReferenceSuggestion(**vars(h)) for h in hits]


@router.post("/references", response_model=ReferencePriceOut, status_code=201)
async def create_reference(
    data: ReferencePriceIn,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Price a non-MRP item. Until an admin does this, nobody can be flagged
    for that item - the system will not invent a truth it was never given."""
    item_key = normalize(data.item_key or data.display_name)
    if not item_key:
        raise HTTPException(422, "Could not derive an item key from that name.")

    existing = await fraud.get_reference(db, admin.campus_id, item_key)
    if existing:
        raise HTTPException(409, f"'{item_key}' is already priced.")

    reference = ReferencePrice(
        campus_id=admin.campus_id,
        item_key=item_key,
        display_name=data.display_name,
        reference_price=Decimal(str(data.reference_price)),
        band_min=Decimal(str(data.band_min)),
        band_max=Decimal(str(data.band_max)),
        tolerance_abs=Decimal(str(data.tolerance_abs)),
        source="ADMIN",
        updated_by=admin.id,
    )
    db.add(reference)
    await db.commit()
    await db.refresh(reference)
    return ReferencePriceOut.model_validate(reference)


@router.patch("/references/{reference_id}", response_model=ReferencePriceOut)
async def update_reference(
    reference_id: uuid.UUID,
    data: ReferencePriceUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    reference = await db.get(ReferencePrice, reference_id)
    if reference is None or reference.campus_id != admin.campus_id:
        raise HTTPException(404, "Reference price not found.")

    for field in ("display_name", "reference_price", "band_min", "band_max", "tolerance_abs"):
        value = getattr(data, field)
        if value is not None:
            setattr(
                reference,
                field,
                value if field == "display_name" else Decimal(str(value)),
            )

    if not (reference.band_min <= reference.reference_price <= reference.band_max):
        raise HTTPException(422, "reference_price must sit inside the band.")

    # A human touched it, so it is authoritative again until the estimator
    # earns the right to move it.
    reference.source = "ADMIN"
    reference.updated_by = admin.id
    await db.commit()
    await db.refresh(reference)
    return ReferencePriceOut.model_validate(reference)


@router.post("/references/refresh", response_model=list[ReferencePriceOut])
async def refresh_references(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Re-run the estimator over every priced item on this campus.

    Also runs on a schedule in the worker; this endpoint exists so an admin can
    force it and see the result immediately.
    """
    await fraud.refresh_all_references(db, admin.campus_id)
    await db.commit()
    return await list_references(admin=admin, db=db)


# ---------------------------------------------------------- admin: proposals


@router.get("/proposals", response_model=list[ProposalOut])
async def list_proposals(
    status: str = "PENDING",
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        select(ReferencePriceProposal)
        .join(
            ReferencePrice,
            ReferencePrice.id == ReferencePriceProposal.reference_price_id,
        )
        .where(
            ReferencePrice.campus_id == admin.campus_id,
            ReferencePriceProposal.status == status,
        )
        .order_by(ReferencePriceProposal.created_at.desc())
    )
    return [ProposalOut.model_validate(p) for p in rows.scalars()]


@router.post("/proposals/{proposal_id}/approve", response_model=ReferencePriceOut)
async def approve_proposal(
    proposal_id: uuid.UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Accept a suggested band. This is the only path by which a band moves -
    the estimator can ask, but a person decides."""
    proposal = await db.get(ReferencePriceProposal, proposal_id)
    if proposal is None:
        raise HTTPException(404, "Proposal not found.")
    if proposal.status != "PENDING":
        raise HTTPException(409, "This proposal was already decided.")

    reference = await db.get(ReferencePrice, proposal.reference_price_id)
    if reference is None or reference.campus_id != admin.campus_id:
        raise HTTPException(404, "Reference price not found.")

    reference.band_min = proposal.proposed_band_min
    reference.band_max = proposal.proposed_band_max
    reference.reference_price = proposal.proposed_price
    reference.source = "ADMIN"
    reference.updated_by = admin.id

    proposal.status = "APPROVED"
    proposal.decided_at = datetime.now(UTC)
    proposal.decided_by = admin.id

    await db.commit()
    await db.refresh(reference)
    return ReferencePriceOut.model_validate(reference)


@router.post("/proposals/{proposal_id}/reject", response_model=ProposalOut)
async def reject_proposal(
    proposal_id: uuid.UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    proposal = await db.get(ReferencePriceProposal, proposal_id)
    if proposal is None:
        raise HTTPException(404, "Proposal not found.")
    if proposal.status != "PENDING":
        raise HTTPException(409, "This proposal was already decided.")
    proposal.status = "REJECTED"
    proposal.decided_at = datetime.now(UTC)
    proposal.decided_by = admin.id
    await db.commit()
    await db.refresh(proposal)
    return ProposalOut.model_validate(proposal)


@router.post("/collusion/sweep", response_model=list[FlagOut])
async def sweep_collusion(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Run the collusion-ring search now and return whatever it raised.

    Also runs on a timer in the worker; this exists so an admin can force it
    after a suspicious week rather than waiting for the next sweep. Returns an
    empty list when the graph is unavailable — a Neo4j outage must never
    manufacture accusations.
    """
    raised = await fraud.sweep_collusion_rings(db)
    await db.commit()
    for flag in raised:
        await db.refresh(flag)
    return [FlagOut.model_validate(f) for f in raised]


# ------------------------------------------------------------ admin: aliases


@router.get("/aliases", response_model=list[ItemAliasOut])
async def list_aliases(
    status: str = "PENDING",
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        select(ItemAlias)
        .where(ItemAlias.campus_id == admin.campus_id, ItemAlias.status == status)
        .order_by(ItemAlias.created_at.desc())
        .limit(200)
    )
    return [ItemAliasOut.model_validate(a) for a in rows.scalars()]


@router.post("/aliases/sweep", response_model=list[ItemAliasOut])
async def sweep_aliases(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Ask the model about item names that matched nothing recently.

    Also runs on a timer. Returns an empty list when no model is configured -
    the alias table simply stays as the admins left it.
    """
    created = await fraud.suggest_item_aliases(db, admin.campus_id)
    await db.commit()
    for row in created:
        await db.refresh(row)
    return [ItemAliasOut.model_validate(a) for a in created]


@router.post("/aliases/{alias_id}/decide", response_model=ItemAliasOut)
async def decide_alias(
    alias_id: uuid.UUID,
    approve: bool,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Confirm or reject a proposed equivalence.

    Approval is the moment an alias starts affecting judgement - until now it
    has changed nothing at all.
    """
    alias = await db.get(ItemAlias, alias_id)
    if alias is None or alias.campus_id != admin.campus_id:
        raise HTTPException(404, "Alias not found.")
    if alias.status != "PENDING":
        raise HTTPException(409, "That alias was already decided.")

    alias.status = "APPROVED" if approve else "REJECTED"
    alias.decided_at = datetime.now(UTC)
    alias.decided_by = admin.id
    await db.commit()
    await db.refresh(alias)
    return ItemAliasOut.model_validate(alias)


@router.post("/rating-farming/sweep", response_model=list[FlagOut])
async def sweep_rating_farming(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Check runners whose reputation rests on their own circle.

    Also runs on a timer. Raises cases for review; applies no punishment - a
    concentrated reputation is already self-limiting through the weighting.
    """
    raised = await fraud.sweep_rating_farming(db)
    await db.commit()
    for flag in raised:
        await db.refresh(flag)
    return [FlagOut.model_validate(f) for f in raised]


# -------------------------------------------------------------- admin: flags


@router.get("/flags", response_model=list[FlagOut])
async def list_flags(
    status: str = "OPEN",
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        select(FraudFlag)
        .where(FraudFlag.status == status)
        .order_by(FraudFlag.created_at.desc())
        .limit(200)
    )
    return [FlagOut.model_validate(f) for f in rows.scalars()]


@router.post("/flags/{flag_id}/review", response_model=FlagOut)
async def review_flag(
    flag_id: uuid.UUID,
    data: FlagReview,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """Uphold or dismiss a flag, releasing the withheld money accordingly.

    Dismissing does more than clear the flag: it pays the runner the amount
    that was held back and restores the claim as evidence for the reference
    estimate, because a claim we judged wrongly should not go on distorting
    what we think an item costs.
    """
    flag = await db.get(FraudFlag, flag_id)
    if flag is None:
        raise HTTPException(404, "Flag not found.")
    if flag.status != "OPEN":
        raise HTTPException(409, "This flag was already reviewed.")

    await fraud.review_flag(db, redis, flag=flag, admin=admin, uphold=data.uphold)
    await db.commit()
    await db.refresh(flag)
    return FlagOut.model_validate(flag)


@router.get("/users/{user_id}/standing", response_model=StandingOut)
async def user_standing(
    user_id: uuid.UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    flags = await fraud.count_recent_flags(db, user_id)
    rows = await db.execute(
        select(UserStrike)
        .where(UserStrike.user_id == user_id)
        .order_by(UserStrike.created_at.desc())
    )
    blocked_until = await fraud.active_runner_block(db, user_id)
    next_at = next((t for t in fraud.STRIKE_THRESHOLDS if t > flags), None)
    return StandingOut(
        flags_in_window=flags,
        strikes=[StrikeOut.model_validate(s) for s in rows.scalars()],
        blocked_until=blocked_until,
        next_action_at=next_at,
    )
