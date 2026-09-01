"""Chapters 3 and 4 — Technical Specification, Design Approach and Details."""

from docx_helpers import (
    body, bullet, chapter, figure, numbered, section, subsection, table,
)


def chapter_3(doc):
    chapter(doc, "3. Technical Specification")

    section(doc, "3.1 Requirements")

    subsection(doc, "3.1.1  Functional")
    bullet(doc, "Identity and verification",
           "Register with an institutional e-mail address, verify by one-time "
           "password, and recover access by a separate reset flow. Only verified "
           "accounts may post or accept errands.")
    bullet(doc, "Errand creation",
           "Post an errand in one of five categories — food, grocery, parcel, "
           "stationery, pharmacy — with a structured item list, per-item quantities, "
           "a drop location on a campus map, a reward, and an optional deadline.")
    bullet(doc, "Escrow",
           "Immobilise the reward plus expected purchase cost at the moment of "
           "posting, and refuse the order if the requester's balance is insufficient.")
    bullet(doc, "Geospatial matching",
           "Identify available runners near the drop point and rank them by effective "
           "distance, offsetting physical distance by social proximity, reputation and "
           "any open fraud penalty.")
    bullet(doc, "Tiered offering",
           "Offer first to runners within two social hops, widening on a timer to the "
           "whole campus so that a student with no connections is never stranded.")
    bullet(doc, "Contention control",
           "Publish an offer to all eligible runners simultaneously and award the "
           "errand to the first acceptance, with concurrent attempts rejected safely.")
    bullet(doc, "Live tracking and messaging",
           "Stream runner position and status transitions to the requester, and carry "
           "a private conversation between the two parties for the errand's lifetime.")
    bullet(doc, "Price claims",
           "Allow a runner to report the amount actually paid per item, and judge each "
           "claim against a reference price for that item at that store.")
    bullet(doc, "Settlement",
           "On confirmation of handoff, pay the runner their reward and eligible "
           "reimbursement, return any unspent surplus to the requester, and withhold "
           "any amount a fraud check refuses to release.")
    bullet(doc, "Ratings",
           "Permit the requester to rate a completed errand once, weighting that "
           "rating by its provenance when computing the reputation used for ranking.")
    bullet(doc, "Fraud detection",
           "Detect price inflation per claim, rating farming per runner and collusion "
           "rings per group, raising flags for human review rather than acting "
           "unilaterally.")
    bullet(doc, "Offer logging",
           "Record, for every dispatch round, the candidate set, each candidate's "
           "ranking terms, whether the round was socially blind, and which runner "
           "accepted.")
    bullet(doc, "Administrative review",
           "Present open flags to an administrator, who may uphold or dismiss each; "
           "the verdict releases or reclaims any withheld funds.")
    bullet(doc, "Wallet",
           "Show a derived balance, the amount currently held in escrow, and a "
           "chronological history of every movement with its reason.")

    subsection(doc, "3.1.2  Non-Functional")
    bullet(doc, "Latency",
           "An offer must reach candidate runners within roughly one second of "
           "posting; the ranking computation must therefore read pre-computed "
           "reputation and graph metrics rather than deriving them per request.")
    bullet(doc, "Correctness of money",
           "No sequence of retries, redeliveries or concurrent requests may pay a "
           "participant twice or release more than was held. This constraint takes "
           "precedence over availability on the settlement path.")
    bullet(doc, "Graceful degradation",
           "Failure of the social graph must reduce matching to distance ordering "
           "rather than halt it. Every graph read degrades to a neutral value, and "
           "unavailability is never interpreted as evidence against a user.")
    bullet(doc, "Auditability",
           "Every balance must be reconstructible from immutable entries, and every "
           "flag must carry the evidence that produced it.")
    bullet(doc, "Proportionality",
           "An unreviewed suspicion may demote a runner in ranking but must never "
           "remove them from the platform. Penalties are bounded so that accumulated "
           "suspicion cannot amount to an undecided ban.")
    bullet(doc, "Scalability",
           "The design must accommodate a campus population of tens of thousands "
           "without architectural change, and multiple campus tenants by partitioning "
           "on campus identity.")
    bullet(doc, "Security and privacy",
           "Credentials are stored only as hashes, handoff secrets are encrypted at "
           "rest, and a user's precise location is visible only to the counterparty of "
           "an active errand.")
    bullet(doc, "Maintainability",
           "The ranking formula must have exactly one implementation, shared by the "
           "matcher and the offer log, so that analysis cannot silently diverge from "
           "the policy it purports to describe.")

    section(doc, "3.2 Feasibility Study")

    subsection(doc, "3.2.1  Technical Feasibility")
    body(doc,
         "Every component is mature and open-source. PostgreSQL with PostGIS provides "
         "transactional integrity and geospatial indexing; Redis supplies the "
         "proximity index, distributed locks and publish/subscribe transport; Kafka "
         "decouples settlement and analytics from the request path; Neo4j holds the "
         "derived social graph; and Ollama runs a seven-billion-parameter language "
         "model locally, avoiding both per-call cost and the transmission of user data "
         "to third parties.")
    body(doc,
         "The principal technical risk is operational rather than algorithmic. The "
         "system depends on five data stores, and the derived graph can silently drift "
         "from the system of record if projection events are lost. This risk is "
         "mitigated by treating the graph as a rebuildable read model with an "
         "idempotent reconstruction routine, so that divergence is repairable rather "
         "than permanent. The team has demonstrated the full stack running under "
         "container orchestration on commodity hardware.")

    subsection(doc, "3.2.2  Economic Feasibility")
    body(doc,
         "Development cost is limited to student effort. Runtime cost is dominated by "
         "a single application server, a managed database and object storage; at campus "
         "scale this is within a small monthly budget, and the local language model "
         "removes what would otherwise be the largest recurring expense.")
    body(doc,
         "The platform's economics are deliberately non-extractive: the reward is paid "
         "by the requester to the runner, and the platform takes no cut in the present "
         "design. Sustainability would therefore come from a modest service fee or "
         "institutional sponsorship rather than from transaction margin. This matters "
         "for the fraud analysis, since a colluding group is avoiding cost and "
         "manufacturing reputation rather than extracting platform funds.")

    subsection(doc, "3.2.3  Social Feasibility")
    body(doc,
         "Adoption depends on trust rather than on features. The escrow design "
         "addresses the requester's principal fear — paying for an errand that is never "
         "run — while the reward and reimbursement guarantee address the runner's, "
         "which is fronting cash at a counter for someone who may not pay.")
    body(doc,
         "Two social risks are taken seriously in the design. First, a fraud flag is an "
         "accusation against a named student, so no detector acts alone and no "
         "unreviewed flag can exclude anyone. Second, preferential routing to friends "
         "risks entrenching existing social advantage; the maturity weighting and the "
         "exploration mechanism both limit how far social position alone can determine "
         "access to work.")

    section(doc, "3.3 System Specification")

    subsection(doc, "3.3.1  Hardware Specification")
    table(doc, ["Component", "Development", "Deployment (campus scale)"],
          [["Processor", "Quad-core x86-64, 2.5 GHz", "4 vCPU"],
           ["Memory", "16 GB", "16 GB"],
           ["Storage", "256 GB SSD", "100 GB SSD, provisioned IOPS"],
           ["GPU", "Not required", "Optional; accelerates local LLM inference"],
           ["Mobile device", "Android 10+ / iOS 15+ with GPS", "—"]],
          widths=[1.5, 2.4, 2.5], font=10)

    subsection(doc, "3.3.2  Software Specification")
    table(doc, ["Layer", "Technology"],
          [["Operating system", "Linux (containers); Windows/macOS for development"],
           ["Backend", "Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Alembic"],
           ["Mobile client", "React Native, Expo SDK 57, expo-router, React Query"],
           ["Web client", "React 18, Vite, React Router, TanStack Query"],
           ["Relational store", "PostgreSQL 16 with PostGIS"],
           ["Cache and transport", "Redis 7 — geospatial index, locks, pub/sub"],
           ["Event streaming", "Apache Kafka with a transactional outbox relay"],
           ["Document store", "MongoDB — chat history"],
           ["Graph store", "Neo4j 5 — derived social graph, Cypher"],
           ["Language model", "Ollama running qwen2.5:7b locally"],
           ["Maps", "Leaflet with OpenStreetMap tiles"],
           ["Notifications", "Firebase Cloud Messaging, Expo Push"],
           ["Testing", "pytest, pytest-asyncio, httpx"],
           ["Tooling", "Docker Compose, Ruff, Git"]],
          widths=[1.7, 4.7], font=10)


def chapter_4(doc):
    chapter(doc, "4. Design Approach and Details")

    section(doc, "4.1 System Architecture")
    body(doc,
         "Errandly is structured as a modular monolith over a polyglot persistence "
         "layer. A single FastAPI process hosts six domain modules with enforced "
         "boundaries — a module reaches another only through its service interface, "
         "never through its tables. This choice is deliberate for a project of this "
         "size: it preserves the transactional guarantees that the escrow path depends "
         "on, while keeping module boundaries clean enough that any of them could later "
         "be extracted into a separate service.")
    figure(doc, "fig_architecture.png", "Fig. 2. Errandly system architecture", width=6.4)
    body(doc,
         "Each store is chosen for a property the others lack. PostgreSQL is the system "
         "of record and the only authority on money. Redis answers proximity queries in "
         "constant time, arbitrates acceptance races through short-lived locks, and "
         "carries real-time messages. Kafka decouples work that must happen from work "
         "that must happen immediately. MongoDB holds chat, whose access pattern is "
         "append-and-scan. Neo4j holds the social graph, where the queries are "
         "variable-length path traversals that relational joins express poorly.")
    body(doc,
         "Two architectural decisions carry most of the system's correctness. The first "
         "is the transactional outbox: a domain event is written to an outbox table in "
         "the same database transaction as the state change that caused it, and a relay "
         "publishes it to Kafka afterwards. An event therefore cannot be lost if the "
         "publisher fails, nor emitted for a transaction that rolled back. The second "
         "is that Neo4j is a strictly derived read model. Nothing is authoritative "
         "there, every read degrades to a neutral value when the graph is unavailable, "
         "and the entire graph can be reprojected from PostgreSQL.")
    body(doc,
         "The Offer Log occupies a deliberate position in the diagram: it sits beneath "
         "the domain modules, written on the dispatch path but read by nothing on it. "
         "It is analytics infrastructure embedded in an operational system, and it is "
         "written best-effort so that a failure to record cannot prevent an errand from "
         "being offered.")

    section(doc, "4.2 Design")

    subsection(doc, "4.2.1  Trust-Aware Matching with Deliberate Exploration")
    body(doc,
         "Candidate generation is purely spatial: Redis returns the nearest available "
         "runners within three kilometres of the drop point. The social graph never "
         "widens this set; it only reorders it, so that a well-connected student cannot "
         "pull errands from across campus.")
    body(doc,
         "Ranking expresses every factor in a single unit — metres of effective "
         "distance — so that the terms remain directly comparable rather than being "
         "buried in a weighted sum of incommensurable scales:")
    body(doc,
         "score  =  distance  −  trust × 1500 m  −  (rating − 3.5) × 800 m  +  penalty",
         align=None, size=12, italic=True)
    body(doc,
         "A direct friend therefore begins 1500 m ahead of a stranger, each star above "
         "neutral is worth 800 m, and an open fraud flag pushes a runner back. The "
         "reputation weight is deliberately smaller than the social weight: reputation "
         "should decide between comparable candidates, not send an errand across campus. "
         "The penalty term is the only one that can add, and it is capped, so that "
         "accumulated suspicion demotes but never excludes.")
    body(doc,
         "Sorting alone would not give a friend genuine priority, because all "
         "candidates are published to within milliseconds of one another and the "
         "nearest stranger usually accepts first. Withholding the offer from runners "
         "beyond two social hops for the first 45 seconds is what actually confers "
         "first refusal; the tier widens on a timer thereafter.")
    figure(doc, "fig_matching.png",
           "Fig. 3. Trust-aware matching with deliberate exploration", width=6.2)
    body(doc,
         "The exploration branch is this project's principal design intervention. With "
         "probability ε — five per cent by default — a dispatch round is ranked on "
         "distance alone, with the social term removed and the hop ceiling lifted. Both "
         "must be suspended together: removing the boost while still hiding the errand "
         "from strangers would leave the sample exactly as biased, since the strangers "
         "whose absence constitutes the problem would still never be offered anything.")
    body(doc,
         "These rounds are the control group. They are the only observations in which "
         "the outcome was not already shaped by the friendship structure, and they are "
         "what makes the statistic in §4.2.4 computable. The mechanism is a "
         "configuration value that can be set to zero, in which case the system behaves "
         "exactly as before at the cost of the analysis it enables.")

    subsection(doc, "4.2.2  The Offer Log")
    body(doc,
         "For every dispatch round the system records the candidate set together with "
         "each candidate's distance, trust, hop count, reputation, penalty and resulting "
         "score; the hop ceiling in force; whether the round was socially blind; and "
         "which runner ultimately accepted. Each round is a separate record, because a "
         "re-offer occurs under a different candidate set and collapsing rounds would "
         "average away the variation the estimate depends upon.")
    body(doc,
         "Storing every term rather than only the final score is essential. A composite "
         "score cannot be decomposed back into its parts, so the counterfactual "
         "question — how would this round have ranked with the social term removed? — "
         "would be unanswerable from the score alone. The ranking formula has exactly "
         "one implementation, shared by the matcher and the log, so that the two cannot "
         "drift apart; an analysis built on a stale copy of the ranking rule would be "
         "worse than no analysis at all.")

    subsection(doc, "4.2.3  Escrow and the Append-Only Ledger")
    body(doc,
         "Money is held from the moment an errand is posted, so that a runner fronting "
         "cash at a counter is not relying on the requester still being solvent an hour "
         "later. The ledger is append-only and balances are derived — the sum of "
         "credits less the sum of debits — with no balance column anywhere in the "
         "schema. A balance that is never written cannot drift from the history that "
         "produced it.")
    figure(doc, "fig_escrow.png",
           "Fig. 5. Escrow state machine and append-only ledger", width=6.2)
    body(doc,
         "Three constraints carry the correctness argument. Amounts are strictly "
         "positive and direction is pinned per entry type, so a hold cannot become a "
         "credit even by a direct write. Released value can never exceed the amount "
         "held, so the platform cannot be made to pay out money it never collected. "
         "Finally, a uniqueness constraint on (errand, user, entry type) makes a "
         "redelivered settlement event collide rather than pay twice — which is what "
         "allows the settlement consumer to be at-least-once without being unsafe.")
    body(doc,
         "A refund appends a credit rather than editing a balance, so a cancelled "
         "errand and its repayment both remain visible in the history. Money withheld "
         "by a fraud check is not refunded but parked, with the hold moving to a "
         "pending-review state, because an administrator may yet judge the runner "
         "honest.")

    subsection(doc, "4.2.4  Social Graph and Collusion-Ring Detection")
    body(doc,
         "The social graph is projected from PostgreSQL into Neo4j as two edge types: "
         "friendship, and payment arising from a settled errand. Trust between two "
         "users is a function of path length, weighted by the maturity of the newest "
         "edge on that path — a chain of trust is only as established as its most "
         "recently created link, so a friendship formed yesterday confers little "
         "advantage today. This directly defends the cheapest attack available, which "
         "is to create a connection and immediately exploit it.")
    figure(doc, "fig_social.png",
           "Fig. 6. Social graph and collusion-ring detection", width=6.2)
    body(doc,
         "Structure alone cannot distinguish a genuine friend group from a collusion "
         "ring; both are fully closed. The discriminator is economic: whether value "
         "circulates within the group and returns to its source. A ring is identified "
         "as a strongly connected component of the payment graph whose members are "
         "mutual friends, subject to floors on group size, per-leg value and number of "
         "laps.")
    body(doc,
         "As established in §2.2, the in-group concentration used to trigger this "
         "search is distorted by the matching policy. The design response is "
         "policy-conditioned excess circulation. Because the offer log records the "
         "policy's own ranking at the moment of each decision, the system can compute "
         "how much in-group activity the policy predicted, and compare it against what "
         "occurred:")
    body(doc,
         "excess  =  observed in-group share  −  in-group share predicted by the policy",
         align=None, size=12, italic=True)
    body(doc,
         "An honest friend group follows the policy, so its excess is near zero however "
         "strong the boost; its concentration is fully explained. A colluding group "
         "seeks its own members out beyond what the policy suggested, and retains a "
         "large excess. Expressed as a standardised deviation, this yields an actual "
         "test statistic in place of the hand-tuned constants identified as the second "
         "deficiency in §2.2.")

    subsection(doc, "4.2.5  Multi-Signal Fraud Detection")
    body(doc,
         "Three detectors operate at different granularities and on independent "
         "evidence. Price inflation is judged per claim against a reference price for "
         "that item at that store, with a tolerance that scales with item value so that "
         "cheap items are not effectively unprotected. Rating farming is judged per "
         "runner from the provenance of their ratings — concentration within their own "
         "circle, the gap between friend and stranger ratings, and bursts of in-circle "
         "praise following a penalty. Collusion is judged per group as described above.")
    figure(doc, "fig_fraud.png",
           "Fig. 4. Multi-signal fraud detection pipeline", width=6.3)
    body(doc,
         "The staging is deliberate. Cheap, deterministic arithmetic decides who to "
         "examine; it is exact and cannot be defeated by writing persuasively. Only "
         "then is the language model asked the one question arithmetic cannot answer — "
         "whether a flagged group's errands read as plausible campus activity. Its "
         "verdict is advisory and is recorded alongside the numeric evidence rather "
         "than replacing it.")
    body(doc,
         "No detector applies a punishment on its own authority. Detection withholds "
         "disputed money and adjusts ranking; only an administrator's verdict moves "
         "funds permanently. Dismissing a flag additionally restores the disputed claim "
         "as evidence for the reference estimate, since a claim judged wrongly should "
         "not continue to distort what the system believes an item costs.")

    subsection(doc, "4.2.6  End-to-End Interaction")
    body(doc,
         "Figure 7 traces a single errand through the system. The escrow hold is placed "
         "synchronously, because a requester must be told immediately if their balance "
         "is insufficient. Settlement is asynchronous, because it depends on judging "
         "price claims and must not delay the requester's confirmation. The dashed "
         "arrows mark that boundary.")
    figure(doc, "fig_sequence.png",
           "Fig. 7. End-to-end sequence: post, offer, accept, deliver, settle",
           width=6.4)
    body(doc,
         "The critical property visible in the trace is that money moves in exactly one "
         "place, on exactly one event, and only once. Two independent mechanisms "
         "enforce this: a processed-events table at the consumer, and the uniqueness "
         "constraint in the ledger itself. Either alone would suffice; both together "
         "mean that a defect in one is not a payment defect.")
