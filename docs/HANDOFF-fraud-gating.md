# Handoff — integrity gating & language-channel evals

For Chris. Covers two commits on `feat/payments-fraud-detection` on top of
`c1d8c2d`. Assumes `docs/SOCIAL_GRAPH.md` (yours, plus my §11) as background.

| | |
|---|---|
| Branch | `feat/payments-fraud-detection` |
| Commits | `643c865` gating, `12f61e9` evals |
| Tests | 170 pass (was 143), ruff clean |
| Migrations | none — no schema change |

---

## 1. Your failure-semantics rule: preserved

§6 of your doc asks:

> Only `{}` may filter anyone out of an offer... When fraud checks start gating
> candidates too, keep the same distinction.

Done, and the fraud lookups follow the same contract rather than merely not
breaking yours:

- `integrity.penalties()` returns `None` on any query failure → nobody is
  demoted. `{}` means "asked, nobody is flagged".
- `integrity.co_ringed_with()` returns `None` on failure → **nobody is
  excluded**. Callers check `if co_ringed:`, so `None` and the empty set both
  fall through to "exclude nobody" naturally.

`_safe_scores()` itself is untouched, and the `max_hops` filter still guards on
`scores is not None`. Two tests lock the failure direction specifically —
`test_a_database_failure_penalises_nobody` and
`test_a_failed_ring_lookup_excludes_nobody` — because that is the failure that
would quietly take runners off the platform for no reason.

## 2. What actually changed about matching

Your §8 and my §11 both say integrity gating is not done. That line is now
stale — but the gap was narrower than either of us wrote down.

Both ends of the ladder already reached matching. A `RUNNER_SUSPENDED` strike
sets `fraud_blocked_until`, `zrem`s the runner from the geo set, and
`runners/service.py:59` refuses to let them back online until it lapses. A
`REPUTATION_PENALTY` lowers `effective_reputation`, which `_rank_with_scores`
already read. What did nothing at all was an **OPEN, unreviewed flag** — raised
by a sweep, sitting in the admin console, changing nothing until a human
clicked.

Two mechanisms now:

**A demotion, for everyone flagged.** A fourth term in your formula, in metres
so it stays commensurable:

```
effective = distance − trust × 1500 − (rep − 3.5) × 800 + integrity_penalty
```

Severity 1/2/3 costs 300/700/1200m, decaying linearly over the same 30-day
window the strike ladder counts on, capped at 2000m total. Scaled so a
severity-3 flag is worth less than one friendship and about a star and a half —
a flagged runner at the door still beats a clean runner a kilometre away. The
cap is the load-bearing part: without it flags accumulate until the penalty
exceeds any plausible distance and the demotion becomes a ban nobody decided on.

**One narrow refusal to re-pair.** An errand is not offered to a runner sharing
an open `COLLUSION_RING` flag with *that specific requester*. Neither person is
excluded from anything else — both keep taking work from the rest of campus at
a rank cost and no more. It only declines to keep arranging the one
introduction whose money your cycle search found going round in a circle.

Only `OPEN` flags count. `UPHELD` ones feed `evaluate_pattern`, and the ladder
already lowers reputation, which already lowers rank; counting them here too
would punish one finding twice through two mechanisms.

## 3. What it reads from your graph

The dyad block reads `FraudFlag.details["members"]` on `COLLUSION_RING` rows —
which `sweep_collusion_rings` populates from the cycles it finds over your
`PAID` edges. So the path is: your projection writes `PAID` → the cycle search
finds a closed loop → a flag per member carrying the whole membership → one
indexed lookup on the requester yields everyone they were found circling with.

Worth knowing: **this is the first thing that acts on your edges automatically.**
Everything before it either annotated a flag or asked a human. If the projection
goes stale or double-writes `PAID`, the visible symptom is now runners quietly
not being offered specific people's errands, which is much harder to notice than
a wrong number on a screen. `sweep_collusion_rings` already skips rings whose
members are missing from Postgres, so that path is covered, but stale *edges*
are not.

## 4. I gated the escalation tiers too

`_offer_tier` in `workers/consumers.py` gates identically. Gating only the first
offer would have made the whole thing bypassable by waiting — a flagged runner
would just collect the broadened offer a tier later.

**One thing I did not fix, in your area:** `_offer_tier` calls
`_rank_with_scores(nearby, scores, None, penalties)` — passing `None` for
reputations. So provenance-weighted reputation reorders the *initial* offer and
is ignored on every timed escalation. That predates this work; I preserved the
behaviour rather than changing it silently. If it is deliberate, it deserves a
comment; if not, it is a one-line fix plus the first test that would ever touch
`_offer_tier`.

## 5. The eval harness, and bad news about the review channel

`backend/evals/` measures whether the language channels are any *good*.
`tests/test_semantics.py` only ever proved they were *safe*. Run:

```bash
docker compose exec -T backend python -m evals.run_eval --repeats 3
```

It reuses the production prompt builders, schemas, provider layer and the
`exculpatory` rule; only the DB gather step is swapped for a labelled case file.
Editing a prompt moves the numbers, which is the point — prompt changes were
otherwise untested entirely.

On `qwen2.5:7b`:

| | semantics | reviews |
|---|---|---|
| genuine cleared | 3/3 | **1/2** |
| false clearance | **1/3** | **1/3** |
| score separation | 41.7 pts | **−0.9 pts** |
| controls passed | 3/3 | **1/2** |
| adversarial passed | **0/1** | **0/1** |

**The review channel is not discriminating.** Genuine 55 against farmed 56 is
no signal, and that channel currently annotates every `RATING_FARMING` flag. It
also failed the blank-comments control: an honest runner whose friends rate
without writing scored 25 and was not cleared — the exact false positive the
channel exists to prevent, and the prompt warns the model about it in capitals.

Both channels clear a fraudster who writes well. The model praised the farmed
case for precisely the variety its author manufactured after reading the rules.

Injections were not obeyed (2/2) but never named as attacks — the earlier "and
reported in observations" claim does not reproduce.

Since everything the model produces is advisory and annotation-only, none of
this changes an automated outcome. It does mean the review reading in the admin
console should not be leaned on yet.

All eleven cases are synthetic — written alongside the system by us. The harness
refuses to print a headline accuracy figure until 20+ blind-labelled pilot cases
exist and says why on every run. `evals/README.md` has the procedure, including
why the labeller must not see the model's answer.

## 6. Open, and what I'd want from you

1. **Rings larger than 3** — still open, still your note. The dyad block
   inherits the limit exactly: a 4-member ring with no triangle produces no
   flag, so it gates nothing.
2. **`_offer_tier` reputations** — §4 above. Your call.
3. **Every constant here is unfitted** — 300/700/1200, the 2000m cap, the
   30-day decay. Same caveat as your §8. The pilot should set them; they are
   reasoned defaults scaled against your 1500 and 800.
4. **The review prompt** needs a pass, or the channel needs to be reported as a
   limitation. The harness is the place to iterate against.
5. **Stale lines to fix** when you next touch your doc: §8 and my §11 both say
   integrity gating is not done.

## 7. Where to look

| | |
|---|---|
| `backend/app/modules/fraud/integrity.py` | the whole gating policy, and why each bound is where it is |
| `backend/app/modules/errands/service.py:202` | first-offer dispatch |
| `backend/app/workers/consumers.py:337` | escalation tiers |
| `backend/tests/test_integrity_gating.py` | 27 tests; the last three drive the real offer path |
| `backend/evals/README.md` | how to read the numbers, how to add pilot cases |

Test suite, against the separate test DB — the dev DB has demo data worth
keeping:

```bash
docker compose exec -T -e DATABASE_URL="postgresql+asyncpg://errandly:errandly@db:5432/errandly_test" -e REDIS_URL="redis://redis:6379/1" backend python -m pytest tests/ -q
```
