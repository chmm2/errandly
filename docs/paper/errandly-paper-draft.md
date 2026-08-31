# Trust Without Receipts: Reconciling Social-Graph Matching and Collusion Detection in Catalogue-Free Peer-to-Peer Errand Platforms

**Chris Martin Mattam, Ujjwal Gogoi, Sanskriti Sajlal**
School of Computer Science and Engineering, Vellore Institute of Technology, Vellore, India

> **Draft status.** Numbers marked ✅ are measured and reproducible from this
> repository. Numbers marked ⬜ are placeholders for the evaluation described in
> §VI-B, which has not been run. Do not submit with any ⬜ remaining.
> Every reference needs its volume/page/DOI completed before submission —
> they are listed here by author, title, venue and year only.

---

## Abstract

Peer-to-peer delivery platforms control reimbursement fraud by knowing what
things cost: they integrate merchant catalogues or point-of-sale systems, so a
courier's claimed expenditure can be checked against a record. Campus errand
platforms have no such record. Canteens and stationery shops publish no
catalogue and issue no receipts, so a runner's reported spend on an unpriced
item is unfalsifiable, and every downstream control — reimbursement,
reputation, dispatch priority — must be inferred from behaviour and
relationships rather than verified against a document.

We present Errandly, a campus errand platform built for this
*catalogue-free* setting, and identify a structural conflict it creates. To
match errands to trustworthy runners we propagate trust over a student social
graph, where closeness raises trust. To detect collusion we search the same
graph, where closeness raises suspicion. The two uses are in direct opposition:
a tight friend group is simultaneously the strongest trust signal available and
the most effective substrate for reward farming. We show that structure alone
cannot resolve this — a genuine friend group and a collusion ring induce
isomorphic subgraphs — and that the separating evidence is whether settled value
*circulates* within the group. Accordingly, structural closeness is treated as
collusion *capacity* and never as evidence, escalating to a penalty only under
money-flow corroboration.

Two further results follow. First, the local clustering coefficient, the usual
measure of neighbourhood cohesion, ranks this threat backwards: because it
normalises by `deg(deg−1)`, a four-person ring scores 0.5 while a benign
ten-person residential group scores 0.8. We substitute an embeddedness ratio
that is invariant to group size ✅. Second, we characterise an attack class in
which no datum is forged: a penalised runner restores reputation through genuine
errands for real friends who leave sincere ratings. Shilling-attack detectors,
which search for inauthentic profiles and injected ratings, are inapplicable
because nothing is inauthentic. We show the separating signal lies in the joint
distribution over rater identity, rating timing relative to sanction, and money
circulation, and defend against it by discounting *provenance concentration*
rather than friendship.

The system is implemented as an event-sourced backend with an append-only audit
trail, deliberately using robust statistics and graph structure rather than
learned models, so that any accusation made against a student can be explained
to them.

**Index Terms** — trust propagation, collusion detection, social graphs,
reputation systems, peer-to-peer commerce, truth discovery, fraud detection.

---

## I. Introduction

### A. Motivation

A student in a hostel wants dinner from a canteen two blocks away. Another
student is walking past it. A platform that connects them captures value that
neither aggregator apps nor informal messaging groups serve well: aggregators
levy 21–24% commissions plus flat fees for a trip someone was already making,
and informal arrangements offer no recourse when either side defaults.

Building this is not, in itself, novel. Several campus errand products exist,
verify students by institutional email, and hold payment in escrow. What none of
them confronts is the consequence of the goods being *unpriced*.

### B. The catalogue-free setting

Commercial delivery platforms resolve expenditure fraud structurally. DoorDash
and comparable services integrate restaurant menus; grocery-delivery services
carry a store catalogue and capture receipts. In each case the merchant supplies
ground truth, and a courier's claim is validated against it.

A campus canteen supplies nothing. It has no point-of-sale integration, no
published catalogue, and issues no receipt for a ₹25 puff. When a runner buys an
item and reports what it cost, that report is the **only** record of the
transaction. The requester cannot verify it; neither can the platform.

This single property propagates through the whole system:

1. **Reimbursement** cannot be validated, only judged for plausibility.
2. **Plausibility** requires knowing what the item ought to cost, which must be
   estimated from the population of past claims — claims made by the same people
   the estimate will later police.
3. **Judgement** therefore attaches to *people*, not documents, so reputation
   becomes load-bearing.
4. **Reputation** gates access to work, which makes manipulating it
   economically rational.
5. **Manipulation** is easiest among people who know each other, which makes the
   social graph both the resource and the vulnerability.

The contribution of this paper is the analysis of step 5 and a mechanism that
survives it.

### C. Contributions

1. We formulate **catalogue-free errand commerce**, where expenditure is
   unverifiable by construction and fraud control is inferential end to end
   (§III).
2. We identify and resolve the **trust/collusion tension**: social closeness is
   simultaneously the best available trust signal and the best collusion
   substrate. We show structure alone cannot separate the cases and require
   money-flow corroboration before closeness is treated as risk (§IV-C).
3. We show the **local clustering coefficient ranks the threat backwards** and
   give a size-invariant embeddedness measure that does not ✅ (§IV-B).
4. We characterise **reputation repair without forged data** and give a
   detector based on provenance concentration, sanction-relative timing and
   money circulation (§IV-D).
5. We report an implementation and evaluation, including a **negative result**
   for one component (§VI).

---

## II. Related Work and Positioning

This section states plainly what each of our mechanisms inherits, and what we
change. We claim composition and analysis, not the underlying techniques.

### A. Comparison with prior work

| Area | Representative prior work | What it establishes | What we change |
|---|---|---|---|
| Graph-based trust | Jiang *et al.* [1] | Trust propagates over social paths and decays with hop distance | We add a *closure discount*: trust arriving through a closed neighbourhood is worth less, inverting the usual assumption that cohesion implies trustworthiness |
| Social trust in matching | Chiou & Tu [2]; Fu & Liu [3] | Weighting by raters' social closeness improves trust estimates; trust can be a formal objective in task assignment | Prior work *ranks* by trust. We show ranking is near-inert when offers are broadcast simultaneously, and stage offers **in time** by social distance instead |
| Escrow for P2P fraud | [4] | Structured hold-and-release reduces fraud | Escrow assumes the amount is known. We address the case where the amount itself is the contested claim |
| Price anomaly detection | Sarpal *et al.* [5] | Statistical price bounds from historical and proximate prices flag outliers at scale | Built for structured SKUs with known catalogue prices. Ours must estimate the reference from adversarial self-reports, with no catalogue |
| Marketplace fraud features | Maranzato & Pereira [6] | Behavioural and pricing features separate fraudulent from honest sellers | Their features are computed *post hoc*; ours feed back into dispatch, which creates the reputation-repair incentive we then have to defend |
| Truth discovery | Li *et al.* [7] | Infer a latent true value from conflicting sources by estimating source reliability | Our estimator is an instance of this. Our addition is Sybil-and-volume resistance by construction: per-source medians before cross-source aggregation |
| Multi-truth discovery | Lin & Chen [8] | Objects may legitimately have several true values | Directly relevant: an item genuinely has different prices at different vendors. We treat this as a covariate (vendor) rather than a value set, and pool hierarchically |
| Performative prediction | Perdomo *et al.* [9] | Model outputs influence the data the model is later trained on | Names our estimator's central risk exactly. We contribute concrete mitigations in a deployed system rather than a theoretical treatment |
| Robust aggregation | Byzantine-resistant estimators [10] | Medians and trimmed means resist a bounded fraction of adversarial inputs | We apply MAD-based rejection and per-runner vote limiting, and note the known weakness: coordinated low-magnitude attacks defeat median defences |
| Shilling attacks | Zhang *et al.* [11] | Collusive rating manipulation is detectable from rating patterns, group lockstep and profile signatures | **All of this assumes forged data.** Our attack forges nothing — real friends, real errands, sincere ratings — so these detectors do not apply (§IV-D) |
| Graph AML / fraud rings | [12] | Cycles and dense communities in transaction graphs indicate collusion | Cycle detection is standard. Our contribution is *conjunction*: a cycle is acted on only where the same graph also shows social closure, and closure only where money circulates |

### B. The gap

Prior work treats these as separate problems. Trust-aware matching literature
uses the social graph to *find* good workers. Fraud literature uses transaction
graphs to *catch* bad ones. To our knowledge no prior system uses one social
graph for both purposes, and consequently none confronts the contradiction that
arises when it does: the same edge that raises a runner's dispatch priority also
raises the likelihood that money moving along it is circular.

We also find no prior treatment of unverifiable expenditure in peer delivery.
Existing campus platforms provide verified identity and escrow but assume the
claimed amount is correct.

---

## III. Threat Model

We assume a runner who is a genuine, email-verified student, acting alone or
with genuine friends, seeking to extract more value than their work is worth. We
do **not** assume forged identities: institutional email verification makes
Sybil creation costly, and — importantly — the attacks below do not require it.

The attacker's campaign proceeds in six stages, each with a corresponding
control:

| Stage | Attacker move | Control (§) |
|---|---|---|
| 1 | Inflate the reported price of an unpriced item | Robust reference estimation with admin-bounded band (IV-E) |
| 2 | Keep every claim just below the flagging line | Distribution-based detection of clustering against the threshold (IV-E) |
| 3 | Accept the flag; reputation falls; dispatch priority falls | Strike ladder; rank demotion (IV-F) |
| 4 | Restore reputation through genuine errands for friends | Provenance-weighted reputation (IV-D) |
| 5 | Circulate value within the group so the ratings above cost nothing | Closed-cycle detection over settlement edges (IV-C) |
| 6 | Make farmed errands resemble genuine ones | Semantic channel, advisory only (IV-G) |

The loop closes because reputation gates access to work: repairing it is not
vanity but a precondition for reaching new victims. Stage 4 is therefore
economically compelled, which is what makes it worth defending against.

**Out of scope.** Physical collusion with shopkeepers (a forged verbal price),
account sharing, and coercion. We note these as limitations (§VII).

---

## IV. System Design

### A. Architecture

Errandly is a modular monolith over PostgreSQL/PostGIS, Redis, Kafka and
MongoDB, with a Neo4j social graph maintained as a **derived read model**.
Friendship state is authoritative in PostgreSQL; a transactional outbox
publishes changes to Kafka, and a dedicated consumer projects them into Neo4j.

Two properties follow, and both are deliberate. First, no request path writes to
the graph, so a graph failure cannot fail a user action. Second, the graph is
reconstructible from the event log, so it may be discarded and rebuilt. All
graph reads are guarded by a circuit breaker returning a neutral value; losing
the graph degrades matching to distance-only ordering, which is the behaviour
the platform had before the graph existed.

### B. Trust propagation and the closure discount

Trust from requester *u* to candidate runner *v* decays with friendship hop
distance in the manner of [1]:

```
trust(u,v) = δ^(hops−1) × (1 − closure_penalty(via))      δ = 0.45
```

Measured decay ✅: 1.0000, 0.4500, 0.2025, 0.0911 at one through four hops.
Beyond four hops a candidate is treated as a stranger.

The second factor is our departure from [1]. Trust arriving through a *closed*
neighbourhood is discounted, because closure indicates the endorsement carries
little information from outside the group.

**Choice of measure.** The natural candidate is the local clustering
coefficient. It is unsuitable here, and instructively so. Because it normalises
by `deg(deg−1)`, its value depends on group size in the wrong direction:

| Structure | Clustering coefficient | Interpretation |
|---|---|---|
| 4-person ring, one external tie | 0.50 | small ring, high risk, **low score** |
| 10-person residential group | 0.80 | large benign group, **high score** |

The metric ranks the more dangerous configuration below the more benign one.
Since collusion rings are small by nature — they require coordination and trust
among members — this is precisely backwards.

We therefore define **closure** as an embeddedness ratio over the neighbourhood
*excluding ego*:

```
closure(u) = internal / (internal + boundary)
```

where *internal* counts edges among *u*'s neighbours and *boundary* counts edges
from those neighbours to nodes outside the neighbourhood. Excluding *u* is
necessary: including it counts *u*'s own spokes as internal, which makes a star
— the maximally *open* structure — score as closed as a clique (0.889 against
0.875 in our measurements) ✅.

Measured, this is invariant to size ✅:

| Structure | closure | penalty |
|---|---|---|
| fully closed ring, n = 3…10 | 1.000 | 0.700 (cap) at every n |
| hub with 8 mutually unacquainted friends | 0.000 | 0.000 |

### C. Money-flow corroboration

Closure establishes *capacity* for collusion, never its occurrence. Three
roommates who genuinely take turns fetching dinner and three students farming
rewards from each other induce **isomorphic subgraphs**. No purely relational
measure can distinguish them.

The distinguishing evidence is whether value circulates. We project settlement
events into the graph as directed `PAID` edges (requester → runner, carrying
amount and timestamp) and derive two signals, deliberately kept separate:

**Circulation** — per user, the fraction of settled platform value exchanged
with their own friends. A gradient: it discounts trust, it does not accuse.
Suppressed below minimum value and transaction-count floors so that a new
student with two errands for a friend does not read as wholly internal.

**Closed cycles** — a directed `PAID` cycle whose members are pairwise friends,
requiring multiple circuits and a minimum value on the narrowest leg. This is a
specific accusation about identified people, so it raises a flag for human
review rather than acting autonomously. All members are flagged: the structure
is symmetric and identifies no ringleader.

It is worth being precise about *why* a cycle is suspicious, because the obvious
reading is wrong. The platform is a pure custodian: it holds a requester's funds
and releases them to the runner, and injects nothing. A closed cycle is
therefore **exactly zero-sum** — no participant gains a rupee by circulating
money, and no money is stolen in the cycle at all.

The motive is not extraction but **cost avoidance**. Manufacturing reputation
requires completed errands carrying good ratings, and ratings can only be relied
upon when the requester is a confederate — but each such errand costs that
confederate real money. Circulation removes that cost: when A pays B, B pays C
and C pays A, each has paid out approximately what they received, while the
group has produced three completed errands and three sincere five-star ratings
at a net cost of approximately zero.

The cycle is therefore not the fraud; it is what makes the reputation farming of
§IV-D economically sustainable. This distinguishes it sharply from an honest
friend group, whose money *leaks outward* to the wider campus and for whom
internal errands remain a genuine expense. It also explains why no funds are
withheld on a ring flag: nothing was misappropriated in the cycle. The
extraction occurs later, against strangers, using the priority that the
manufactured reputation buys.

**The conjunction is the mechanism.** Neither signal penalises alone. Closed but
not circulating is an ordinary friend group; circulating but open is someone who
trades with friends among many others. On identical three-person triangles:

| Configuration | circulation | member→member trust | flagged |
|---|---|---|---|
| value circulates internally | 1.00 | 0.05 | yes |
| value flows out to campus | 0.00 | 1.00 | no |

Accordingly the structural penalty caps at 0.70; only with money-flow
corroboration does it rise to 0.95. It never reaches 1.0, because a corroborated
group may contain a member who merely has friends.

### D. Reputation repair without forged data

Stage 4 of the threat model is the paper's second analytical contribution.

A penalised runner recovers by running errands for their own friends and
collecting five-star ratings. Every element is authentic: the friendship is
real, the errand was performed, the food was delivered, and the rating is
**sincere** — the friend genuinely was satisfied. There is no fabricated
profile, no purchased review, no automated behaviour.

This places the attack outside the shilling-detection literature [11], whose
methods search for inauthenticity: anomalous rating distributions, lockstep
timing among fake accounts, profile signatures. Applied here they find nothing,
because there is nothing false to find. No individual transaction is evidence of
anything.

The separating signal is distributional. We compute a rating profile per runner,
partitioned by whether the rater is a declared friend, and weight ratings by

```
w = 1                                  if rater is not a friend, or
                                       concentration ≤ 0.50
w = 1 − min(0.75, excess × 0.75)       otherwise
```

where `excess = (concentration − 0.50) / 0.50`. Crucially the discount attaches
to **concentration of provenance**, never to friendship itself: a runner rated
well by twenty strangers and five friends is unaffected. The score is then
shrunk toward a neutral prior by effective sample size, so a farmed reputation
becomes *low-confidence* rather than *low*, and matching treats an unproven
runner as unproven rather than as dishonest.

Measured effect ✅:

| Rating provenance | concentration | effective weight | ranked score |
|---|---|---|---|
| 20 friends, 0 strangers | 1.00 | 5.0 | 4.08 |
| 20 strangers, 0 friends | 0.00 | 20.0 | 4.57 |
| 15 strangers, 5 friends | 0.25 | 20.0 | 4.57 |

Twenty farmed ratings purchase the standing of five honest ones. Recovery
therefore requires strangers — which is the behaviour the platform wants to
restore.

Two independent detectors then flag farming outright: a **differential** (
friends rate the runner materially higher than strangers do) and a **burst** (
in-cluster praise arriving shortly after a sanction). The second requires no
stranger ratings at all, which matters because a runner who has lost stranger
work is exactly the one farming.

### E. Reference-price estimation under performativity

For unpriced items the platform maintains a reference price per campus item,
bounded by an administrator-set band. The estimator is an instance of truth
discovery [7], with three defences whose necessity follows from [9]:

1. **Per-runner vote limiting.** Each runner's own median is taken first, then
   the median across runners. A runner submitting an inflated claim two hundred
   times contributes a single value to the outer median; volume purchases no
   influence.
2. **Robust rejection before estimation.** MAD-based rather than
   standard-deviation-based, since an extreme claim inflates a standard
   deviation sufficiently to re-admit itself.
3. **A human-set band as a hard bound.** An estimate may move only within it;
   drift to an edge raises a proposal for review rather than silently widening
   the band. Claims previously adjudicated fraudulent are excluded from future
   estimation.

Without (1) and (3) the estimator is performative in the sense of [9]:
inflated claims raise the estimate, the raised estimate normalises the next
inflated claim, and the detector converges on accepting the fraud it exists to
detect.

Nothing here is learned. For a scalar with an adversary attached, robust
statistics is both adequate and *explainable* — a suspended student can be shown
the reference, the tolerance and their own claim.

**Known deficiency.** The reference is keyed on (campus, item) with no vendor
dimension, while prices genuinely differ between outlets. Pooling produces a
two-sided error: an honest runner buying at an expensive outlet appears
persistently elevated, while a fraudster at a cheap outlet is *better
camouflaged than an honest runner*. §VII describes the hierarchical correction.

### F. Staged dispatch

Prior work ranks candidates by trust [2], [3]. We observe that ranking is nearly
inert under simultaneous broadcast: all candidates in a dispatch round receive
the offer within milliseconds, so ordering a broadcast leaves a race that the
nearest stranger usually wins.

Social preference must therefore come from *when* each cohort is told. Offers
escalate over social distance on a timer — friends and friends-of-friends at
posting, out to four hops after 45 s, and unrestricted after 90 s — with each
tier recorded in the audit trail so that a restart cannot re-offer a tier. An
errand posted by a student with no nearby connections falls through immediately
to an open offer, since an unseen errand is worse than one taken by a stranger.

Within a tier, candidates are ordered by effective distance, with trust,
reputation and integrity penalties expressed in metres so the terms remain
commensurable:

```
effective = distance − trust×1500 − (rep−3.5)×800 + integrity_penalty
```

The integrity term is capped, and decays over the same window the strike ladder
uses. The cap is load-bearing: uncapped, accumulated flags would exceed any
plausible distance and silently convert a demotion into a ban that no
administrator decided.

### G. The language channel

Where structure and money answer *who* and *how much*, neither answers *what
for* — and content is the only remaining signal separating genuine reciprocal
errands from farmed ones. A locally-hosted language model reads errand text and
returns a schema-constrained verdict.

Three constraints govern it: it is **advisory only** and never raises a
severity; its useful direction is **exculpatory**, reducing false positives on
genuine friend groups, where error is cheapest; and all analysed text is
attacker-controlled, so it is fenced, labelled untrusted, and schema-constrained
such that a crafted note can at worst move a number a human reviews.

---

## V. Implementation

Approximately 170 backend tests pass ✅. The system runs as containerised
services: API, outbox relay, and workers hosting four Kafka consumer groups
(notifications, analytics, settlement, social-graph projection).

Every fraud-relevant decision is reconstructible from an append-only event log.
This is a deliberate stance rather than an artefact: the decisions in question
withhold money and suspend students, and an accusation a platform cannot explain
is one the accused cannot contest. It is also why learned models are confined to
the advisory channel of §IV-G.

---

## VI. Evaluation

### A. Measured results ✅

1. **Hop decay** behaves as specified: 1.0000 / 0.4500 / 0.2025 / 0.0911.
2. **Size invariance of closure**: fully closed rings score the 0.700 penalty
   cap at every size from 3 to 10 members; a hub with eight mutually
   unacquainted friends scores 0.000. The clustering coefficient, by contrast,
   scores the 4-ring at 0.50 and the 10-group at 0.80.
3. **Ego exclusion is necessary**: including ego scores a star at 0.889 against
   a ring at 0.875 — indistinguishable.
4. **Conjunction discriminates** on isomorphic triangles: circulation 1.00 vs
   0.00, member-to-member trust 0.05 vs 1.00.
5. **Farming resistance**: 20 farmed ratings yield a ranked score of 4.08
   against 4.57 for 20 honest ratings.
6. **Language-channel evaluation — a negative result.** Against a local
   `qwen2.5:7b`, the semantic channel separated genuine from farmed clusters by
   41.7 points, but the review channel achieved **−0.9** points of separation
   (genuine 55, farmed 56) and failed a blank-comment control. The channel is
   not discriminating and is reported as such. Prompt injections embedded in
   errand text were not obeyed (2/2). All eleven cases are synthetic and the
   harness refuses to report a headline accuracy figure until blind-labelled
   pilot cases exist.

### B. Planned evaluation ⬜ — not yet run

Generate campus-like social graphs by stochastic block model, plant collusion
rings of sizes 3–8 at varying circulation rates, include benign close-knit
groups as hard negatives, and report precision/recall for:

| Condition | Hypothesis |
|---|---|
| distance only | baseline |
| structure only | precision falls — benign groups flagged |
| money only | recall falls — sub-threshold rings missed |
| conjunction | both retained |
| clustering coefficient substituted | fails on small rings |
| pooled vs vendor-hierarchical reference | pooled produces false positives at expensive vendors |

This tests contributions 2 and 3 directly and converts approximately fifteen
hand-set constants into swept parameters.

---

## VII. Limitations

1. **Ring detection is limited to 3-cycles.** A four-member ring without an
   internal triangle raises no flag.
2. **Friendship is declared.** A ring whose members never friend each other is
   invisible to every social mechanism here. They forfeit dispatch preference,
   but escape the discount entirely.
3. **The rating discount is bounded at 0.75**, so approximately 100 farmed
   ratings eventually exceed 20 honest ones ✅. Volume defeats the weighting
   given sufficient patience, though the money circulation it requires is
   detectable by §IV-C.
4. **The reference price has no vendor dimension** (§IV-E). The correction is
   hierarchical pooling: a vendor-specific estimate shrunk toward the campus
   estimate in proportion to that vendor's sample size.
5. **Coordinated low-magnitude poisoning** defeats median-based defences, a
   known limitation of robust aggregation [10].
6. **All thresholds are unfitted.** They are reasoned defaults, not values
   derived from data.
7. **Evaluation is synthetic.** No pilot cohort has yet used the system.
8. Physical collusion with a shopkeeper, account sharing and coercion are out of
   scope.

---

## VIII. Conclusion

Removing the merchant catalogue from a delivery platform removes the ground
truth that every fraud control implicitly assumes, and forces those controls to
become inferential. Inference over a social graph then creates a conflict that
does not arise when trust and fraud detection are studied separately: the
closeness that identifies a trustworthy runner is the closeness that makes
collusion practical.

Our position is that structural closeness should be read as *capacity* and never
as evidence, with money-flow corroboration required before it carries a penalty;
that the usual measure of cohesion ranks this threat backwards and should be
replaced with a size-invariant one; and that the most difficult attacks in a
closed community contain no forged data at all, so detection must rest on the
joint distribution of authentic events rather than on the identification of
fakes.

---

## References

> ⚠️ Complete volume, number, pages and DOI for each before submission.

[1] W. Jiang, G. Wang, Md. Z. A. Bhuiyan, and J. Wu, "Understanding graph-based
trust evaluation in online social networks: Methodologies and challenges,"
*ACM Computing Surveys*, vol. 49, no. 1, 2016.

[2] S.-Y. Chiou and T.-Y. Tu, "A trusted mobile ride-hailing evaluation system
with privacy and authentication," *IEEE Access*, vol. 8, pp. 61929–61942, 2020.

[3] F. Donglai and L. Yanhua, "Trust-aware task allocation in collaborative
crowdsourcing model," *The Computer Journal*, vol. 64, no. 6, 2021.

[4] "An escrow-based peer-to-peer online payment system for fraud reduction,"
*Methods in Science and Technology Studies*, 2026.

[5] A. Sarpal, Q. Kang, F. Huang, Y. Song, and L. Wan, "A marketplace price
anomaly detection system at scale," arXiv:2310.04367, 2023.

[6] R. P. Maranzato and A. M. Pereira, "Feature extraction for fraud detection
in electronic marketplaces," in *Proc. IEEE Latin American Web Congress
(LA-Web)*, 2009.

[7] Y. Li *et al.*, "A survey on truth discovery," *ACM SIGKDD Explorations*,
2016. (arXiv:1505.02463)

[8] X. Lin and L. Chen, "Domain-aware multi-truth discovery from conflicting
sources," *Proc. VLDB Endowment*, vol. 11, no. 5, 2018.

[9] J. Perdomo, T. Zrnic, C. Mendler-Dünner, and M. Hardt, "Performative
prediction," in *Proc. ICML*, 2020. See also "Performative prediction: Past and
future," arXiv:2310.16608, 2023.

[10] "Data poisoning attacks and defenses to crowdsourcing systems,"
arXiv:2102.09171, 2021.

[11] F. Zhang *et al.*, "Shilling attack detection for recommender systems based
on credibility of group users and rating time series," *PLOS ONE*, vol. 13,
no. 5, 2018.

[12] Graph-based anti-money-laundering and fraud-ring detection. *Select a
specific citation — candidates include topology-agnostic temporal money
laundering detection, arXiv:2309.13662, 2023.*
