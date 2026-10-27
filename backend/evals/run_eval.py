"""Offline evaluation for the language channels.

Not a test. It talks to a real model, takes minutes, and its numbers move
between runs — everything pytest must never do. `backend/tests/test_semantics.py`
covers the contract (no provider means no opinion, injected text stays fenced, a
low score clears nobody); this measures whether the model is any *good*, which
is a different question and cannot be asserted in CI.

Run it:

    docker compose exec -T backend python -m evals.run_eval
    docker compose exec -T backend python -m evals.run_eval --repeats 5
    docker compose exec -T backend python -m evals.run_eval --channel reviews
    docker compose exec -T backend python -m evals.run_eval --json out.json

What it reuses from production, deliberately: the prompt builders, the Pydantic
schemas, the provider layer in `core/llm.py`, and the `exculpatory` rule on the
verdict dataclasses. Only the DB gather step is replaced — by the case file,
which is the whole point, since the evidence has to be controlled and labelled.
If the prompts drift, these numbers drift with them, which is what you want.

**On what these numbers are worth.** Cases marked `"source": "synthetic"` were
written alongside the system by the people who built it. Separation on them
demonstrates the channel functions end to end. It is *not* an accuracy result
and must not be reported as one: we wrote the questions and the answer key, and
the model was never held out from anything. Only `"source": "pilot"` cases —
real histories from the deployment, labelled by a human who was not choosing
them to make a point — support a claim about accuracy. The report says so at
the bottom every time, and refuses to print a headline figure until there are
enough of them.

The two numbers that actually matter are not the ones that look best:

  * **false clearance rate** — farmed cases the model called genuine. This is
    the channel arguing to clear a real ring. Want zero.
  * **control failures** — honest groups the model would not clear, especially
    the terse and repetitive ones. The channel's entire justification is
    reducing false positives on real friend groups; failing here means it is
    adding suspicion to innocent people instead of removing it.

A run that scores well on the obvious cases and fails the controls is worse
than no channel at all, so the report leads with the controls.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core import llm
from app.modules.fraud.semantics import (
    CLUSTER_SYSTEM,
    MAX_TOKENS,
    MIN_ERRANDS_FOR_JUDGEMENT,
    MIN_REVIEWS_FOR_JUDGEMENT,
    REVIEW_SYSTEM,
    ClusterAssessment,
    ReviewAssessment,
    ReviewVerdict,
    SemanticVerdict,
    build_prompt,
    build_review_prompt,
)

CASES_DIR = Path(__file__).parent / "cases"

# How many labelled pilot cases before a headline accuracy figure is printed at
# all. Not a statistical threshold — it is deliberately a low bar that the
# synthetic set cannot clear, so the report cannot accidentally be quoted as an
# accuracy result while the set is still all hand-written.
MIN_PILOT_CASES = 20


@dataclass
class Outcome:
    """One model call against one case."""

    score: int | None = None
    cleared: bool | None = None
    observations: list[str] = field(default_factory=list)
    seconds: float = 0.0
    abstained: bool = False
    reason: str = ""


@dataclass
class CaseResult:
    case: dict
    outcomes: list[Outcome]

    @property
    def label(self) -> str:
        return self.case["label"]

    @property
    def source(self) -> str:
        return self.case.get("source", "synthetic")

    @property
    def probes(self) -> list[str]:
        return self.case.get("probes", [])

    @property
    def scores(self) -> list[int]:
        return [o.score for o in self.outcomes if o.score is not None]

    @property
    def clearances(self) -> list[bool]:
        return [o.cleared for o in self.outcomes if o.cleared is not None]

    @property
    def mean_score(self) -> float | None:
        return statistics.mean(self.scores) if self.scores else None

    @property
    def cleared(self) -> bool | None:
        """Majority verdict across repeats. None if the model never answered."""
        if not self.clearances:
            return None
        return sum(self.clearances) * 2 > len(self.clearances)

    @property
    def flipped(self) -> bool:
        """Did the verdict change between repeats? Instability is itself a
        finding: a channel that answers differently on identical input cannot
        support a threshold."""
        return len(set(self.clearances)) > 1

    @property
    def correct(self) -> bool | None:
        """Genuine cases should be cleared; farmed cases should not."""
        if self.cleared is None:
            return None
        return self.cleared if self.label == "genuine" else not self.cleared

    @property
    def named_the_injection(self) -> bool:
        """Whether any run reported the injection attempt in observations."""
        markers = [m.lower() for m in self.case.get("injection_markers", [])]
        if not markers:
            return False
        for outcome in self.outcomes:
            blob = " ".join(outcome.observations).lower()
            if any(m in blob for m in markers):
                return True
        return False


# ---------------------------------------------------------------- running


async def _run_semantics(case: dict) -> Outcome:
    evidence = case["evidence"]
    if len(evidence) < MIN_ERRANDS_FOR_JUDGEMENT:
        return Outcome(
            abstained=True,
            reason=f"only {len(evidence)} errands, production needs {MIN_ERRANDS_FOR_JUDGEMENT}",
        )

    started = time.time()
    parsed = await llm.structured(
        ClusterAssessment,
        system=CLUSTER_SYSTEM,
        prompt=build_prompt(evidence),
        max_tokens=MAX_TOKENS,
    )
    seconds = time.time() - started

    if parsed is None:
        return Outcome(seconds=seconds, abstained=True, reason="model returned nothing usable")

    verdict = SemanticVerdict(
        assessment=parsed, errands_considered=len(evidence), model=llm.model_name()
    )
    return Outcome(
        score=parsed.coherence,
        cleared=verdict.exculpatory,
        observations=list(parsed.observations),
        seconds=seconds,
    )


async def _run_reviews(case: dict) -> Outcome:
    reviews = case["reviews"]
    if len(reviews) < MIN_REVIEWS_FOR_JUDGEMENT:
        return Outcome(
            abstained=True,
            reason=f"only {len(reviews)} reviews, production needs {MIN_REVIEWS_FOR_JUDGEMENT}",
        )

    started = time.time()
    parsed = await llm.structured(
        ReviewAssessment,
        system=REVIEW_SYSTEM,
        prompt=build_review_prompt(reviews),
        max_tokens=MAX_TOKENS,
    )
    seconds = time.time() - started

    if parsed is None:
        return Outcome(seconds=seconds, abstained=True, reason="model returned nothing usable")

    verdict = ReviewVerdict(
        assessment=parsed, reviews_considered=len(reviews), model=llm.model_name()
    )
    return Outcome(
        score=parsed.authenticity,
        cleared=verdict.exculpatory,
        observations=list(parsed.observations),
        seconds=seconds,
    )


RUNNERS = {"semantics": _run_semantics, "reviews": _run_reviews}


async def run_channel(channel: str, repeats: int, only: str | None) -> list[CaseResult]:
    path = CASES_DIR / f"{channel}.json"
    if not path.exists():
        print(f"  no case file at {path}, skipping")
        return []

    cases = json.loads(path.read_text(encoding="utf-8"))["cases"]
    if only:
        cases = [c for c in cases if c["id"] == only]
        if not cases:
            print(f"  no case with id {only!r} in {channel}")
            return []

    runner = RUNNERS[channel]
    results: list[CaseResult] = []

    for case in cases:
        outcomes: list[Outcome] = []
        for _ in range(repeats):
            outcomes.append(await runner(case))
        result = CaseResult(case=case, outcomes=outcomes)
        results.append(result)
        _print_case_line(result)

    return results


def _print_case_line(r: CaseResult) -> None:
    if r.cleared is None:
        verdict, mark = "abstained", "-"
    else:
        verdict = "cleared" if r.cleared else "not cleared"
        mark = "ok" if r.correct else "MISS"

    score = f"{r.mean_score:5.1f}" if r.mean_score is not None else "  n/a"
    flag = "  <- FLIPPED between repeats" if r.flipped else ""
    latency = statistics.median([o.seconds for o in r.outcomes if o.seconds]) if r.outcomes else 0
    print(
        f"  [{mark:>4}] {r.case['id']:<34} {r.label:<8} score {score}  "
        f"{verdict:<12} {latency:5.1f}s{flag}"
    )


# ---------------------------------------------------------------- reporting


def _rate(hits: int, total: int) -> str:
    if not total:
        return "n/a"
    return f"{hits}/{total} ({100 * hits / total:.0f}%)"


def report(channel: str, results: list[CaseResult]) -> dict[str, Any]:
    if not results:
        return {}

    genuine = [r for r in results if r.label == "genuine"]
    farmed = [r for r in results if r.label == "farmed"]
    judged = [r for r in results if r.cleared is not None]

    genuine_cleared = [r for r in genuine if r.cleared]
    falsely_cleared = [r for r in farmed if r.cleared]

    controls = [r for r in results if "control" in r.probes]
    control_failures = [r for r in controls if r.correct is False]
    adversarial = [r for r in results if "adversarial" in r.probes]
    injections = [r for r in results if "injection" in r.probes]
    flipped = [r for r in results if r.flipped]

    g_scores = [s for r in genuine for s in r.scores]
    f_scores = [s for r in farmed for s in r.scores]

    print()
    print(f"  {channel} summary")
    print("  " + "-" * 62)
    print(
        f"    genuine cleared      {_rate(len(genuine_cleared), len(genuine)):>18}"
        "   (want high)"
    )
    print(
        f"    FALSE CLEARANCE      {_rate(len(falsely_cleared), len(farmed)):>18}"
        "   (want 0)"
    )
    abstentions = len(results) - len(judged)
    print(f"    abstained            {_rate(abstentions, len(results)):>18}")

    if g_scores and f_scores:
        gap = statistics.mean(g_scores) - statistics.mean(f_scores)
        print(
            f"    score separation     {gap:>15.1f} pts   "
            f"(genuine {statistics.mean(g_scores):.0f} vs farmed {statistics.mean(f_scores):.0f})"
        )

    if controls:
        passed = len(controls) - len(control_failures)
        print(f"    controls passed      {_rate(passed, len(controls)):>18}")
    if adversarial:
        adv_ok = [r for r in adversarial if r.correct]
        print(f"    adversarial passed   {_rate(len(adv_ok), len(adversarial)):>18}")
    if injections:
        obeyed = [r for r in injections if r.cleared]
        named = [r for r in injections if r.named_the_injection]
        resisted = len(injections) - len(obeyed)
        print(f"    injections resisted  {_rate(resisted, len(injections)):>18}")
        print(f"    injections reported  {_rate(len(named), len(injections)):>18}   (observations)")
    if flipped:
        unstable = _rate(len(flipped), len(results))
        print(f"    UNSTABLE             {unstable:>18}   (verdict changed)")

    if control_failures:
        print()
        print("    control failures — the channel is adding suspicion to honest groups:")
        for r in control_failures:
            print(f"      {r.case['id']}: {r.case['note'][:88]}")

    return {
        "channel": channel,
        "genuine_cleared": [len(genuine_cleared), len(genuine)],
        "false_clearance": [len(falsely_cleared), len(farmed)],
        "control_failures": [r.case["id"] for r in control_failures],
        "unstable": [r.case["id"] for r in flipped],
        "mean_genuine_score": statistics.mean(g_scores) if g_scores else None,
        "mean_farmed_score": statistics.mean(f_scores) if f_scores else None,
        "cases": [
            {
                "id": r.case["id"],
                "label": r.label,
                "source": r.source,
                "probes": r.probes,
                "scores": r.scores,
                "clearances": r.clearances,
                "cleared": r.cleared,
                "correct": r.correct,
                "flipped": r.flipped,
                "observations": [o.observations for o in r.outcomes],
                "seconds": [round(o.seconds, 2) for o in r.outcomes],
                "abstentions": [o.reason for o in r.outcomes if o.abstained],
            }
            for r in r_sorted(results)
        ],
    }


def r_sorted(results: list[CaseResult]) -> list[CaseResult]:
    return sorted(results, key=lambda r: (r.label, r.case["id"]))


def provenance_note(all_results: list[CaseResult]) -> None:
    """The part that keeps the numbers honest."""
    pilot = [r for r in all_results if r.source == "pilot"]
    synthetic = [r for r in all_results if r.source != "pilot"]

    print()
    print("=" * 68)
    print(f"  provenance: {len(synthetic)} synthetic, {len(pilot)} pilot")
    print("=" * 68)
    if len(pilot) < MIN_PILOT_CASES:
        print(
            f"  NOT AN ACCURACY RESULT. {len(pilot)} labelled pilot cases; "
            f"{MIN_PILOT_CASES} is the floor\n"
            "  before this prints a headline figure.\n"
            "\n"
            "  Synthetic cases were written alongside the system, by the people who\n"
            "  built it. Separation on them shows the channel works end to end and\n"
            "  catches regressions when a prompt changes. It says nothing about\n"
            "  accuracy on real campus data, because we wrote both the questions and\n"
            "  the answer key. Do not put these numbers in the paper as accuracy.\n"
            "\n"
            "  To get a real figure: export real flagged clusters from the pilot,\n"
            "  have a human label them WITHOUT seeing the model's answer, and add\n"
            "  them with \"source\": \"pilot\". See evals/README.md."
        )
    else:
        correct = [r for r in pilot if r.correct]
        print(f"  pilot accuracy: {_rate(len(correct), len(pilot))}")
        print("  Report alongside the false-clearance rate and the control results,")
        print("  never as a single headline number.")


# ---------------------------------------------------------------- entrypoint


async def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate the fraud language channels.")
    ap.add_argument("--channel", choices=["semantics", "reviews", "all"], default="all")
    ap.add_argument(
        "--repeats",
        type=int,
        default=3,
        help="runs per case; >1 measures whether the verdict is stable (default 3)",
    )
    ap.add_argument("--case", help="run a single case by id")
    ap.add_argument("--json", dest="json_out", help="write full results to this path")
    args = ap.parse_args()

    if not llm.configured():
        print("No model configured. Set LLM_PROVIDER=ollama (or an Anthropic key) in backend/.env.")
        return 2

    print()
    print(
        f"  provider {llm.provider()} | model {llm.model_name()} "
        f"| {args.repeats} run(s) per case"
    )
    print()

    channels = ["semantics", "reviews"] if args.channel == "all" else [args.channel]
    reports: list[dict] = []
    everything: list[CaseResult] = []

    for channel in channels:
        print(f"  {channel}")
        results = await run_channel(channel, args.repeats, args.case)
        everything.extend(results)
        rep = report(channel, results)
        if rep:
            reports.append(rep)
        print()

    provenance_note(everything)

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(
                {"provider": llm.provider(), "model": llm.model_name(), "reports": reports},
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\n  raw results written to {args.json_out}")

    # Non-zero when the model would clear a farmed case or fail a control, so
    # this can gate a release if you ever want it to. Never gate on the headline
    # rate: it moves between runs and would make the gate meaningless.
    harmful = any(rep["false_clearance"][0] or rep["control_failures"] for rep in reports)
    return 1 if harmful else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
