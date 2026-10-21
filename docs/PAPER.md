# Paper framing — working draft

Status: framing and contributions are settled and literature-checked. The
evaluation is **not done**, and that is the only thing standing between this
and a submission. Marked ✅ / ⚠️ / ❌ throughout so nobody mistakes a plan for a
result.

---

## Title

**Trust Without Receipts: Reconciling Social-Graph Matching and Collusion
Detection in Catalogue-Free Peer-to-Peer Errand Platforms**

Alternatives, if a venue prefers a shorter hook:

- *One Graph, Two Purposes: When Social Closeness Is Both the Trust Signal and
  the Collusion Substrate*
- *No Catalogue, No Receipt: Inferential Fraud Control for Campus Errand
  Commerce*

---

## The thesis, in one sentence

When a delivery platform has no merchant catalogue and no receipts, every fraud
control becomes inferential rather than verified — and the social graph that
makes inference possible is the same structure that makes collusion easy, so
trust and fraud detection must be designed against each other rather than
separately.

---

## Why the setting is different (the gap that survives checking)

Every commercial delivery platform resolves price fraud by **knowing the
price**: DoorDash and Swiggy integrate restaurant menus, Instacart carries a
store catalogue and scans receipts. The merchant supplies ground truth.

A campus errand platform has none of that. Canteens and stationery shops have
no POS integration, publish no catalogue, and issue no receipts. A runner buys
an unpriced item with escrowed money and **reports what it cost**. The
requester cannot check. The platform cannot check.

So the price is not a fact to be validated; it is a **claim to be judged**.
Once that is true, every downstream control — reimbursement, reputation,
dispatch — rests on inference about people rather than verification of
documents. That is the setting this paper addresses, and we found no prior work
that targets it. Campus errand products with escrow exist (ErrandEarn, RunAm,
Swaply, CarryCome); **none of them addresses unverifiable expenditure**, and
that — not escrow, and not campus verification — is where the research problem
lives.

> ⚠️ Do **not** claim "no campus platform has escrow or verified identity."
> Several do. That claim is falsifiable in one search and would discredit the
> rest of the paper.

---

## Contributions

**C1 — Problem formulation.** Catalogue-free errand commerce, where
expenditure is unverifiable by construction, and fraud control is therefore
inferential end to end. We characterise the resulting attack surface.

**C2 — The trust/collusion tension, and a rule that resolves it.** In a closed
community the structure that identifies a trustworthy runner is the same
structure that makes collusion feasible: a tight friend group is simultaneously
the best trust signal and the best fraud substrate. We show that structural
closeness alone cannot separate a genuine friend group from a collusion ring —
the graphs are isomorphic — and that the discriminator is whether **value
circulates** inside the group. Structural closeness is therefore treated as
*capacity*, never as evidence, and is escalated only under money-flow
corroboration.

**C3 — A size-independent closure metric.** We show the local clustering
coefficient ranks the threat backwards: because it divides by `deg·(deg−1)`, a
4-person ring scores 0.5 while a 10-person benign hostel group scores 0.8. We
substitute an embeddedness ratio — internal over internal-plus-boundary edges,
computed over the neighbourhood excluding ego — which scores any fully closed
ring identically regardless of size. Measured: 0.700 for rings of size 3–10;
0.000 for a hub with eight mutually unacquainted friends.

**C4 — An attack class containing no forged data.** Reputation-repair
collusion, where a penalised runner restores their score through *genuine*
errands for *real* friends who leave *sincere* ratings. No fake profile, no
purchased review, no bot: every datum is authentic, so shilling-attack
detectors — which hunt inauthenticity — find nothing. We show the separating
signal is the joint distribution over rater identity, rating timing relative to
the penalty, and money circulation, and give a detector over it that discounts
**concentration of provenance** rather than friendship itself.

**C5 — A working implementation**, event-sourced and explainable by
construction, with an evaluation of the mechanism and an honest negative result
for one component.

---

## Threat model

A runner who wants to extract more than their work is worth, on a platform
where nothing they claim can be checked against a document.

| stage | move | control |
|---|---|---|
| 1 | inflate an unverifiable price | robust reference estimation + band |
| 2 | keep every claim just under the line | distribution-based "walking the line" detection |
| 3 | absorb the flag, lose reputation | strike ladder → rank demotion in metres |
| 4 | restore reputation via genuine errands for friends | provenance-weighted reputation |
| 5 | circulate the same money inside the group | closed-cycle detection over `PAID` edges |
| 6 | make farmed errands look real | semantic channel (advisory) |

The loop matters: reputation **gates access to work**, so repair is
economically rational, not vanity. That is what makes stages 4–6 a real attack
rather than a hypothetical.

---

## Honest prior-art positioning

State these explicitly in Related Work. Naming your own prior art is what makes
reviewers trust the parts you do claim.

| our mechanism | established field — cite it |
|---|---|
| reference-price estimation from claims | truth discovery / truth inference |
| several valid prices per item (vendors differ) | multi-truth discovery |
| "the estimator learns to accept the fraud it polices" | **performative prediction** (canonical example: house-price models moving house prices) |
| one-runner-one-vote, MAD rejection | robust / Byzantine-resistant aggregation |
| claim-vs-reference bands | marketplace price anomaly detection (MoatPlus) |
| hop-decayed trust over a social graph | graph-based trust evaluation (Jiang et al.) |
| social trust in worker selection | trust-aware task assignment (CAT, TruthTrust, Fu & Liu) |
| collusive rating inflation | shilling-attack detection |
| cycle detection for fraud rings | graph AML / fraud-ring literature |

**What is ours is the composition and the tension (C2), the metric result (C3),
and the no-forged-data attack class (C4).** The price estimator is an
engineering instance of known methods — it belongs in the paper as supporting
material, never as the headline.

---

## Structure

1. **Introduction** — catalogue-free setting; price as claim; the tension
2. **Related work** — the table above, positioned honestly
3. **Threat model** — the six-stage loop
4. **Design**
   4.1 trust propagation and staged dispatch
   4.2 embeddedness and the closure metric (C3)
   4.3 money-flow circulation and closed cycles (C2)
   4.4 provenance-weighted reputation (C4)
   4.5 reference-price estimation under performativity
   4.6 the language channel, and why it is advisory only
5. **Implementation** — event-sourced, Postgres authoritative + Neo4j derived,
   explainability by construction
6. **Evaluation** — ❌ see below
7. **Limitations**
8. **Conclusion**

---

## Evaluation — what exists and what does not

✅ **Have.** Closure vs clustering across ring sizes 3–10 (C3). Circulation and
trust on isomorphic triangles (C2). Farming resistance curves from the
reputation weighting. A language-channel eval harness with a published negative
result.

❌ **Need.** The ablation. Generate campus-like graphs, plant rings of size 3–8
at varying circulation, and compare:

| condition | expected failure |
|---|---|
| distance only | baseline |
| structure only | flags genuine close-knit groups |
| money only | misses rings below the circulation knee |
| **conjunction** | both hold |
| clustering coefficient instead of closure | fails on small rings |
| pooled vs vendor-hierarchical reference price | false positives on honest runners at expensive vendors |

This single study tests C2 and C3 directly, produces baselines, and converts
~15 unfitted constants into swept parameters. It needs no pilot users.

⚠️ **Also state as limitations:** ring detection is limited to 3-cycles;
friendship is *declared*, so a ring that never friends each other is invisible;
the rating discount caps at 0.75, so ~100 farmed ratings eventually overtake 20
honest ones; the reference price has no vendor dimension; every threshold is
unfitted; all eval cases are synthetic.

---

## Venue

Realistic target: a Scopus-indexed conference — comfortable with the ablation
done, defensible without it. Frame as a **systems-and-measurement** paper, not
a theory paper. Top-tier venues (WWW, ICWSM, CSCW, AsiaCCS) would want real
pilot data and larger scale.
