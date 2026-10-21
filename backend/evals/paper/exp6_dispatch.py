"""Experiment 6: does staging offers in time do what ranking cannot?

The same simulated semesters (campus.py, ROUTINE regime) are dispatched three
ways:

  broadcast   every nearby runner is told at once, in trust order (the
              ordering alone carries the social preference)
  staged      production: friends and friends-of-friends first, wider circle
              at +45 s, everyone at +90 s, via the real scheduler cadence
  sequential  one runner at a time in trust order, 30 s each
  staged_original
              staged, under the scheduler rule before the review fix: an
              errand whose first offer went out unrestricted (tier 0) was
              never widened, so it expired if nobody in the first radius
              accepted

Runner willingness and response delay are drawn per (errand, runner), so a
given runner behaves identically under every policy; only when they are told
differs. No graph database is involved.

Also reported, for the staged policy: how the 5 % of socially blind
(exploring) rounds differ from the rest, which is the service cost of keeping
collusion evidence interpretable.

Run: python -m evals.paper.exp6_dispatch
"""

from __future__ import annotations

from dataclasses import replace
from statistics import median

from evals.paper.campus import Campus, Config, Semester
from evals.paper.common import ci95, save


def stats(errands, campus, only=None) -> dict:
    rows = [e for e in errands if e["kind"] == "normal" and (only is None or only(e))]
    done = [e for e in rows if e["winner"] is not None]
    waits = sorted(e["wait_s"] for e in done)
    near = [e for e in done if e["winner_hops"] <= 2]
    direct = [e for e in done if e["winner_hops"] == 1]
    benign = [e for e in done if campus.kind[e["req"]] == "benign"]
    benign_in = [e for e in benign if campus.group_of[e["winner"]] == campus.group_of[e["req"]]]
    return {
        "errands": len(rows),
        "expired_rate": 1 - len(done) / len(rows) if rows else 0.0,
        "within_2_hops": len(near) / len(done) if done else 0.0,
        "direct_friend": len(direct) / len(done) if done else 0.0,
        "benign_in_group": len(benign_in) / len(benign) if benign else 0.0,
        "wait_median_s": median(waits) if waits else None,
        "wait_p90_s": waits[int(0.9 * len(waits))] if waits else None,
    }


def tier0(errands) -> dict:
    rows = [e for e in errands if e["kind"] == "normal" and e["first_tier"] == 0]
    done = [e for e in rows if e["winner"] is not None]
    return {"tier0_errands": len(rows),
            "tier0_expired_rate": 1 - len(done) / len(rows) if rows else 0.0}


POLICIES = {
    "broadcast": {"dispatch": "broadcast"},
    "staged": {"dispatch": "staged"},
    "staged_original": {"dispatch": "staged", "widen_open_offers": False},
    "sequential": {"dispatch": "sequential"},
}


def main(seeds=tuple(range(1, 31))) -> dict:
    out = {"seeds": len(seeds), "policies": {}, "exploring": {}}
    per = {p: [] for p in POLICIES}
    explore_split = {"exploring": [], "regular": []}
    for s in seeds:
        base = Config(seed=s)
        campus = Campus(base)
        for policy in per:
            sem = Semester(campus, replace(base, **POLICIES[policy]))
            sem.run()
            st = {**stats(sem.errands, campus), **tier0(sem.errands)}
            per[policy].append(st)
            print(s, policy, {k: round(v, 3) if isinstance(v, float) else v
                              for k, v in st.items()}, flush=True)
            if policy == "staged":
                explore_split["exploring"].append(
                    stats(sem.errands, campus, only=lambda e: e["exploring"]))
                explore_split["regular"].append(
                    stats(sem.errands, campus, only=lambda e: not e["exploring"]))

    def agg(rows):
        keys = [k for k in rows[0] if rows[0][k] is not None]
        return {k: {m: (round(v, 4) if isinstance(v, float) else v)
                    for m, v in ci95([r[k] for r in rows]).items()}
                for k in keys}

    out["policies"] = {p: agg(v) for p, v in per.items()}
    out["exploring"] = {k: agg(v) for k, v in explore_split.items()}
    for p, v in out["policies"].items():
        print(p, v)
    for k, v in out["exploring"].items():
        print("staged", k, v)
    save("exp6_dispatch", out)
    return out


if __name__ == "__main__":
    main()
