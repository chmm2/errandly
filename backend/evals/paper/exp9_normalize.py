"""Experiment 9: does a misspelt claim reach the right reference?

A claim whose item name does not group with its peers is judged against no
reference at all, so it is never checked. This measures tiers 1-2 of
fraud.normalize.resolve_key (deterministic rules, then fuzzy matching against
the keys a campus already prices) on a hand-built set of variants of twenty
canteen items, and on names that must NOT be merged into a listed item.

The variants were written by us, so this measures coverage of the kinds of
error we thought of, not field accuracy.

Second part, adversarial names. A runner who wants a priced line paid
unchecked has every reason to type a name that groups with nothing. For an
order holding three priced lines and two hand-typed unpriced ones, each
attempted name is classified twice, by the rule before the review fix
(resolve_key against the campus's priced keys) and by the deployed rule
(fraud.service._match_order_line against the order's own lines):

  JUDGED_SAME   judged against the reference of the line it really is
  JUDGED_OTHER  judged against a different priced line's reference
  UNCHECKED     no reference: paid as claimed, up to the escrow hold
  REFUSED       rejected with 422, nothing recorded

Run: python -m evals.paper.exp9_normalize
"""

from __future__ import annotations

from types import SimpleNamespace

from app.modules.fraud import service as fraud
from app.modules.fraud.normalize import normalize, resolve_key
from evals.paper.common import save

ITEMS = ["Chicken Puff", "Veg Puff", "Egg Puff", "Masala Tea", "Ginger Tea", "Samosa",
         "Veg Sandwich", "Chicken Sandwich", "Cold Coffee", "Hot Coffee", "Veg Biryani",
         "Chicken Biryani", "Paneer Roll", "Chicken Roll", "Veg Maggi", "Lime Soda",
         "Water Bottle", "Chocolate Milkshake", "Bread Omelette", "Paratha"]

# Realistic ways a runner at a counter types each one.
VARIANTS = {
    "Chicken Puff": ["chicken puffs", "CHICKEN PUFF", "chkn puf", "chiken puff", "chicken puf",
                     "chicken-puff", "chikcen puff", "chicken  puff!!", "1 chicken puff",
                     "chicken puff pc"],
    "Veg Puff": ["veg puffs", "vej puff", "veg puf", "vegetable puff", "Veg-Puff",
                 "veg pufff", "vg puff", "veg puff (1)", "veg puffs x2", "VEG PUFF"],
    "Egg Puff": ["egg puffs", "egg puf", "eg puff", "Egg  Puff", "egg-puff", "egg pufs",
                 "eggpuff", "egg puff pcs", "EGG PUFF", "egg puffe"],
    "Masala Tea": ["masala chai", "masla tea", "masala tea!", "Masala-Tea", "masala teaa",
                   "MASALA TEA", "masala tee", "masal tea", "masala tea 1", "a masala tea"],
    "Ginger Tea": ["ginger chai", "ginger tea", "gingr tea", "Ginger-Tea", "ginger tee",
                   "GINGER TEA", "ginger teas", "ginjer tea", "ginger tea pc", "the ginger tea"],
    "Samosa": ["samosas", "samos", "SAMOSA", "samoosa", "smosa", "samosa pcs", "2 samosas",
               "samosa (2)", "samosaa", "Samosa."],
    "Veg Sandwich": ["veg sandwiches", "veg sandwitch", "veg sndwch", "vegetable sandwich",
                     "veg sanwich", "VEG SANDWICH", "veg-sandwich", "veg sandwhich",
                     "veg sandwich 1", "veg sandwichs"],
    "Chicken Sandwich": ["chicken sandwiches", "chkn sandwich", "chicken sandwitch",
                         "chicken sndwch", "chiken sandwich", "CHICKEN SANDWICH",
                         "chicken sanwich", "chicken-sandwich", "chicken sandwhich",
                         "chicken sandwich pc"],
    "Cold Coffee": ["cold cofee", "cold coffe", "COLD COFFEE", "cold-coffee", "cold coffees",
                    "cold cofe", "cold kofee", "cold coffee!", "coldcoffee", "cold coffee 1"],
    "Hot Coffee": ["hot cofee", "hot coffe", "HOT COFFEE", "hot-coffee", "hot coffees",
                   "hot cofe", "hott coffee", "hot coffee!", "hotcoffee", "hot coffee pc"],
    "Veg Biryani": ["veg biriyani", "veg biriani", "vegetable biryani", "veg briyani",
                    "VEG BIRYANI", "veg-biryani", "veg biryanni", "veg biryani 1",
                    "veg biriyani plate", "veg biryanis"],
    "Chicken Biryani": ["chicken biriyani", "chicken biriani", "chkn biryani", "chiken biryani",
                        "CHICKEN BIRYANI", "chicken-biryani", "chicken briyani",
                        "chicken biryanni", "chicken biryani 1", "chicken biryanis"],
    "Paneer Roll": ["paneer rolls", "panner roll", "paneer rol", "PANEER ROLL", "paneer-roll",
                    "paner roll", "paneer rool", "paneer roll pc", "paneer roll!", "panir roll"],
    "Chicken Roll": ["chicken rolls", "chkn roll", "chiken roll", "CHICKEN ROLL",
                     "chicken-roll", "chicken rol", "chicken rool", "chicken roll pcs",
                     "chicken roll 2", "chickn roll"],
    "Veg Maggi": ["veg maggie", "veg magi", "vegetable maggi", "VEG MAGGI", "veg-maggi",
                  "veg maggii", "veg magggi", "veg maggi 1", "veg maggi!", "vej maggi"],
    "Lime Soda": ["lime sodas", "lime sodaa", "LIME SODA", "lime-soda", "lyme soda",
                  "lime soad", "lime soda 1", "lime soda!", "limesoda", "lime sodda"],
    "Water Bottle": ["water bottles", "wtr btl", "water btl", "WATER BOTTLE", "water-bottle",
                     "watr bottle", "water botle", "water bottle 1", "a water bottle",
                     "water bottel"],
    "Chocolate Milkshake": ["choco milkshake", "choc milkshake", "chocolate milkshakes",
                            "CHOCOLATE MILKSHAKE", "chocolate milk shake",
                            "chocolate milkshak", "chocolate-milkshake", "chocolat milkshake",
                            "chocolate milkshake 1", "chocolate milkshake!"],
    "Bread Omelette": ["bread omlette", "bread omelet", "bread omelettes", "BREAD OMELETTE",
                       "bread-omelette", "bred omelette", "bread omellete", "bread omelette 1",
                       "bread omlet", "bread omelette!"],
    "Paratha": ["parathas", "parota", "porotta", "PARATHA", "paratha!", "paratta", "parata",
                "paratha 2", "paratha pcs", "parantha"],
}

# Names that are a different thing and must not be priced as a listed item.
MUST_NOT_MERGE = ["large masala tea", "mutton biryani", "paneer tikka roll", "egg roll",
                  "chicken puff jumbo", "veg cheese sandwich", "iced tea", "lemon tea",
                  "mango milkshake", "masala dosa", "chicken 65", "egg biryani",
                  "veg noodles", "chicken noodles", "cheese maggi", "fresh lime juice",
                  "green tea", "filter coffee", "aloo paratha", "paneer puff"]


ORDER_PRICED = ["Chicken Puff", "Veg Puff", "Masala Tea"]
ORDER_LOOSE = ["Notebook", "Blue Pen"]

# What a runner might type instead of the item's name, by intent.
ATTACKS = {
    "Chicken Puff": {
        "misspell": ["chikn pufff", "chicken pufs", "chickn puff", "chicken poof"],
        "padding": ["chicken puff special", "chicken puff large", "big chicken puff",
                    "fresh chicken puff"],
        "obfuscation": ["ch1cken puff", "c h i c k e n puff", "chicken_puff", "chickenpuff",
                        "ch\u0456cken puff", "CHICKEN PUFF :)"],
        "rename": ["snack", "item 1", "zzq special", "bakery item", "puff pastry"],
        "swap": ["notebook", "blue pen"],
    },
    "Veg Puff": {
        "misspell": ["vej puf", "veg pufff", "vg puff", "veg poff"],
        "padding": ["veg puff special", "veg puff large", "big veg puff", "fresh veg puff"],
        "obfuscation": ["v3g puff", "v e g puff", "veg_puff", "vegpuff", "VEG PUFF!!"],
        "rename": ["snack", "item 2", "qqx", "bakery item", "vegetable pastry"],
        "swap": ["notebook", "blue pen"],
    },
    "Masala Tea": {
        "misspell": ["masla tee", "masala teaa", "msala tea", "masala tae"],
        "padding": ["masala tea large", "special masala tea", "masala tea cup",
                    "hot masala tea"],
        "obfuscation": ["m4sala tea", "m a s a l a tea", "masala_tea", "masalatea",
                        "MASALA TEA..."],
        "rename": ["drink", "item 3", "chai", "beverage", "cutting"],
        "swap": ["notebook", "blue pen"],
    },
}


def adversarial() -> dict:
    campus_keys = [normalize(i) for i in ITEMS]
    lines = [(normalize(n), SimpleNamespace(item_key=normalize(n)), 1) for n in ORDER_PRICED]
    lines += [(normalize(n), None, 1) for n in ORDER_LOOSE]

    def old_rule(name, target):
        key, matched = resolve_key(name, campus_keys)
        if not matched:
            return "UNCHECKED"
        return "JUDGED_SAME" if key == target else "JUDGED_OTHER"

    def new_rule(name, target):
        bound = fraud._match_order_line(name, lines)
        if bound is None:
            return "REFUSED"
        if bound[1] is None:
            return "UNCHECKED"
        return "JUDGED_SAME" if bound[1].item_key == target else "JUDGED_OTHER"

    outcomes = ("JUDGED_SAME", "JUDGED_OTHER", "UNCHECKED", "REFUSED")
    table: dict[str, dict] = {}
    attempts = []
    for item, kinds in ATTACKS.items():
        target = normalize(item)
        for kind, names in kinds.items():
            row = table.setdefault(kind, {"attempts": 0,
                                          "old": dict.fromkeys(outcomes, 0),
                                          "new": dict.fromkeys(outcomes, 0)})
            for name in names:
                o, n = old_rule(name, target), new_rule(name, target)
                row["attempts"] += 1
                row["old"][o] += 1
                row["new"][n] += 1
                attempts.append({"item": item, "kind": kind, "name": name,
                                 "old": o, "new": n})
    total = {"attempts": sum(r["attempts"] for r in table.values()),
             "old": {k: sum(r["old"][k] for r in table.values()) for k in outcomes},
             "new": {k: sum(r["new"][k] for r in table.values()) for k in outcomes}}
    return {"order_priced": ORDER_PRICED, "order_loose": ORDER_LOOSE,
            "by_kind": table, "total": total, "attempts": attempts}


def main() -> dict:
    keys = [normalize(i) for i in ITEMS]
    correct = wrong = unmatched = 0
    misses = []
    per_item = {}
    for item, variants in VARIANTS.items():
        target = normalize(item)
        ok = 0
        for v in variants:
            key, matched = resolve_key(v, keys)
            if matched and key == target:
                correct += 1
                ok += 1
            elif matched:
                wrong += 1
                misses.append({"variant": v, "expected": target, "got": key, "kind": "WRONG"})
            else:
                unmatched += 1
                misses.append({"variant": v, "expected": target, "got": key, "kind": "UNMATCHED"})
        per_item[item] = ok
    false_merges = []
    for name in MUST_NOT_MERGE:
        key, matched = resolve_key(name, keys)
        if matched:
            false_merges.append({"name": name, "merged_into": key})
    total = sum(len(v) for v in VARIANTS.values())
    out = {"items": len(ITEMS), "variants": total, "correct": correct, "wrong": wrong,
           "unmatched": unmatched, "per_item_correct": per_item, "misses": misses,
           "negatives": len(MUST_NOT_MERGE), "false_merges": false_merges,
           "adversarial": adversarial()}
    print({k: v for k, v in out.items()
           if k not in ("misses", "per_item_correct", "adversarial")})
    for kind, row in out["adversarial"]["by_kind"].items():
        print("adversarial", kind, row)
    print("adversarial total", out["adversarial"]["total"])
    for m in misses:
        print(m)
    save("exp9_normalize", out)
    return out


if __name__ == "__main__":
    main()
