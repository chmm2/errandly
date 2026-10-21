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
from app.modules.fraud import collusion
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

# --- how long a friendship takes to count for full trust --------------------
#
# A friendship carries less weight until it has been around a while, and the
# direction matters: it is the BRAND-NEW edge that is weak evidence, not the
# old one. An edge created yesterday could have been created for this errand.
#
# This is the tie that the farming work pushes attackers toward. Weighting
# ratings by distinct rater made repetition worthless, so the cheapest evasion
# became breadth — recruit eighty friends and have each rate once, which scores
# exactly as an honest runner does. Every one of those ties has to be created,
# and created recently. Maturity is what makes recruiting a network on Tuesday
# not pay off on Wednesday.
#
# Deliberately NOT a decay on old edges. Age makes a friendship stronger
# evidence, not weaker: a tie that has survived two years is more likely real
# than one from last week. Penalising it would punish the ordinary population
# to inconvenience nobody, since rebuilding a stale network costs an attacker
# nothing anyway.
FRIENDSHIP_MATURITY_DAYS = 30.0
# A new friendship is not worthless — most are exactly what they look like.
# It is discounted, and matures to full weight over the window above.
NEW_FRIENDSHIP_FLOOR = 0.40


def _maturity(age_days: float | None) -> float:
    """How much a friendship of this age counts, in [NEW_FRIENDSHIP_FLOOR, 1].

    Unknown age counts in full: edges written before `since` was recorded are
    genuinely old, and treating missing data as suspicious would penalise the
    earliest users of the platform for the platform's own gap.
    """
    if age_days is None:
        return 1.0
    if age_days >= FRIENDSHIP_MATURITY_DAYS:
        return 1.0
    ramp = max(0.0, age_days) / FRIENDSHIP_MATURITY_DAYS
    return NEW_FRIENDSHIP_FLOOR + (1.0 - NEW_FRIENDSHIP_FLOOR) * ramp

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
# Cap on the discount from STRUCTURE ALONE. Never 1.0: a closed neighbourhood
# is only capable of collusion, and a full discount on a suspicion would make
# the ranker discontinuous.
MAX_CLOSURE_PENALTY = 0.7
# Cap once money-flow evidence corroborates the shape. Higher because the
# question has changed: not "could this group collude" but "is value going
# round in it". Still short of 1.0 — even a corroborated ring may contain
# someone who simply has friends, and a 1.0 would erase them from matching.
MAX_CORROBORATED_PENALTY = 0.95


def _closure_penalty(closure: float, degree: int, circulation: float = 0.0) -> float:
    """How much to discount trust flowing through this neighbourhood.

    Rises with closure and is *not* diluted by degree — an earlier version
    divided the penalty by degree to spare well-connected intermediaries, which
    had the perverse effect of exempting exactly the small tight groups the
    measure exists to catch.

    Structure alone cannot separate a genuine four-person friend group from a
    four-person collusion ring: both look identically closed. What distinguishes
    them is whether *value circulates* inside the group, and `circulation` is
    that measurement — the share of a user's settled platform money that moved
    between them and their own friends (see modules/fraud/collusion.py).

    Circulation does not create a penalty on its own. An open, sociable group
    that happens to trade internally is not suspicious, and a closed group that
    barely transacts is only a shape. The penalty escalates where BOTH hold:
    the neighbourhood is sealed AND the money goes round inside it. That
    conjunction is what lifts the cap from 0.7 to 0.95 — structure asks the
    question, money flow answers it.
    """
    if degree < 2 or closure <= CLOSURE_KNEE:
        return 0.0
    excess = (closure - CLOSURE_KNEE) / (1.0 - CLOSURE_KNEE)
    structural = min(MAX_CLOSURE_PENALTY, excess * MAX_CLOSURE_PENALTY)

    corroboration = collusion.circulation_penalty(circulation)
    if corroboration <= 0.0:
        return structural

    # Interpolate from the structural prior toward the corroborated cap, in
    # proportion to how strong the money-flow evidence is.
    headroom = MAX_CORROBORATED_PENALTY - structural
    return min(MAX_CORROBORATED_PENALTY, structural + headroom * corroboration)


def _direct_penalty(closure: float, degree: int, circulation: float) -> float:
    """Discount on a DIRECT friendship.

    The closure penalty above only ever applied to the intermediary carrying a
    multi-hop path, which leaves a hole exactly where collusion lives: in a
    three-person ring every member is one hop from every other, there is no
    intermediary, and the ranker offered them each other's errands first at
    full trust.

    Structure alone must never discount a direct friend. A close-knit friend
    group is the most ordinary thing on a campus and the strongest honest trust
    signal the platform has — penalising it on shape would punish exactly the
    students the feature exists to serve. Only money-flow evidence justifies a
    discount here, scaled by how sealed the group is: the conjunction, never
    either half alone.
    """
    if degree < 2:
        return 0.0
    corroboration = collusion.circulation_penalty(circulation)
    if corroboration <= 0.0:
        return 0.0
    return min(MAX_CORROBORATED_PENALTY, closure * corroboration * MAX_CORROBORATED_PENALTY)


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


def _path_age_days(row: dict) -> float | None:
    """Age in days of the NEWEST friendship on the path, or None if every edge
    on it predates the `since` field."""
    newest = row.get("newest_since")
    if newest is None:
        return None
    try:
        when = datetime.fromisoformat(str(newest))
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (datetime.now(UTC) - when).total_seconds() / 86400.0)


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
    WITH c, path, length(path) AS hops, nodes(path) AS ns,
         // The NEWEST link on the path. A chain of trust is only as
         // established as its most recently created tie: an old friendship
         // reached through an edge made yesterday tells you about yesterday.
         reduce(newest = null, r IN relationships(path) |
                CASE WHEN r.since IS NULL THEN newest
                     WHEN newest IS NULL OR datetime(r.since) > datetime(newest)
                     THEN r.since ELSE newest END) AS newest_since,
         // Null only when EVERY edge predates the field, which means the path
         // is old rather than unknown.
         size([r IN relationships(path) WHERE r.since IS NULL]) AS undated
    WITH c, hops, newest_since, undated,
         CASE WHEN size(ns) > 2 THEN ns[1] ELSE null END AS via
    RETURN c.id           AS runner_id,
           hops           AS hops,
           newest_since   AS newest_since,
           undated        AS undated,
           via.id         AS via_id,
           via.name       AS via_name,
           CASE WHEN via IS NULL THEN 0.0
                ELSE coalesce(via.closure, 0.0) END AS via_closure,
           CASE WHEN via IS NULL THEN 0
                ELSE coalesce(via.degree, 0) END       AS via_degree,
           CASE WHEN via IS NULL THEN 0.0
                ELSE coalesce(via.circulation, 0.0) END AS via_circulation,
           coalesce(c.closure, 0.0)     AS c_closure,
           coalesce(c.degree, 0)        AS c_degree,
           coalesce(c.circulation, 0.0) AS c_circulation
    """ % settings.social_max_hops  # noqa: UP031 — Cypher is full of braces

    rows = await run_read(
        cypher, me=str(requester_id), candidates=[str(c) for c in candidate_ids]
    )

    out: dict[uuid.UUID, dict] = {}
    for r in rows:
        hops = int(r["hops"])
        base = HOP_DECAY ** (hops - 1)  # direct friend (1 hop) = 1.0
        if r.get("via_id") is None:
            # Direct friend: no intermediary to judge, so judge the candidate.
            penalty = _direct_penalty(
                float(r.get("c_closure") or 0.0),
                int(r.get("c_degree") or 0),
                float(r.get("c_circulation") or 0.0),
            )
        else:
            penalty = _closure_penalty(
                float(r["via_closure"] or 0.0),
                int(r["via_degree"] or 0),
                float(r.get("via_circulation") or 0.0),
            )
        maturity = _maturity(_path_age_days(r))
        out[uuid.UUID(r["runner_id"])] = {
            "hops": hops,
            "trust": round(base * (1.0 - penalty) * maturity, 4),
            "via": r.get("via_name"),
            "closure_penalty": round(penalty, 4),
            "maturity": round(maturity, 4),
        }
    return out
