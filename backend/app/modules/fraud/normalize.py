"""Item-name normalization.

A fraud detector that cannot tell "Chicken Puffs" from "chkn puf" is blind:
each spelling gets its own tiny sample, no sample ever reaches the threshold
for an estimate, and every claim comes back NO_REFERENCE. Grouping is a
precondition for detection, not a nicety.

Three tiers, cheapest first:
  1. deterministic rules  - case, punctuation, spacing, plurals, abbreviations
  2. fuzzy match          - typos, against the keys this campus already knows
  3. LLM alias resolution - the genuinely ambiguous leftovers (opt-in)

Tier 3 is the only place a model is used in this system, and it runs on the
*name*, never on the price. A model that could move prices would be a way to
launder a fraudulent claim into an accepted one.
"""

import re
import unicodedata
from difflib import SequenceMatcher

# Abbreviations and misspellings seen in canteen orders. Deliberately small and
# hand-kept: every entry here is a guess we are confident about.
ABBREVIATIONS = {
    "chkn": "chicken",
    "chknp": "chicken",
    "chik": "chicken",
    "chiken": "chicken",
    "chicke": "chicken",
    "puf": "puff",
    "puffs": "puff",
    "pufs": "puff",
    "veg": "vegetable",
    "vej": "vegetable",
    "nonveg": "non vegetable",
    "choco": "chocolate",
    "choc": "chocolate",
    "sndwch": "sandwich",
    "sandwitch": "sandwich",
    "brgr": "burger",
    "burgr": "burger",
    "samosa": "samosa",
    "samos": "samosa",
    "btl": "bottle",
    "wtr": "water",
    "cofee": "coffee",
    "coffe": "coffee",
    "chai": "tea",
    "biriyani": "biryani",
    "biriani": "biryani",
    "paratha": "paratha",
    "parota": "paratha",
    "porotta": "paratha",
    "maggie": "maggi",
    "roll": "roll",
}

# Words that carry no price signal. Size and flavour words are NOT here -
# a large tea costs more than a small one, so collapsing them would hide
# a real price difference behind a fake match.
STOPWORDS = {"a", "an", "the", "of", "with", "and", "plus", "pc", "pcs", "piece", "pieces"}

# Plural forms we undo. Kept conservative: blind s-stripping turns
# "samosas" into "samosa" correctly but "chips" into "chip" wrongly.
IRREGULAR_SINGULARS = {
    "chips": "chips",
    "fries": "fries",
    "noodles": "noodles",
    "samosas": "samosa",
    "rolls": "roll",
    "puffs": "puff",
    "burgers": "burger",
    "sandwiches": "sandwich",
    "biscuits": "biscuit",
    "breads": "bread",
    "eggs": "egg",
    "bottles": "bottle",
    "cakes": "cake",
}

_PUNCT = re.compile(r"[^\w\s]")
_SPACES = re.compile(r"\s+")

# Below this ratio two names are different items, not a typo of each other.
FUZZY_THRESHOLD = 0.86


def _singularize(word: str) -> str:
    if word in IRREGULAR_SINGULARS:
        return IRREGULAR_SINGULARS[word]
    # Only strip a trailing 's' when what remains is still a real-looking word.
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def normalize(raw: str) -> str:
    """Collapse a free-text item name to its canonical join key.

    Deterministic and dependency-free: the same input always produces the same
    key, which matters because this key is stored on every claim and a change
    in behaviour would orphan historical data.
    """
    if not raw:
        return ""
    # Strip accents so "café" and "cafe" agree.
    text = unicodedata.normalize("NFKD", raw)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = _PUNCT.sub(" ", text)
    text = _SPACES.sub(" ", text).strip()

    words: list[str] = []
    for word in text.split(" "):
        if not word or word in STOPWORDS:
            continue
        word = ABBREVIATIONS.get(word, word)
        word = _singularize(word)
        word = ABBREVIATIONS.get(word, word)
        # An abbreviation may expand to a phrase ("nonveg" -> "non vegetable").
        words.extend(word.split(" "))

    return " ".join(words)[:120]


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def best_fuzzy_match(key: str, known_keys: list[str]) -> tuple[str, float] | None:
    """Nearest known key above the threshold, or None.

    Ties break toward the shorter key: "chicken puff" beats "chicken puff jumbo"
    when both score alike, because the more specific name should have to earn
    the match rather than absorb everything nearby.
    """
    if not key or not known_keys:
        return None
    scored = [(k, similarity(key, k)) for k in known_keys]
    scored = [(k, s) for k, s in scored if s >= FUZZY_THRESHOLD]
    if not scored:
        return None
    scored.sort(key=lambda kv: (-kv[1], len(kv[0])))
    return scored[0]


def resolve_key(raw: str, known_keys: list[str]) -> tuple[str, bool]:
    """Map a raw name onto an existing key where possible.

    Returns (key, matched_existing). When nothing matches, the normalized form
    becomes a new key in its own right - an unrecognised item is not an error,
    it is just an item nobody has priced yet.
    """
    key = normalize(raw)
    if not key:
        return "", False
    if key in known_keys:
        return key, True
    match = best_fuzzy_match(key, known_keys)
    if match:
        return match[0], True
    return key, False
