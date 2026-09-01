"""Fuzzy lookup over the admin's non-MRP price list.

A requester typing "chikn puf" into a shopping list must still land on the
priced item, or the order falls back to an unpriced line and the whole
reference-price mechanism is bypassed by a typo. Matching therefore has to
tolerate misspelling, word order, singular/plural and partial words.

Deterministic and dependency-free, like `normalize`. difflib is stdlib and the
catalogue is campus-sized - tens to low hundreds of rows - so ranking every
candidate on every keystroke is cheaper than maintaining a trigram index, and
it cannot drift out of step with the normalizer the rest of the module uses.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ItemAlias, ReferencePrice
from .normalize import normalize

# Below this nothing is offered. Set by hand against the misspellings people
# actually make: "chikn puf" scores 0.91 against "chicken puff" and "omlet"
# reaches "bread omelette" at 0.68, while unrelated words sit under 0.2. Too
# low and the box fills with noise the user reads past; too high and one
# dropped letter hides the item.
MIN_SCORE = 0.46
MAX_RESULTS = 8


@dataclass(frozen=True)
class Suggestion:
    reference_id: uuid.UUID
    item_key: str
    display_name: str
    reference_price: float
    band_min: float
    band_max: float
    score: float
    # Set when the query matched through an approved alias rather than the
    # item's own name, so the UI can say why a search for "patties" returned
    # a puff instead of leaving the user to guess.
    matched_via: str | None


def _token_score(query_key: str, candidate_key: str) -> float:
    """How well two normalized keys agree, ignoring word order.

    Word order is ignored on purpose: "puff chicken" and "chicken puff" are the
    same request, and a requester scanning a shelf does not type in a canonical
    order.
    """
    if not query_key or not candidate_key:
        return 0.0
    if query_key == candidate_key:
        return 1.0

    q_words = query_key.split()
    c_words = candidate_key.split()

    # A whole-string ratio catches transpositions and dropped letters that
    # per-word comparison misses once a word boundary moves.
    whole = SequenceMatcher(None, query_key, candidate_key).ratio()

    def best_of(word: str, pool: list[str]) -> float:
        best = 0.0
        for other in pool:
            if other.startswith(word) or word.startswith(other):
                # Prefix agreement is the strongest signal while someone is
                # still typing, which is most of the time this runs.
                best = max(best, 0.94)
            else:
                best = max(best, SequenceMatcher(None, word, other).ratio())
        return best

    # How much of what the user typed is accounted for. This alone rewards a
    # partial query ("chick") without penalising it for the words not yet
    # typed.
    covered_query = sum(best_of(w, c_words) for w in q_words) / len(q_words)

    # How much of the candidate the query explains. Without this term a longer
    # entry scores at least as well as an exact one - "cold coffee 10c8d6"
    # covers the query just as fully as "cold coffee" - and the real item gets
    # pushed off the end of the list by its own near-duplicates.
    covered_candidate = sum(best_of(w, q_words) for w in c_words) / len(c_words)

    # Weighted toward the query, because a half-typed search must still work;
    # the candidate term is only there to break ties against padded names.
    score = max(whole, 0.75 * covered_query + 0.25 * covered_candidate)

    # A clean substring is a deliberate abbreviation ("cold coffee" inside
    # "cold coffee large"), not a coincidence. Capped below an exact match so
    # it can never displace the item the user actually named.
    if query_key in candidate_key:
        score = max(score, 0.88)
    return score


async def search_references(
    db: AsyncSession,
    *,
    campus_id: uuid.UUID,
    query: str,
    limit: int = MAX_RESULTS,
) -> list[Suggestion]:
    """Rank the campus price list against a partial, possibly misspelt query.

    An empty query returns the cheapest-to-scan default: the list in
    alphabetical order, so the box is useful before a key is pressed.
    """
    rows = (
        await db.execute(
            select(ReferencePrice).where(ReferencePrice.campus_id == campus_id)
        )
    ).scalars().all()
    if not rows:
        return []

    query_key = normalize(query or "")
    if not query_key:
        ordered = sorted(rows, key=lambda r: r.display_name.lower())[:limit]
        return [
            Suggestion(
                reference_id=r.id,
                item_key=r.item_key,
                display_name=r.display_name,
                reference_price=float(r.reference_price),
                band_min=float(r.band_min),
                band_max=float(r.band_max),
                score=0.0,
                matched_via=None,
            )
            for r in ordered
        ]

    # Approved aliases only. A PENDING alias is a suggestion awaiting a human,
    # and offering it here would let an unreviewed mapping steer a requester
    # onto the wrong reference price - the same asymmetry the alias table
    # enforces when judging claims.
    alias_rows = (
        await db.execute(
            select(ItemAlias).where(
                ItemAlias.campus_id == campus_id,
                ItemAlias.status == "APPROVED",
            )
        )
    ).scalars().all()
    aliases: dict[str, list[str]] = {}
    for a in alias_rows:
        aliases.setdefault(a.item_key, []).append(a.alias_key)

    scored: list[Suggestion] = []
    for r in rows:
        best = _token_score(query_key, r.item_key)
        via = None
        # The display name can carry words the key drops as stopwords, so it is
        # worth scoring in its own right.
        best = max(best, _token_score(query_key, normalize(r.display_name)))
        for alias_key in aliases.get(r.item_key, []):
            alias_score = _token_score(query_key, alias_key)
            if alias_score > best:
                best = alias_score
                via = alias_key
        if best >= MIN_SCORE:
            scored.append(
                Suggestion(
                    reference_id=r.id,
                    item_key=r.item_key,
                    display_name=r.display_name,
                    reference_price=float(r.reference_price),
                    band_min=float(r.band_min),
                    band_max=float(r.band_max),
                    score=round(best, 4),
                    matched_via=via,
                )
            )

    # Ties broken by name so the list does not reshuffle between keystrokes.
    scored.sort(key=lambda s: (-s.score, s.display_name.lower()))
    return scored[:limit]
