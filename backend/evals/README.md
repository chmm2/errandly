# Language-channel evaluation

Measures whether the fraud language channels are any *good*. Separate from
`backend/tests/`, which tests whether they are *safe* — that no provider means
no opinion, that injected text stays fenced, that a low score clears nobody.
Those are deterministic and belong in CI. These numbers are not and do not.

```bash
docker compose exec -T backend python -m evals.run_eval
docker compose exec -T backend python -m evals.run_eval --repeats 5
docker compose exec -T backend python -m evals.run_eval --channel reviews
docker compose exec -T backend python -m evals.run_eval --case genuine-but-terse
docker compose exec -T backend python -m evals.run_eval --json /app/evals/last_run.json
```

Needs a model configured — `LLM_PROVIDER=ollama` with Ollama running, or an
Anthropic key. Exits non-zero if the model would clear a farmed case or fail a
control, so it can gate a release. It never gates on the headline rate.

## Reading the report

Four numbers, in descending order of how much they matter:

**Control failures.** Honest groups the model would not clear — the terse
writers, the creature-of-habit orderer, the runner whose friends rate without
commenting. The channel exists to *reduce* false positives on real friend
groups. If it fails these it is adding suspicion to innocent people, and a
channel that does that is worse than no channel.

**False clearance.** Farmed cases called genuine. This is the model arguing to
clear a real ring. Want zero. Watch the `adversarial` cases especially: those
are farmed histories written by someone who read the rules and wrote well. If
the model clears them, writing well defeats the channel, which would make it
security theatre.

**Score separation.** Mean primary score on genuine minus farmed. A separation
near zero means the channel is not discriminating at all, whatever the pass/fail
column says. Negative is worse than useless.

**Stability.** Whether a verdict changes between repeats on identical input. A
channel that answers differently each time cannot support a threshold. At
`OLLAMA_TEMPERATURE=0.0` this should be zero; if it is not, the thresholds in
`SemanticVerdict.exculpatory` are resting on noise.

`injections reported` is crude — it substring-matches `injection_markers`
against the observations. It undercounts a model that notices the injected text
but describes it in its own words rather than naming it as manipulation, so read
a low number as "look at the raw observations", not as a hard failure. Use
`--json` and inspect. `injections resisted` is exact and is the one that matters.

## The provenance rule

Every case carries `"source"`.

- `synthetic` — written alongside the system, by us. Separation on these shows
  the channel works end to end and catches regressions when a prompt changes.
  **They cannot support an accuracy claim.** We wrote the questions and the
  answer key; nothing was held out.
- `pilot` — real histories from the deployment, labelled by a human.

The harness refuses to print a headline accuracy figure until there are at least
`MIN_PILOT_CASES` pilot cases, and prints the caveat at the bottom of every run.
This is deliberate: the easiest way to end up with an indefensible number in a
paper is to build a test set, score well on it, and forget who wrote it.

## Adding pilot cases

The labelling must be blind, or it is not evidence:

1. Export real flagged clusters — `FraudFlag` rows with `rule='COLLUSION_RING'`,
   and the errands joining their `details.members`. `semantics.gather_evidence`
   already returns exactly the per-errand shape the case file wants.
2. Strip `details.semantic` before anyone looks. **The labeller must not see
   what the model said.** If they do, the label is contaminated and the case is
   worthless.
3. Have a human — ideally two, and record where they disagree — label each
   `genuine` or `farmed` from the errand text and whatever ground truth exists
   (an admin decision, a confession, a refund).
4. Add with `"source": "pilot"`, and set `"probes": ["control"]` on any case
   that is an honest friend group. Those are the ones worth the most.

Disagreement between labellers is a result, not a problem to tidy away. If two
humans cannot agree whether a history reads as genuine, that is the ceiling on
what the model can be expected to do, and the paper should say so.

## Case schema

```jsonc
{
  "id": "unique-slug",
  "label": "genuine" | "farmed",     // ground truth
  "source": "synthetic" | "pilot",
  "probes": ["control", "adversarial", "injection", "false-positive"],
  "note": "why this case exists and what it probes",
  "injection_markers": ["ignore", "instruction"],  // injection cases only
  "evidence": [ /* semantics.json: gather_evidence() shape */ ],
  "reviews":  [ /* reviews.json: gather_reviews() shape */ ]
}
```

A case below `MIN_ERRANDS_FOR_JUDGEMENT` (6) or `MIN_REVIEWS_FOR_JUDGEMENT` (4)
is recorded as an abstention rather than run, matching what production would do
with the same evidence.

## What the harness reuses from production

The prompt builders, the Pydantic schemas, the provider layer, the system
prompts (`CLUSTER_SYSTEM` / `REVIEW_SYSTEM`), and the `exculpatory` rule on the
verdict dataclasses. Only the database gather step is replaced, by the case
file — which is the point, since the evidence has to be controlled.

So if someone edits a prompt, these numbers move. That is the intended
behaviour: this is the regression net for prompt changes, which are otherwise
completely untested.
