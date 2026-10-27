"""Front matter, abstract and Chapter 1 of the Project-I report.

Title, team and guide are taken from the Review-1 submission so that the
document is continuous with what has already been approved.
"""

from docx.shared import Pt

from docx_helpers import _run, body, centered, chapter, pagebreak, section, table

TITLE = ("Errandly: A Trust-Aware, Fraud-Resistant Platform for Campus Errands, "
         "Micro-Delivery and Commerce")

TEAM = [
    ("23BCE0743", "CHRIS MARTIN MATTAM"),
    ("23BCE0832", "SANSKRITI SAJLAL"),
    ("23BDS0335", "UJJWAL GOGOI"),
]
GUIDE = "Dr. Ranjithkumar S"
GUIDE_TITLE = "Assistant Professor, School of Computer Science and Engineering"
PROJECT_ID = "20226UG03"


def front_matter(doc):
    centered(doc, "BCSE497J - Project-I", size=13, bold=True, after=14)
    centered(doc, TITLE, size=16, bold=True, caps=True, after=18)
    centered(doc, "A project report submitted in partial fulfilment of the "
                  "requirements for the degree of", size=12, after=6)
    centered(doc, "B.Tech.", size=13, bold=True, after=4)
    centered(doc, "in", size=12, after=4)
    centered(doc, "Computer Science and Engineering", size=13, bold=True, after=14)
    centered(doc, "by", size=12, after=10)
    for reg, name in TEAM:          # sorted on register number
        centered(doc, f"{reg}          {name}", size=13, bold=True, after=4)
    centered(doc, "", size=10, after=12)
    centered(doc, "Under the Supervision of", size=12, after=6)
    centered(doc, GUIDE, size=13, bold=True, after=2)
    centered(doc, GUIDE_TITLE, size=12, after=4)
    centered(doc, f"Project ID: {PROJECT_ID}", size=11, italic=True, after=22)
    centered(doc, "School of Computer Science and Engineering", size=13, bold=True, after=6)
    centered(doc, "Vellore Institute of Technology, Vellore", size=12, after=18)
    centered(doc, "September 2026", size=12, bold=True, after=6)

    pagebreak(doc)
    chapter(doc, "Declaration", page_break=False)
    body(doc, "We hereby declare that the report titled “" + TITLE + "” submitted by "
              "us to Vellore Institute of Technology, Vellore, in partial fulfilment of "
              "the requirements for the award of the degree of Bachelor of Technology in "
              "Computer Science and Engineering, is a record of bonafide work carried "
              "out by us under the supervision of " + GUIDE + ". We further declare that "
              "the work reported in this report has not been submitted, and will not be "
              "submitted, either in part or in full, for the award of any other degree "
              "or diploma of this institute or of any other institute or university.")
    body(doc, "")
    body(doc, "Place: Vellore")
    body(doc, "Date:   <DD / MM / 2026>")
    body(doc, "")
    body(doc, "Signature of the Candidates")

    pagebreak(doc)
    chapter(doc, "Certificate", page_break=False)
    body(doc, "This is to certify that the report titled “" + TITLE + "” is prepared "
              "and submitted by Chris Martin Mattam (23BCE0743), Sanskriti Sajlal "
              "(23BCE0832) and Ujjwal Gogoi (23BDS0335) to Vellore Institute of "
              "Technology, Vellore, in partial fulfilment of the requirements for the "
              "award of the degree of Bachelor of Technology in Computer Science and "
              "Engineering, and is a bonafide record carried out under my guidance. The "
              "project fulfils the requirements as per the regulations of this institute "
              "and in my opinion meets the necessary standards for submission. The "
              "contents of this report have not been submitted and will not be submitted "
              "either in part or in full, for the award of any other degree or diploma, "
              "and the same is certified.")
    body(doc, "")
    body(doc, "Signature of the Guide:                                                "
              "Signature of the Internal Examiner:")
    body(doc, "Name:  " + GUIDE + "                                     Name:")
    body(doc, "Date:                                                                     "
              "     Date:")
    body(doc, "")
    body(doc, "Approved by the Head of Department,")
    body(doc, "B.Tech. Computer Science and Engineering")
    body(doc, "Date:")

    pagebreak(doc)
    chapter(doc, "Acknowledgement", page_break=False)
    body(doc, "We record our sincere gratitude to our supervisor, " + GUIDE + ", " +
              GUIDE_TITLE + ", whose guidance shaped both the direction of this work and "
              "the standard we held it to. The insistence on measuring what we claimed "
              "rather than asserting it is the single habit that changed this project "
              "most.")
    body(doc, "We thank the Head of the Department and the faculty of the School of "
              "Computer Science and Engineering for the review sessions that repeatedly "
              "sent us back to first principles, and the management of Vellore Institute "
              "of Technology for the facilities that made sustained experimental work "
              "possible.")
    body(doc, "Finally, we thank the students who tested early builds on campus and "
              "reported the failures we had not thought to look for. Several design "
              "decisions defended in this report exist because a real user did something "
              "we had assumed nobody would do.")


def abstract(doc):
    pagebreak(doc)
    centered(doc, "Abstract", size=14, bold=True, caps=True, after=12)
    body(doc,
         "Errandly is a campus-verified platform on which VIT students post everyday "
         "errands — shopping lists, food orders, parcel pickups and main-gate "
         "collections — and resell pre-owned hostel items to one another. Every "
         "transaction settles through an escrow wallet: the requester's money is held by "
         "the platform when the task is posted and released only once delivery is "
         "confirmed, so neither side has to trust the other first. The system is built "
         "as a modular-monolith FastAPI backend over PostgreSQL with PostGIS, Redis, "
         "Kafka, MongoDB and Neo4j, with mobile and web clients.")
    body(doc,
         "Errands are matched to nearby runners by a ranking combining walking "
         "distance, social proximity drawn from a friendship graph, and reputation "
         "earned from completed transactions. Three detectors guard the "
         "platform: one checks each reported price against what that item costs at "
         "that shop, one checks whether a runner's ratings come only "
         "from their own friends, and one searches for a collusion ring — a group of "
         "friends who repeatedly pay one another in a closed loop, so the same money "
         "circles the same few people while every lap manufactures reputation at no "
         "real cost.")
    body(doc,
         "The research contribution resolves a conflict between the first mechanism and "
         "the last. Because the matcher deliberately offers errands to friends first, "
         "friends transact with one another far more often than chance would predict — "
         "which is exactly the pattern the ring detector treats as evidence. The "
         "platform therefore manufactures its own suspicion, and honest friend groups "
         "are flagged for something the routing caused. We correct this by computing how "
         "much in-group activity the matcher itself predicted and admitting only the "
         "unexplained excess as evidence. We further show that a sufficiently strong "
         "trust preference makes collusion undetectable in principle, and that offering "
         "a small fraction of errands with friendship ignored restores detection at "
         "negligible cost.")
    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = 1.15
    p.paragraph_format.space_before = Pt(10)
    _run(p, "Keywords — ", size=12, bold=True)
    _run(p, "Campus Commerce; Peer-to-Peer Errands; Escrow Wallet; Trust-Aware "
            "Matching; Social Graph; Collusion Detection; Reputation Systems; Price "
            "Anomaly Detection.", size=12)


def table_of_contents(doc):
    pagebreak(doc)
    centered(doc, "Table of Contents", size=14, bold=True, caps=True, after=12)
    rows = [
        ("", "Abstract", "iv"),
        ("", "List of Figures", "vi"),
        ("1", "INTRODUCTION", "1"),
        ("1.1", "Background", "1"),
        ("1.2", "Motivation", "2"),
        ("1.3", "Scope of the Project", "2"),
        ("2", "PROJECT DESCRIPTION AND GOALS", "3"),
        ("2.1", "Literature Review", "3"),
        ("2.2", "Research Gap", "6"),
        ("2.3", "Aim and Objectives", "8"),
        ("2.4", "Problem Statement", "9"),
        ("2.5", "Project Plan", "10"),
        ("3", "TECHNICAL SPECIFICATION", "11"),
        ("3.1", "Requirements", "11"),
        ("3.2", "Feasibility Study", "14"),
        ("3.3", "System Specification", "16"),
        ("4", "DESIGN APPROACH AND DETAILS", "18"),
        ("4.1", "System Architecture", "18"),
        ("4.2", "Design", "21"),
        ("5", "REFERENCES", "29"),
    ]
    table(doc, ["No.", "Title", "Page"], rows, widths=[0.7, 5.0, 0.7], font=11)
    body(doc, "Page numbers are indicative; repaginate in Word after final layout.",
         italic=True, size=10)

    centered(doc, "List of Figures", size=14, bold=True, caps=True, after=10)
    figs = [
        ("Fig. 1", "Gantt chart of the project plan", "10"),
        ("Fig. 2", "Errandly system architecture", "18"),
        ("Fig. 3", "Trust-aware matching with deliberate exploration", "21"),
        ("Fig. 4", "Multi-signal fraud detection pipeline", "25"),
        ("Fig. 5", "Escrow state machine and append-only ledger", "23"),
        ("Fig. 6", "Social graph and collusion-ring detection", "24"),
        ("Fig. 7", "End-to-end sequence: post, offer, accept, deliver, settle", "27"),
    ]
    table(doc, ["Figure", "Caption", "Page"], figs, widths=[0.9, 4.8, 0.7], font=11)


def chapter_1(doc):
    chapter(doc, "1. Introduction")

    section(doc, "1.1 Background")
    body(doc,
         "A residential university campus generates a continuous stream of small, "
         "time-bound needs. Groceries must be fetched, food collected, parcels picked up "
         "from the main gate, and — at the end of every semester — furniture, cycles and "
         "books cleared out of hostel rooms. These tasks are individually trivial and "
         "collectively substantial, handled today through scattered messaging groups, "
         "informal favours and cash in hand.")
    body(doc,
         "Commercial delivery platforms serve this need poorly. Their economics assume "
         "vendor partnerships and city-scale logistics; their commissions and flat fees "
         "are heavy for a task worth a few tens of rupees; and their couriers cannot "
         "enter hostel blocks. Resale is served worse still: no channel exists between an "
         "outgoing student clearing a room and an incoming one furnishing theirs.")
    body(doc,
         "The capability, however, already exists on campus: at any hour many students "
         "are moving between the same small set of locations and could carry an item at "
         "almost no marginal cost. Realising that as a platform introduces the classic "
         "problems of a market between strangers — money must move before a service is "
         "rendered, quality is observed only by the two parties, and reputation is both "
         "the main trust signal and the obvious target for manipulation.")

    section(doc, "1.2 Motivation")
    body(doc,
         "Trust on a campus is not uniform. Students already know some of their "
         "neighbours, and an errand run by an acquaintance carries materially less risk "
         "than one run by a stranger. A platform able to represent those existing "
         "relationships should route work more safely than one treating every "
         "participant as interchangeable, and a closed, institutionally-verified "
         "population makes that far more tractable than an open marketplace.")
    body(doc,
         "The same structure is what makes fraud possible. A small group of mutually "
         "connected students can transact among themselves to accumulate "
         "completed-errand history and favourable ratings at no real cost, and can "
         "inflate reported purchase prices knowing the platform never sees a receipt. "
         "Reputation manipulation and collusion are therefore not incidental risks but "
         "direct consequences of the trust mechanism itself.")
    body(doc,
         "The deeper motivation emerged during implementation. Having built both a "
         "trust-aware matcher and a graph-based collusion detector, we found the first "
         "systematically corrupts the evidence available to the second. This is not a "
         "defect of our implementation; it follows from the architecture the literature "
         "recommends, and appears to be unaddressed.")

    section(doc, "1.3 Scope of the Project")
    body(doc,
         "The project covers a complete campus commerce platform: campus-email identity "
         "and verification, four errand categories, a peer resale marketplace, "
         "geospatial matching, live tracking, in-app messaging, an escrow wallet holding "
         "funds between order and settlement, reputation from completed transactions, "
         "and an administrative console for fraud review, delivered through mobile and "
         "web clients.")
    body(doc,
         "Within that system the research scope is narrow and specific: the interaction "
         "between the matching policy and the fraud-detection layer. The project "
         "characterises how trust-based routing biases the evidence used for collusion "
         "detection, proposes a policy-conditioned statistic correcting for it, "
         "establishes the detectability limit arising when the routing policy saturates, "
         "and evaluates deliberate exploration as a remedy.")
    body(doc,
         "Three boundaries are stated explicitly. Real-money settlement through a "
         "licensed gateway is designed but not implemented; the ledger is complete and "
         "gateway-ready but transacts in platform credit. The peer resale marketplace is "
         "specified in this report and scheduled for Project-II; the errand path is "
         "implemented end to end. Finally, the evaluation reported here is "
         "simulation-based, with a live pilot cohort deferred to Project-II.")
