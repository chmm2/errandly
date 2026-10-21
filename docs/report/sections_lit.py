"""Chapter 2 — Project Description and Goals, plus the reference list.

Ten papers, not fifty. The selection rule is strict: a paper appears only where
Errandly implements something that answers it. Each row therefore ends with the
gap that paper leaves and the specific mechanism in this project that closes it,
so the review reads as an argument rather than a catalogue.

The reference list is the single source of truth for citation numbers: the prose
cites entries by index, so inserting a work renumbers the text rather than
silently desynchronising it.
"""

from docx.shared import Inches, Pt

from docx_helpers import (
    _run, body, chapter, figure, numbered, section, subsection, table,
)

REFERENCES = [
    "W. Jiang, G. Wang, Md. Z. A. Bhuiyan and J. Wu, “Understanding graph-based "
    "trust evaluation in online social networks: methodologies and challenges,” ACM "
    "Computing Surveys, vol. 49, no. 1, pp. 1–35, 2016.",
    "S.-Y. Chiou and T.-Y. Tu, “A trusted mobile ride-hailing evaluation system with "
    "privacy and authentication,” IEEE Access, vol. 8, pp. 61929–61942, 2020.",
    "F. Donglai and L. Yanhua, “Trust-aware task allocation in collaborative "
    "crowdsourcing model,” The Computer Journal, vol. 64, no. 6, 2021.",
    "P. Cheng, L. Chen and J. Ye, “Cooperation-aware task assignment in spatial "
    "crowdsourcing,” in Proc. IEEE 35th Int. Conf. Data Engineering (ICDE), 2019, "
    "pp. 1442–1453.",
    "“An escrow-based peer-to-peer online payment system for fraud reduction,” "
    "Methods in Science and Technology Studies, 2026.",
    "A. Sarpal, Q. Kang, F. Huang, Y. Song and L. Wan, “A marketplace price anomaly "
    "detection system at scale,” arXiv preprint arXiv:2310.04367, 2023.",
    "R. P. Maranzato and A. M. Pereira, “Feature extraction for fraud detection in "
    "electronic marketplaces,” in Proc. IEEE Latin American Web Congress (LA-Web), "
    "2009.",
    "S. D. Kamvar, M. T. Schlosser and H. Garcia-Molina, “The EigenTrust algorithm "
    "for reputation management in P2P networks,” in Proc. 12th Int. Conf. World Wide "
    "Web (WWW), 2003, pp. 640–651.",
    "B. Viswanath, A. Post, K. P. Gummadi and A. Mislove, “An analysis of social "
    "network-based Sybil defenses,” in Proc. ACM SIGCOMM, 2010, pp. 363–374.",
    "J. Perdomo, T. Zrnic, C. Mendler-Dünner and M. Hardt, “Performative "
    "prediction,” in Proc. 37th Int. Conf. Machine Learning (ICML), 2020, "
    "pp. 7599–7609.",
    "R. E. Tarjan, “Depth-first search and linear graph algorithms,” SIAM Journal on "
    "Computing, vol. 1, no. 2, pp. 146–160, 1972.",
]

WEBLINKS = [
    "Transactional outbox pattern. https://microservices.io/patterns/data/"
    "transactional-outbox.html",
    "Neo4j Cypher manual. https://neo4j.com/docs/cypher-manual/current/",
    "Redis geospatial commands. https://redis.io/docs/latest/commands/geosearch/",
    "Ollama model library. https://ollama.com/library/qwen2.5",
]

LIT_ROWS = [
    ["[1] Jiang et al.,\nACM Comput.\nSurv., 2016",
     "Formalise how trust is computed and propagated across a social graph, not "
     "merely between two directly connected users.",
     "Comparative survey of graph-simplification and graph-analogy trust-"
     "propagation methods.",
     "+ Establishes hop-distance trust decay as a tunable design problem.\n"
     "− Survey only; no matching, fraud or campus application.",
     "Gap: decay depends on distance alone.\nOurs: trust also decays with the age "
     "of the newest edge on the path, so a friendship made yesterday buys almost "
     "nothing today."],
    ["[2] Chiou & Tu,\nIEEE Access,\n2020",
     "Let ride-hailing riders weight a driver's ratings by the rater's closeness "
     "to them rather than treating all raters alike.",
     "Social-network-based scoring with cryptographic rater privacy; implemented "
     "and tested on Android.",
     "+ First to fold the user's own social graph into trust scoring.\n"
     "− Rating weighting only; no price or fraud signal.",
     "Gap: closeness raises a rater's weight.\nOurs: closeness lowers it once a "
     "runner's ratings concentrate inside their own circle — the farming case."],
    ["[3] Fu & Liu,\nComputer\nJournal, 2021",
     "Assign crowdsourcing tasks to the most trusted worker, not merely the "
     "nearest or the cheapest.",
     "T-Aware model: trust scored from platform history and optimised jointly "
     "with task cost during assignment.",
     "+ Treats trust as a formal objective in assignment.\n"
     "− Trust from platform history only; no peer graph; not campus-scoped.",
     "Gap: no notion of who actually knows whom.\nOurs: a real friendship graph "
     "supplies trust, and every ranking term is expressed in one unit — metres of "
     "effective distance."],
    ["[4] Cheng, Chen\n& Ye, IEEE\nICDE, 2019",
     "Co-assign workers who have previously collaborated successfully.",
     "Cooperation-aware assignment; cooperativeness scored from interaction "
     "history and optimised during matching.",
     "+ Demonstrates measurable quality gains from social history.\n"
     "− The policy decides who transacts with whom, and that effect is never "
     "examined.",
     "Gap: the policy shapes the very history it later consumes.\nOurs: this "
     "feedback loop is the project's central research problem (G5)."],
    ["[5] Escrow-based\nP2P payment\nsystem, 2026",
     "Reduce fraud in peer-to-peer online payments through a trusted third "
     "party.",
     "Object-oriented design; third-party escrow; PHP/MySQL implementation.",
     "+ Structured, auditable release of funds.\n"
     "− Generic e-commerce; balances are stored and mutated in place.",
     "Gap: a stored balance can drift from its own history.\nOurs: an append-only "
     "ledger with derived balances, and a uniqueness rule that makes a "
     "redelivered settlement collide instead of paying twice."],
    ["[6] Sarpal et al.,\narXiv:2310.\n04367, 2023",
     "Detect mispriced or manipulated listings at marketplace scale without "
     "manual review.",
     "MoatPlus: an ensemble of unsupervised models over historical and proximate "
     "prices sets a data-driven price bound.",
     "+ Price consensus needs no receipts; +46.6% precision in the riskiest "
     "categories.\n− Built for structured catalogue items, not peer-reported cash "
     "spend.",
     "Gap: one price per item ignores that the same item costs differently at "
     "different shops.\nOurs: a per-store reference, shrunk toward the campus "
     "median by how much independent evidence supports it."],
    ["[7] Maranzato &\nPereira, IEEE\nLA-Web, 2009",
     "Detect sellers gaming reputation systems in electronic marketplaces.",
     "Behavioural and transaction features — pricing and feedback patterns — "
     "extracted from real marketplace data.",
     "+ Transaction patterns flag reputation gaming without manual review.\n"
     "− Detects fraud after the fact; never fed back into matching.",
     "Gap: detection and matching are disconnected.\nOurs: an open flag is a "
     "bounded ranking penalty, so suspicion demotes a runner at once but can "
     "never exclude them."],
    ["[8] Kamvar et al.,\nWWW, 2003",
     "Compute a global trust value for every peer in a peer-to-peer network.",
     "EigenTrust: transitive propagation of local trust, power iteration to a "
     "global trust vector.",
     "+ Canonical and fully distributed.\n− The authors themselves note "
     "vulnerability to collusive groups that rate one another up.",
     "Gap: the collusive-group weakness is acknowledged, not solved.\nOurs: rings "
     "are found as directed payment cycles among mutual friends using Tarjan's "
     "algorithm [11]."],
    ["[9] Viswanath\net al., ACM\nSIGCOMM, 2010",
     "Unify and evaluate social-graph defences against fake identities.",
     "Comparative analysis of SybilGuard, SybilLimit and SybilRank over real "
     "network topologies.",
     "+ Shows these schemes are really community detection.\n− Effectiveness "
     "rests entirely on the trust assumption holding in the deployed network.",
     "Gap: the graph is treated as observed, never as produced by the platform.\n"
     "Ours: our graph is produced by our own routing, so its evidence must be "
     "conditioned on the policy that created it."],
    ["[10] Perdomo\net al., ICML,\n2020",
     "Formalise settings in which deploying a model changes the distribution the "
     "model was built to predict.",
     "Performative prediction: risk minimisation over a distribution that depends "
     "on the deployed model; performative stability.",
     "+ Exactly the right apparatus for a self-influencing system.\n− Developed "
     "for prediction and pricing; never applied to fraud evidence.",
     "Gap: nobody applies it to a fraud graph the platform itself generated.\n"
     "Ours: the routing policy becomes the null hypothesis against which in-group "
     "activity is judged."],
]


def chapter_2(doc):
    chapter(doc, "2. Project Description and Goals")

    section(doc, "2.1 Literature Review")
    body(doc,
         "Ten works are reviewed. The selection rule is deliberately strict: a paper "
         "appears only where this project implements something that answers it. Broad "
         "surveys of campus marketplace applications are excluded, because such work is "
         "integrative rather than methodological and leaves no gap a design decision "
         "could close.")
    body(doc,
         "The papers follow the path an errand actually takes through the system. Works "
         "[1]–[4] concern how a task should be assigned when participants know one "
         "another. Work [5] concerns holding the money in between. Works [6] and [7] "
         "concern judging whether what a runner reported is honest. Works [8]–[10] "
         "concern what happens when the people being judged are themselves connected. "
         "The final column of Table 2.1 states, for each paper, the gap it leaves and "
         "the specific mechanism in this project that closes it.")

    table(doc,
          ["Paper", "Objective", "Methodology", "Pros / Cons",
           "Gap left  →  our response"],
          LIT_ROWS, widths=[0.95, 1.20, 1.20, 1.35, 1.70], font=7.5)

    body(doc,
         "Read down the final column, the ten papers describe one unfinished argument. "
         "Trust should inform assignment [1]–[4]; money should be held neutrally in "
         "between [5]; reported prices and reputations should be checked statistically "
         "[6], [7]; and connected users can defeat a reputation system simply by "
         "cooperating [8], [9]. Every step is established. What no paper addresses is "
         "that the first step corrupts the evidence available to the last — a phenomenon "
         "formalised in an entirely separate literature [10] and never applied here.")

    section(doc, "2.2 Research Gap")
    body(doc,
         "Five gaps motivate this project. The first four were identified during "
         "requirements analysis and shape the platform; the fifth emerged during "
         "implementation and constitutes the research contribution.")

    subsection(doc, "G1.  Trust is assumed rather than engineered")
    body(doc,
         "Campus resale and errand applications rely on informal goodwill or a simple "
         "star rating. Nothing holds a payment until a task is actually completed, so "
         "the entire risk of non-delivery sits with whichever party moves first — the "
         "requester who pays up front, or the runner who fronts cash at a counter. The "
         "escrow ledger of §4.2.3 removes that asymmetry.")

    subsection(doc, "G2.  Commerce and tasks live apart")
    body(doc,
         "Marketplace applications solve resale; delivery applications solve tasks. No "
         "platform lets one verified campus identity do both, under a single wallet, a "
         "single reputation and a single dispute process. Each semester usable "
         "furniture, cycles and books are discarded by outgoing students purely for want "
         "of a trusted resale channel that operates on the same rails as errands.")

    subsection(doc, "G3.  Price integrity without receipts")
    body(doc,
         "Most campus vendors issue no receipt, so a runner's claimed spend cannot be "
         "checked against proof. Marketplace anomaly detection [6] shows that a "
         "statistical price consensus can substitute for receipts, but assumes "
         "catalogue items with a single price. A campus sells the same item at "
         "materially different prices in different outlets, and a single campus-wide "
         "reference is then wrong in both directions at once: it reads an honest runner "
         "at the dearer canteen as inflating, while leaving a runner inflating at the "
         "cheaper one comfortably inside the band.")

    subsection(doc, "G4.  Detection that never reaches the matcher")
    body(doc,
         "Fraud detection in marketplaces [7] is retrospective: features are extracted, "
         "sellers are scored, and a human acts later. The result is not fed back into "
         "who is offered work next, so a runner under active suspicion continues to "
         "receive exactly as many offers as before.")

    subsection(doc, "G5.  The platform manufactures its own fraud evidence")
    body(doc,
         "This is the project's principal research gap, and it becomes visible only once "
         "the first four are solved together. Trust-aware assignment [3], [4] promotes "
         "socially connected runners up the offer queue. Collusion detection [8], [9] "
         "reads concentrated in-group transaction activity as evidence of a ring. "
         "Deployed together — as the literature independently recommends — the first "
         "mechanism produces the pattern the second treats as evidence.")
    body(doc,
         "Honest friends are therefore pushed toward a flag they did nothing to earn, "
         "while a genuine ring can attribute its own concentration to the platform. The "
         "distortion is worst for precisely the tight-knit groups the detector watches "
         "most closely, since greater closure means more opportunities for the trust "
         "boost to apply. The two signals the detector treats as corroborating one "
         "another — closure and circulation — are consequently correlated through the "
         "routing policy rather than through fraud.")
    body(doc,
         "The prior literature does not address this because of a shared premise: in "
         "[8] and [9] the social graph is exogenous, something the platform observes. "
         "Here it is endogenous, generated by the platform's own decisions. Performative "
         "prediction [10] supplies precisely the right apparatus, and has been developed "
         "for prediction and pricing rather than for fraud evidence. Three concrete "
         "deficiencies follow.")
    numbered(doc,
             "No collusion detector conditions its evidence on the assignment policy "
             "that produced the interactions it examines.")
    numbered(doc,
             "The thresholds used to declare a ring — group size, leg value, number of "
             "laps, concentration — are hand-tuned constants, so there is no test "
             "statistic and no principled false-positive rate.")
    numbered(doc,
             "The relationship between the strength of a trust boost and the "
             "detectability of collusion is unquantified, so there is no basis on which "
             "to choose that boost.")

    section(doc, "2.3 Aim and Objectives")
    body(doc,
         "Aim. To design, develop and validate Errandly, a campus-verified platform on "
         "which VIT students earn through paid peer-run errands and resell pre-owned "
         "essentials within a closed, trust-verified network, settling every transaction "
         "through an escrow wallet, so that campus errands and resale happen safely and "
         "without informal cash deals or outside gig-platform markups — and to do so "
         "without the trust mechanism destroying the platform's own ability to detect "
         "abuse by the socially connected.")
    body(doc, "The aim decomposes into eight objectives.", size=12)
    numbered(doc,
             "Errand and marketplace core. Implement four errand types — shopping list, "
             "food order, parcel pickup and main-gate collection — together with a peer "
             "resale marketplace, on one modular-monolith FastAPI backend serving both "
             "mobile and web clients.")
    numbered(doc,
             "Identity and verification. Restrict signup to the campus e-mail domain "
             "with one-time-password verification, and build reputation only from "
             "completed transactions.")
    numbered(doc,
             "Trust-first matching. Rank nearby runners from a Redis geospatial query by "
             "social proximity, reputation and integrity standing, breaking ties by "
             "distance, with race-guarded acceptance.")
    numbered(doc,
             "Escrow wallet. Hold the requester's payment at posting, release it only on "
             "confirmed delivery, and settle unpriced items against a price consensus "
             "rather than the runner's claim alone — for errands and marketplace sales "
             "alike.")
    numbered(doc,
             "Auditable lifecycle. Event-source every state transition through a "
             "transactional outbox, so the full history of any errand or payment is "
             "reconstructable.")
    numbered(doc,
             "Multi-signal fraud detection. Detect price inflation per claim, rating "
             "farming per runner and collusion rings per group, feeding each result back "
             "into matching as a bounded penalty rather than a ban.")
    numbered(doc,
             "Policy-conditioned evidence. Record the full candidate set and every "
             "ranking term for each dispatch round, and use the routing policy itself as "
             "the null hypothesis, so that only in-group activity the policy cannot "
             "explain is admitted as evidence of collusion.")
    numbered(doc,
             "Validation. Pilot with a VIT student cohort and measure "
             "completed-transaction rate, dispute rate and time-to-match, alongside a "
             "simulation study of the detector's false-positive behaviour.")

    section(doc, "2.4 Problem Statement")
    body(doc,
         "VIT students routinely need groceries fetched, food collected, parcels picked "
         "up, or hostel items resold before moving out. These needs are met today "
         "through scattered messaging groups, informal favours and full-markup delivery "
         "applications, for tasks a hostelmate two blocks away could complete in ten "
         "minutes. Food-delivery platforms take roughly 21–24% of every order with a "
         "flat platform fee stacked on top, and no campus platform today verifies both "
         "sides of a peer transaction before money changes hands.")
    body(doc,
         "The engineering problem is to build a closed, campus-verified platform that "
         "matches errands and resale listings to nearby trusted peers, holds funds "
         "neutrally until delivery is confirmed, and detects abuse of both prices and "
         "reputations in a setting where receipts do not exist.")
    body(doc,
         "The research problem sits inside it. Routing on social trust and detecting "
         "collusion among the socially connected are in direct tension: the stronger the "
         "social preference in assignment, the more in-group concentration arises for "
         "entirely innocent reasons, and the less of it survives as evidence. The task "
         "is therefore not to detect collusion, but to separate the platform's own "
         "contribution to an observed pattern from the participants' — and to establish "
         "how strong a trust boost may be before that separation becomes impossible.")

    section(doc, "2.5 Project Plan")
    body(doc,
         "The project follows an Agile methodology across six sprints of roughly two to "
         "three weeks, preceded by requirements analysis and architectural design and "
         "followed by evaluation and documentation, spanning July to October 2026. "
         "Sprints overlap by about a week so that review feedback and carry-over do not "
         "stall the sprint that follows.")
    body(doc,
         "The ordering is dictated by dependency rather than convenience. The escrow "
         "ledger precedes the social graph because settlement records are the payment "
         "edges the graph projects; the social graph precedes fraud detection because "
         "ring detection operates over those edges; and the offer log is scheduled last "
         "among the implementation sprints because its value is proportional to the "
         "volume of dispatch data accumulated after it goes live.")
    figure(doc, "fig_gantt.png", "Fig. 1. Gantt chart of the project plan", width=6.4)


def chapter_5_references(doc):
    chapter(doc, "5. References")
    body(doc, "Journals, Conferences and Books  <IEEE Format>", size=12)
    for i, ref in enumerate(REFERENCES, start=1):
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.line_spacing = 1.15
        pf.space_after = Pt(6)
        pf.left_indent = Inches(0.45)
        pf.first_line_indent = Inches(-0.45)
        _run(p, f"[{i}]\t{ref}", size=11)
    body(doc, "")
    body(doc, "Weblinks", size=12)
    for link in WEBLINKS:
        p = doc.add_paragraph()
        p.paragraph_format.line_spacing = 1.15
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.left_indent = Inches(0.45)
        _run(p, link, size=11)
