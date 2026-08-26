"""Friendships (Postgres) and social trust scoring (Neo4j).

The friendship half is ordinary CRUD. The scoring half is the platform's
differentiator, so the reasoning is written down here rather than left in a
paper nobody reads next to the code.

Trust over a social path is usually modelled as decaying with hop distance
(Jiang et al., ACM CSUR 2016). That is necessary but not sufficient here,
because on a single campus the structure that makes someone trustworthy is the
same structure that makes collusion easy. Four friends who take turns running
each other's grocery errands — a category where spend is unverifiable because
campus stores issue no receipts — look to a pure social ranker like the most
trustworthy matches on the platform.

So trust is discounted by how *closed* the neighbourhood carrying it is:

    trust = Π(edge_weight) × decay(hops) × (1 − closure_penalty)

A friend-of-friend reached through someone with many diverse connections is
informative: that intermediary has reputation at stake across many contexts. A
friend-of-friend reached through a small clique that only transacts internally
is not, and is a fraud signal rather than a trust signal.

Only the structural half of `closure_penalty` is implemented here. The
money-flow half needs settlement data (see PAID edges in the projection) and
belongs to the fraud work; `closure_penalty` is written so that half can be
added without touching the ranker.
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.graph import run_read
from app.modules.auth.models import User
from app.modules.outbox import service as outbox
from app.modules.social.models import Friendship, pair

logger = logging.getLogger(__name__)

AGGREGATE = "SOCIAL"


class SocialError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ------------------------------------------------------------------ friendships


async def _get_pair(db: AsyncSession, a: uuid.UUID, b: uuid.UUID) -> Friendship | None:
    lo, hi = pair(a, b)
    return await db.scalar(
        select(Friendship).where(Friendship.user_lo == lo, Friendship.user_hi == hi)
    )


async def request_friend(db: AsyncSession, me: User, target_id: uuid.UUID) -> Friendship:
    if target_id == me.id:
        raise SocialError("You can't add yourself.", 422)

    target = await db.get(User, target_id)
    if target is None or target.deleted_at is not None:
        raise SocialError("No such student.", 404)
    if target.campus_id != me.campus_id:
        # The whole trust model assumes one closed campus population.
        raise SocialError("That student isn't on your campus.", 403)

    existing = await _get_pair(db, me.id, target_id)
    if existing:
        if existing.status == "ACCEPTED":
            raise SocialError("You're already friends.", 409)
        if existing.status == "BLOCKED":
            # Deliberately the same message the recipient would see for a
            # decline: revealing "you are blocked" invites a second account.
            raise SocialError("Couldn't send that request.", 409)
        if existing.status == "PENDING":
            if existing.requested_by == me.id:
                raise SocialError("Request already sent.", 409)
            # They asked us first — treat accepting as the obvious intent.
            return await respond_to_request(db, me, existing.id, accept=True)
        # DECLINED → allow a fresh attempt by reusing the row.
        existing.status = "PENDING"
        existing.requested_by = me.id
        existing.responded_at = None
        await db.commit()
        await db.refresh(existing)
        return existing

    lo, hi = pair(me.id, target_id)
    row = Friendship(user_lo=lo, user_hi=hi, requested_by=me.id, status="PENDING")
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def respond_to_request(
    db: AsyncSession, me: User, friendship_id: uuid.UUID, accept: bool
) -> Friendship:
    row = await db.get(Friendship, friendship_id)
    if row is None or me.id not in (row.user_lo, row.user_hi):
        raise SocialError("No such request.", 404)
    if row.status != "PENDING":
        raise SocialError("That request is no longer pending.", 409)
    if row.requested_by == me.id:
        raise SocialError("You can't accept your own request.", 403)

    row.status = "ACCEPTED" if accept else "DECLINED"
    row.responded_at = datetime.now(UTC)

    if accept:
        # Only ACCEPTED reaches the graph. A pending or declined request is not
        # a trust signal and must never influence matching.
        outbox.emit(
            db,
            AGGREGATE,
            row.id,
            "FriendshipAccepted",
            {
                "user_a": str(row.user_lo),
                "user_b": str(row.user_hi),
                "at": row.responded_at.isoformat(),
            },
        )
    await db.commit()
    await db.refresh(row)
    return row


async def remove_friend(db: AsyncSession, me: User, other_id: uuid.UUID) -> None:
    row = await _get_pair(db, me.id, other_id)
    if row is None or row.status != "ACCEPTED":
        raise SocialError("You aren't friends.", 404)
    lo, hi = row.user_lo, row.user_hi
    await db.delete(row)
    outbox.emit(
        db, AGGREGATE, row.id, "FriendshipRemoved", {"user_a": str(lo), "user_b": str(hi)}
    )
    await db.commit()


async def block_user(db: AsyncSession, me: User, other_id: uuid.UUID) -> Friendship:
    """Block someone. Also severs the graph edge, so a blocked pair can never
    be matched to each other through social ranking."""
    if other_id == me.id:
        raise SocialError("You can't block yourself.", 422)
    row = await _get_pair(db, me.id, other_id)
    if row is None:
        lo, hi = pair(me.id, other_id)
        row = Friendship(user_lo=lo, user_hi=hi, requested_by=me.id, status="PENDING")
        db.add(row)
        await db.flush()
    if row.status != "BLOCKED":
        row.status_before_block = row.status
    row.status = "BLOCKED"
    row.blocked_by = me.id
    row.responded_at = datetime.now(UTC)
    outbox.emit(
        db,
        AGGREGATE,
        row.id,
        "FriendshipRemoved",
        {"user_a": str(row.user_lo), "user_b": str(row.user_hi)},
    )
    await db.commit()
    await db.refresh(row)
    return row


async def list_friends(db: AsyncSession, me: User) -> list[User]:
    rows = list(
        await db.scalars(
            select(Friendship).where(
                Friendship.status == "ACCEPTED",
                or_(Friendship.user_lo == me.id, Friendship.user_hi == me.id),
            )
        )
    )
    ids = [r.user_hi if r.user_lo == me.id else r.user_lo for r in rows]
    if not ids:
        return []
    return list(await db.scalars(select(User).where(User.id.in_(ids))))


async def list_pending(db: AsyncSession, me: User) -> list[tuple[Friendship, User]]:
    """Incoming requests awaiting my response, with the requester attached."""
    rows = list(
        await db.scalars(
            select(Friendship).where(
                Friendship.status == "PENDING",
                Friendship.requested_by != me.id,
                or_(Friendship.user_lo == me.id, Friendship.user_hi == me.id),
            )
        )
    )
    if not rows:
        return []
    users = {
        u.id: u
        for u in await db.scalars(
            select(User).where(User.id.in_([r.requested_by for r in rows]))
        )
    }
    return [(r, users[r.requested_by]) for r in rows if r.requested_by in users]


async def _friend_ids(db: AsyncSession, user_id: uuid.UUID) -> set[uuid.UUID]:
    rows = list(
        await db.scalars(
            select(Friendship).where(
                Friendship.status == "ACCEPTED",
                or_(Friendship.user_lo == user_id, Friendship.user_hi == user_id),
            )
        )
    )
    return {r.user_hi if r.user_lo == user_id else r.user_lo for r in rows}


async def search_students(
    db: AsyncSession, me: User, query: str, limit: int = 20
) -> list[dict]:
    """Find students on my campus by name or student ID.

    Mutual-friend counts come from Postgres rather than the graph: this is a
    one-hop intersection that Postgres answers exactly, and the search box must
    keep working when the graph is down.
    """
    q = query.strip()
    if len(q) < 2:
        return []

    like = f"%{q}%"
    candidates = list(
        await db.scalars(
            select(User)
            .where(
                User.campus_id == me.campus_id,
                User.id != me.id,
                User.deleted_at.is_(None),
                User.account_status == "ACTIVE",
                or_(User.display_name.ilike(like), User.student_id.ilike(like)),
            )
            .limit(limit)
        )
    )
    if not candidates:
        return []

    my_friends = await _friend_ids(db, me.id)
    existing = {}
    for row in await db.scalars(
        select(Friendship).where(
            or_(
                Friendship.user_lo.in_([c.id for c in candidates]),
                Friendship.user_hi.in_([c.id for c in candidates]),
            ),
            or_(Friendship.user_lo == me.id, Friendship.user_hi == me.id),
        )
    ):
        other = row.user_hi if row.user_lo == me.id else row.user_lo
        existing[other] = row

    out = []
    for c in candidates:
        row = existing.get(c.id)
        if row is None:
            rel = "NONE"
        elif row.status == "ACCEPTED":
            rel = "FRIENDS"
        elif row.status == "BLOCKED":
            rel = "BLOCKED"
        elif row.status == "PENDING":
            rel = "PENDING_OUT" if row.requested_by == me.id else "PENDING_IN"
        else:
            rel = "NONE"  # DECLINED reads as addable again

        theirs = await _friend_ids(db, c.id)
        out.append(
            {
                "id": c.id,
                "display_name": c.display_name,
                "student_id": c.student_id,
                "photo_url": c.photo_url,
                "reputation_score": c.reputation_score,
                "relationship": rel,
                "mutual_friends": len(my_friends & theirs),
            }
        )
    return out


# --------------------------------------------------------------------- scoring

# Trust retained per hop. 0.45 means a friend-of-a-friend carries a little under
# half the weight of a direct friend, and by hop 4 the contribution is ~4% —
# enough to prefer a distant-but-connected runner over a total stranger, not
# enough to outrank someone closer.
HOP_DECAY = 0.45

# Closure is the share of a neighbourhood's edges that stay inside it:
#
#     closure = internal / (internal + boundary)
#
# Deliberately NOT the local clustering coefficient. Clustering divides by
# deg×(deg−1), so a small clique cannot reach a high value however closed it is
# — a 4-person ring scores 0.5 while a 10-person hostel block scores 0.8. That
# ranks the threat exactly backwards, since the small ring is the likelier
# collusion unit. Closure is size-independent: what marks a ring is that its
# edges do not leave it, whether there are four members or ten.
CLOSURE_KNEE = 0.55
# Cap on the discount. Never 1.0: a real friendship is still weak evidence even
# inside a ring, and a full discount would make the ranker discontinuous.
MAX_CLOSURE_PENALTY = 0.7


def _closure_penalty(closure: float, degree: int) -> float:
    """How much to discount trust flowing through this neighbourhood.

    Rises with closure and is *not* diluted by degree — an earlier version
    divided the penalty by degree to spare well-connected intermediaries, which
    had the perverse effect of exempting exactly the small tight groups the
    measure exists to catch.

    Structure alone cannot separate a genuine four-person friend group from a
    four-person collusion ring: both look identically closed. What distinguishes
    them is whether *value circulates* inside the group — which needs the PAID
    edges the settlement projection writes, and is the fraud work's half of this
    function. Until that lands, this term is a soft prior, not a verdict, which
    is why MAX_CLOSURE_PENALTY sits well below 1.0.
    """
    if degree < 2 or closure <= CLOSURE_KNEE:
        return 0.0
    excess = (closure - CLOSURE_KNEE) / (1.0 - CLOSURE_KNEE)
    return min(MAX_CLOSURE_PENALTY, excess * MAX_CLOSURE_PENALTY)


def degree_label(degree: int | None) -> str:
    """LinkedIn-style badge for a friendship degree.

    'R' rather than '4th+' for anyone unreachable: the useful distinction to a
    runner scanning a feed is 'someone I'm connected to' vs 'a stranger', and a
    4th-degree path is, in practice, the latter.
    """
    return {1: "1st", 2: "2nd", 3: "3rd"}.get(degree or 0, "R" if not degree else f"{degree}th")


async def connection_between(viewer_id: uuid.UUID, other_id: uuid.UUID) -> dict:
    """One viewer→other connection, shaped for ConnectionOut."""
    if viewer_id == other_id:
        return {"degree": 0, "label": "You", "via": None, "trust": 0.0}
    scores = await social_scores(viewer_id, [other_id])
    s = scores.get(other_id)
    if not s:
        return {"degree": None, "label": "R", "via": None, "trust": 0.0}
    return {
        "degree": s["hops"],
        "label": degree_label(s["hops"]),
        "via": s.get("via"),
        "trust": s["trust"],
    }


async def connections_for(
    viewer_id: uuid.UUID, other_ids: list[uuid.UUID]
) -> dict[uuid.UUID, dict]:
    """Batch form of connection_between — one graph round-trip for a whole feed.

    Anyone with no path is simply absent from the result; callers fill in the
    stranger default. Doing this per-errand instead would put one Neo4j query
    per row on the feed's critical path.
    """
    targets = [i for i in set(other_ids) if i != viewer_id]
    if not targets:
        return {}
    scores = await social_scores(viewer_id, targets)
    return {
        rid: {
            "degree": s["hops"],
            "label": degree_label(s["hops"]),
            "via": s.get("via"),
            "trust": s["trust"],
        }
        for rid, s in scores.items()
    }


async def social_scores(
    requester_id: uuid.UUID, candidate_ids: list[uuid.UUID]
) -> dict[uuid.UUID, dict]:
    """Score each candidate runner's social proximity to the requester.

    Returns {runner_id: {"hops": int, "trust": float, "via": str | None}} for
    candidates reachable within social_max_hops. Absent means 'no path found or
    graph unavailable' — callers must treat that as unknown, not as zero trust.
    """
    if not candidate_ids:
        return {}

    cypher = """
    MATCH (me:User {id: $me})
    UNWIND $candidates AS cid
    MATCH (c:User {id: cid})
    OPTIONAL MATCH path = shortestPath((me)-[:FRIEND*1..%d]-(c))
    WITH c, path
    WHERE path IS NOT NULL
    WITH c, path, length(path) AS hops, nodes(path) AS ns
    // The intermediary carrying the path (the hop just after me), if any.
    WITH c, hops, CASE WHEN size(ns) > 2 THEN ns[1] ELSE null END AS via
    RETURN c.id           AS runner_id,
           hops           AS hops,
           via.id         AS via_id,
           via.name       AS via_name,
           CASE WHEN via IS NULL THEN 0.0
                ELSE coalesce(via.closure, 0.0) END AS via_closure,
           CASE WHEN via IS NULL THEN 0
                ELSE coalesce(via.degree, 0) END       AS via_degree
    """ % settings.social_max_hops

    rows = await run_read(
        cypher, me=str(requester_id), candidates=[str(c) for c in candidate_ids]
    )

    out: dict[uuid.UUID, dict] = {}
    for r in rows:
        hops = int(r["hops"])
        base = HOP_DECAY ** (hops - 1)  # direct friend (1 hop) = 1.0
        penalty = _closure_penalty(float(r["via_closure"] or 0.0), int(r["via_degree"] or 0))
        out[uuid.UUID(r["runner_id"])] = {
            "hops": hops,
            "trust": round(base * (1.0 - penalty), 4),
            "via": r.get("via_name"),
            "closure_penalty": round(penalty, 4),
        }
    return out
