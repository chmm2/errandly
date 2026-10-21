"""Report figures for the Project-I document.

Regenerate with:  python docs/report/figures.py

Monochrome throughout — the report prints in black and white, and a figure that
only reads in colour stops carrying its meaning the moment it is photocopied.
Emphasis is therefore carried by line weight and fill value, never by hue.

matplotlib rather than graphviz on purpose: no binary dependency, and every box
is placed deliberately rather than by a layout engine that reflows the whole
picture when one node is added.

Design rule: a figure carries STRUCTURE, not prose. Labels are short noun
phrases; anything needing a sentence belongs in the body text beside the figure.
"""

from __future__ import annotations

import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse, FancyArrowPatch, FancyBboxPatch

OUT = pathlib.Path(__file__).parent / "figures"
OUT.mkdir(parents=True, exist_ok=True)

BLACK = "#000000"
INK = "#111111"
GREY = "#555555"
LINE = "#999999"
WHITE = "#ffffff"
FILL_1 = "#f4f4f4"   # tier stripe
FILL_2 = "#e6e6e6"   # emphasised / novel block
FILL_3 = "#d0d0d0"   # strongest emphasis

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 9,
    "figure.dpi": 200,
    "savefig.dpi": 200,
    "savefig.bbox": "tight",
    "savefig.facecolor": "white",
})


def box(ax, x, y, w, h, text, fill=WHITE, lw=1.1, fs=8.5, bold=False,
        ls="solid", radius=0.018):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle=f"round,pad=0.005,rounding_size={radius}",
        facecolor=fill, edgecolor=BLACK, linewidth=lw, linestyle=ls, zorder=2))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs,
            color=INK, zorder=3, fontweight="bold" if bold else "normal",
            linespacing=1.5)


def arrow(ax, p1, p2, lw=1.0, ls="solid", rad=0.0, style="-|>"):
    ax.add_patch(FancyArrowPatch(
        p1, p2, arrowstyle=style, mutation_scale=10, color=BLACK, linewidth=lw,
        linestyle=ls, zorder=1, connectionstyle=f"arc3,rad={rad}",
        shrinkA=2, shrinkB=2))


def alabel(ax, x, y, text, fs=7.0, ha="center"):
    """A label on white, so it never sits on top of a line."""
    ax.text(x, y, text, ha=ha, va="center", fontsize=fs, color=GREY, zorder=4,
            bbox=dict(boxstyle="round,pad=0.18", fc=WHITE, ec="none"))


def canvas(w, h, title=None, sub=None):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    if title:
        ax.text(0.5, 0.988, title, ha="center", va="top", fontsize=11.5,
                fontweight="bold", color=BLACK)
    if sub:
        ax.text(0.5, 0.950, sub, ha="center", va="top", fontsize=7.8,
                color=GREY, style="italic")
    return fig, ax


def band(ax, y, h, label):
    """Tier stripe with its label in a left gutter, outside the stripe."""
    ax.add_patch(FancyBboxPatch(
        (0.070, y), 0.925, h, boxstyle="round,pad=0,rounding_size=0.010",
        facecolor=FILL_1, edgecolor="none", zorder=0))
    ax.text(0.036, y + h / 2, label, ha="center", va="center", fontsize=7.0,
            color=GREY, fontweight="bold", rotation=90)


def footnote(ax, text, y=0.012):
    ax.text(0.5, y, text, ha="center", va="bottom", fontsize=7.2, color=GREY,
            style="italic")


def save(fig, name):
    fig.savefig(OUT / name)
    plt.close(fig)
    print(f"  {name}")


# ═══════════════════════════════════════════════ Fig 2: System Architecture
def fig_architecture():
    fig, ax = canvas(11.4, 9.0, "Errandly — System Architecture",
                     "modular monolith over polyglot persistence; asynchronous work "
                     "isolated behind a transactional outbox")

    band(ax, 0.800, 0.118, "CLIENTS")
    band(ax, 0.652, 0.114, "API")
    band(ax, 0.404, 0.214, "DOMAIN")
    band(ax, 0.200, 0.172, "ASYNC")
    band(ax, 0.062, 0.112, "STORAGE")

    for x, t in ((0.126, "Mobile App\nReact Native / Expo"),
                 (0.412, "Web App\nReact + Vite"),
                 (0.698, "Admin Console\nfraud review")):
        box(ax, x, 0.818, 0.240, 0.078, t, bold=True)

    box(ax, 0.111, 0.670, 0.290, 0.072, "REST  (FastAPI)\nJWT · rate limit")
    box(ax, 0.432, 0.670, 0.220, 0.072, "WebSocket\ntracking · chat")
    box(ax, 0.683, 0.670, 0.270, 0.072, "Push\nFCM / Expo")

    mods = ["Auth\n& Identity", "Errands\n& Matching", "Ledger\n& Escrow",
            "Social\nGraph", "Fraud\nDetection", "Chat &\nNotify"]
    for i, t in enumerate(mods):
        novel = t.startswith(("Errands", "Ledger", "Social", "Fraud"))
        box(ax, 0.0936 + i * 0.1486, 0.516, 0.135, 0.082, t,
            fill=FILL_2 if novel else WHITE, lw=2.0 if novel else 1.1,
            bold=novel, fs=8.2)
    box(ax, 0.0936, 0.430, 0.878, 0.054,
        "Offer Log   ·   candidate set + every ranking term, per dispatch round",
        fill=FILL_2, lw=2.0, fs=8.4, bold=True)

    box(ax, 0.110, 0.292, 0.175, 0.064, "Transactional\nOutbox")
    box(ax, 0.320, 0.292, 0.130, 0.064, "Relay")
    box(ax, 0.485, 0.292, 0.130, 0.064, "Kafka", bold=True)
    box(ax, 0.650, 0.304, 0.170, 0.052, "settlement · analytics", fs=7.6)
    box(ax, 0.650, 0.236, 0.170, 0.052, "notifications · graph", fs=7.6)
    box(ax, 0.845, 0.272, 0.140, 0.064, "Ollama LLM\nqwen2.5:7b", fill=FILL_2,
        lw=2.0, fs=7.8, bold=True)

    stores = [("PostgreSQL\n+ PostGIS", "system of record"), ("Redis", "GEO · locks · pub/sub"),
              ("Kafka log", "durable events"), ("MongoDB", "chat history"),
              ("Neo4j", "derived graph"), ("Object\nstore", "media")]
    for i, (t, sub) in enumerate(stores):
        x = 0.0893 + i * 0.1493
        box(ax, x, 0.098, 0.140, 0.064, t, fs=8)
        ax.text(x + 0.070, 0.088, sub, ha="center", va="top", fontsize=6.6, color=GREY)

    for x in (0.246, 0.532, 0.818):
        arrow(ax, (x, 0.818), (x, 0.742))
    arrow(ax, (0.256, 0.670), (0.256, 0.598))
    arrow(ax, (0.542, 0.670), (0.542, 0.598))
    arrow(ax, (0.818, 0.670), (0.818, 0.598))
    arrow(ax, (0.533, 0.516), (0.533, 0.484))
    arrow(ax, (0.197, 0.430), (0.197, 0.356))
    arrow(ax, (0.285, 0.324), (0.320, 0.324))
    arrow(ax, (0.450, 0.324), (0.485, 0.324))
    arrow(ax, (0.615, 0.326), (0.650, 0.330))
    arrow(ax, (0.615, 0.316), (0.650, 0.262))
    arrow(ax, (0.820, 0.304), (0.845, 0.304), ls="dashed")
    arrow(ax, (0.159, 0.292), (0.159, 0.162))
    arrow(ax, (0.756, 0.236), (0.756, 0.162))

    footnote(ax, "Bold outline marks the modules carrying this project's novel "
                 "contribution.   Neo4j is a derived read model, rebuildable from "
                 "PostgreSQL at any time.")
    save(fig, "fig_architecture.png")


# ══════════════════════════════════════════════ Fig 3: Matching pipeline
def fig_matching():
    fig, ax = canvas(10.8, 8.2, "Trust-Aware Matching with Deliberate Exploration",
                     "every ranking term is expressed in metres of effective distance, "
                     "so the terms stay directly comparable")

    box(ax, 0.030, 0.852, 0.200, 0.070, "Errand posted", bold=True)
    box(ax, 0.268, 0.852, 0.210, 0.070, "Redis GEO\n5 nearest, ≤ 3 km")
    box(ax, 0.516, 0.852, 0.215, 0.070, "Drop co-ringed\ncandidates", fill=FILL_2, lw=1.8)
    box(ax, 0.769, 0.852, 0.205, 0.070, "Gather signals\ntrust · rating · flags")
    arrow(ax, (0.230, 0.887), (0.268, 0.887))
    arrow(ax, (0.478, 0.887), (0.516, 0.887))
    arrow(ax, (0.731, 0.887), (0.769, 0.887))

    box(ax, 0.370, 0.735, 0.260, 0.058, "explore ?     ε = 5 %", fill=FILL_3,
        lw=2.0, bold=True, fs=9)
    arrow(ax, (0.871, 0.852), (0.630, 0.778), rad=-0.16)

    # Boxes sized from the text they hold: eight lines at 8.2 pt with 1.5
    # linespacing need ~0.22 of this canvas, so 0.25 leaves a real margin.
    box(ax, 0.045, 0.410, 0.375, 0.250,
        "NORMAL   ·   95 %\n\n"
        "score  =  distance\n"
        "      −  trust × 1500 m\n"
        "      −  (rating − 3.5) × 800 m\n"
        "      +  open-flag penalty\n\n"
        "offered within 2 hops for 45 s",
        fs=8.2)
    box(ax, 0.580, 0.410, 0.375, 0.250,
        "EXPLORING   ·   5 %\n\n"
        "score  =  distance\n"
        "      −  (rating − 3.5) × 800 m\n"
        "      +  open-flag penalty\n\n"
        "no social term · no hop ceiling\n"
        "offered to everyone at once",
        fill=FILL_2, lw=2.0, fs=8.2)
    arrow(ax, (0.430, 0.738), (0.280, 0.662), rad=0.15)
    arrow(ax, (0.570, 0.738), (0.720, 0.662), rad=-0.15)
    alabel(ax, 0.322, 0.722, "no")
    alabel(ax, 0.680, 0.722, "yes")

    box(ax, 0.285, 0.258, 0.430, 0.068,
        "Publish offers   ·   first to accept wins", bold=True, fs=8.8)
    arrow(ax, (0.2325, 0.410), (0.400, 0.326), rad=-0.10)
    arrow(ax, (0.7675, 0.410), (0.600, 0.326), rad=0.10)

    box(ax, 0.200, 0.108, 0.600, 0.080,
        "OFFER  LOG\ncandidates · every term · explored? · who accepted",
        fill=FILL_2, lw=2.0, bold=True, fs=8.4)
    arrow(ax, (0.500, 0.258), (0.500, 0.188))

    footnote(ax, "The exploring branch is the control group: the only rounds whose "
                 "outcome was not already shaped by friendship.", y=0.030)
    save(fig, "fig_matching.png")


# ═════════════════════════════════════════════════ Fig 4: Fraud pipeline
def fig_fraud():
    fig, ax = canvas(11.2, 7.6, "Multi-Signal Fraud Detection",
                     "cheap deterministic arithmetic selects who to examine; "
                     "the language model is consulted only afterwards")

    box(ax, 0.030, 0.836, 0.200, 0.070, "Runner price\nclaim", bold=True, fs=8.2)
    box(ax, 0.268, 0.836, 0.215, 0.070, "Reference price\nitem × store", fs=8.2)
    box(ax, 0.521, 0.836, 0.215, 0.070, "Robust estimate\nmedian · MAD", fs=8.2)
    box(ax, 0.774, 0.836, 0.200, 0.070, "Shrinkage\nby evidence", fs=8.2)
    arrow(ax, (0.230, 0.871), (0.268, 0.871))
    arrow(ax, (0.483, 0.871), (0.521, 0.871))
    arrow(ax, (0.736, 0.871), (0.774, 0.871))

    ax.text(0.5, 0.792, "THREE  INDEPENDENT  DETECTORS", ha="center", va="center",
            fontsize=7.8, color=GREY, fontweight="bold")

    box(ax, 0.030, 0.540, 0.295, 0.222,
        "PRICE  INFLATION\nper claim\n\n"
        "scaled tolerance\nstore-adjusted reference\n\n"
        "OK  ·  ELEVATED  ·  FLAGGED",
        fill=FILL_2, lw=1.8, fs=8.2)
    box(ax, 0.352, 0.540, 0.295, 0.222,
        "RATING  FARMING\nper runner\n\n"
        "concentration\nfriend–stranger gap\npost-penalty burst\n"
        "untested reputation",
        fill=FILL_2, lw=1.8, fs=8.2)
    box(ax, 0.674, 0.540, 0.295, 0.222,
        "COLLUSION  RING\nper group\n\n"
        "closed PAID cycle (SCC)\nmutual friends · repeated laps\n"
        "excess over policy expectation",
        fill=FILL_2, lw=1.8, fs=8.2)

    arrow(ax, (0.130, 0.836), (0.130, 0.762))
    arrow(ax, (0.874, 0.836), (0.874, 0.762))

    box(ax, 0.250, 0.404, 0.500, 0.070,
        "LLM corroboration   ·   do these errands read as genuine?",
        lw=1.6, bold=True, fs=8.6)
    arrow(ax, (0.177, 0.540), (0.330, 0.474), rad=0.10)
    arrow(ax, (0.500, 0.540), (0.500, 0.474))
    arrow(ax, (0.822, 0.540), (0.670, 0.474), rad=-0.10)

    box(ax, 0.320, 0.276, 0.360, 0.068, "Fraud flag   ·   severity 1–3", bold=True)
    arrow(ax, (0.500, 0.404), (0.500, 0.344))

    box(ax, 0.040, 0.118, 0.265, 0.080, "Escrow withheld\nhold → PENDING_REVIEW", fs=8)
    box(ax, 0.368, 0.118, 0.265, 0.080, "Admin review\nuphold / dismiss", fs=8)
    box(ax, 0.696, 0.118, 0.265, 0.080, "Ranking penalty\ndemote, never ban", fs=8)
    arrow(ax, (0.420, 0.276), (0.190, 0.198), rad=0.10)
    arrow(ax, (0.500, 0.276), (0.500, 0.198))
    arrow(ax, (0.580, 0.276), (0.810, 0.198), rad=-0.10)

    footnote(ax, "No detector punishes on its own: an unreviewed flag may demote a "
                 "runner in ranking, never remove them from the platform.", y=0.036)
    save(fig, "fig_fraud.png")


# ══════════════════════════════════════════ Fig 5: Escrow / ledger
def fig_escrow():
    fig, ax = canvas(10.8, 7.6, "Escrow and the Append-Only Ledger",
                     "the balance is derived — Σ credits − Σ debits — never stored "
                     "and never mutated")

    box(ax, 0.040, 0.745, 0.180, 0.075, "OPEN\nhold placed", bold=True, fs=8.2)
    box(ax, 0.310, 0.745, 0.180, 0.075, "HELD\nin escrow", fill=FILL_2, lw=2.0,
        bold=True, fs=8.2)
    box(ax, 0.600, 0.840, 0.185, 0.065, "RELEASED", bold=True, fs=8.2)
    box(ax, 0.600, 0.750, 0.185, 0.065, "REFUNDED", bold=True, fs=8.2)
    box(ax, 0.600, 0.660, 0.185, 0.065, "PENDING_REVIEW", bold=True, fs=7.6)
    box(ax, 0.840, 0.740, 0.120, 0.085, "Admin\nverdict", fill=FILL_2, lw=1.8, fs=8)

    arrow(ax, (0.220, 0.7825), (0.310, 0.7825))
    alabel(ax, 0.265, 0.806, "funds locked")
    arrow(ax, (0.490, 0.795), (0.600, 0.8725), rad=-0.12)
    alabel(ax, 0.545, 0.848, "delivered")
    arrow(ax, (0.490, 0.7825), (0.600, 0.7825))
    alabel(ax, 0.545, 0.800, "cancelled")
    arrow(ax, (0.490, 0.770), (0.600, 0.6925), rad=0.12)
    alabel(ax, 0.545, 0.716, "flagged")
    arrow(ax, (0.785, 0.6925), (0.888, 0.740), rad=-0.14)
    arrow(ax, (0.876, 0.825), (0.788, 0.862), rad=0.22)
    alabel(ax, 0.872, 0.898, "dismiss → pay runner", fs=6.8)
    arrow(ax, (0.840, 0.772), (0.786, 0.778), rad=0.30)
    alabel(ax, 0.900, 0.706, "uphold → refund", fs=6.8)

    ax.add_patch(FancyBboxPatch(
        (0.030, 0.078), 0.945, 0.520, boxstyle="round,pad=0.006,rounding_size=0.014",
        facecolor=WHITE, edgecolor=BLACK, linewidth=1.3, linestyle="dashed", zorder=0))
    ax.text(0.060, 0.560, "LEDGER   —   append-only, one row per movement of money",
            ha="left", va="center", fontsize=8.8, fontweight="bold", color=BLACK)

    entries = [("TOPUP", "credit"), ("HOLD", "debit"), ("REWARD", "credit"),
               ("REIMBURSE", "credit"), ("REFUND", "credit"), ("CLAWBACK", "debit")]
    for i, (t, d) in enumerate(entries):
        box(ax, 0.060 + i * 0.150, 0.428, 0.135, 0.072, f"{t}\n{d}", fs=7.6,
            fill=FILL_2 if d == "debit" else WHITE)

    box(ax, 0.060, 0.268, 0.415, 0.100,
        "INVARIANTS\namount > 0   ·   direction pinned per type\nreleased ≤ amount",
        fs=8.2)
    box(ax, 0.530, 0.268, 0.415, 0.100,
        "IDEMPOTENCY\nUNIQUE (errand, user, entry_type)\n"
        "a redelivered event collides, never pays twice",
        fs=8.2)

    ax.text(0.5, 0.192, "balance   =   Σ credits   −   Σ debits", ha="center",
            va="center", fontsize=11, fontweight="bold", color=BLACK)
    ax.text(0.5, 0.136, "no balance column exists anywhere in the schema",
            ha="center", va="center", fontsize=7.4, color=GREY, style="italic")

    footnote(ax, "A refund appends a credit rather than editing a balance, so a "
                 "cancelled errand and its repayment both stay on the record.", y=0.018)
    save(fig, "fig_escrow.png")


# ═══════════════════════════════════ Fig 6: Social graph & ring detection
def fig_social():
    fig, ax = canvas(11.0, 6.6, "Social Graph and Collusion-Ring Detection",
                     "closure says a group could collude; only circulating money "
                     "says it does")

    ax.text(0.235, 0.855, "HONEST  FRIEND  GROUP", ha="center", fontsize=8.6,
            fontweight="bold", color=BLACK)
    ax.text(0.765, 0.855, "COLLUSION  RING", ha="center", fontsize=8.6,
            fontweight="bold", color=BLACK)
    ax.plot([0.5, 0.5], [0.135, 0.885], color=LINE, lw=0.9, ls="dashed", zorder=0)

    # The axes are 0..1 in both directions on a non-square canvas, so a true
    # Circle draws as an ellipse. Correct the width by the aspect ratio.
    ar = 6.6 / 11.0

    def node(cx, cy, label, r=0.030, bold=False):
        ax.add_patch(Ellipse((cx, cy), width=2 * r * ar, height=2 * r,
                             facecolor=WHITE, edgecolor=BLACK,
                             linewidth=1.6 if bold else 1.1, zorder=3))
        ax.text(cx, cy, label, ha="center", va="center", fontsize=8,
                fontweight="bold" if bold else "normal", zorder=4)

    # honest: closed friendships, money leaves the group
    hon = {"A": (0.155, 0.700), "B": (0.315, 0.700), "C": (0.235, 0.560)}
    for k, (x, y) in hon.items():
        node(x, y, k)
    for a, b in (("A", "B"), ("B", "C"), ("A", "C")):
        ax.plot(*zip(hon[a], hon[b]), color=BLACK, lw=1.1, zorder=1)
    for k, out in (("A", (0.075, 0.430)), ("B", (0.395, 0.430))):
        arrow(ax, hon[k], out, ls="dashed")
    node(0.075, 0.400, "S", r=0.026)
    node(0.395, 0.400, "S", r=0.026)
    ax.text(0.235, 0.330, "money leaves the group\ncirculation  LOW",
            ha="center", va="center", fontsize=8, color=INK)

    # ring: closed friendships AND a closed payment cycle
    ring = {"X": (0.685, 0.700), "Y": (0.845, 0.700), "Z": (0.765, 0.560)}
    for k, (x, y) in ring.items():
        node(x, y, k, bold=True)
    for a, b in (("X", "Y"), ("Y", "Z"), ("X", "Z")):
        ax.plot(*zip(ring[a], ring[b]), color=BLACK, lw=1.1, zorder=1)
    arrow(ax, (0.715, 0.716), (0.815, 0.716), lw=2.0, rad=-0.30)
    arrow(ax, (0.855, 0.672), (0.795, 0.582), lw=2.0, rad=-0.30)
    arrow(ax, (0.735, 0.582), (0.675, 0.672), lw=2.0, rad=-0.30)
    ax.text(0.765, 0.330, "money returns to its source\ncirculation  HIGH",
            ha="center", va="center", fontsize=8, color=INK)

    ax.text(0.235, 0.470, "FRIEND edges", ha="center", fontsize=7.2, color=GREY)
    ax.text(0.765, 0.470, "FRIEND + closed PAID cycle", ha="center", fontsize=7.2,
            color=GREY)

    box(ax, 0.075, 0.150, 0.390, 0.130,
        "IDENTICAL  STRUCTURE\n\nboth groups are fully closed:\n"
        "closure = 1.0, every friendship internal",
        fs=8.2)
    box(ax, 0.535, 0.150, 0.390, 0.130,
        "THE  DISCRIMINATOR\n\ndirected PAID cycle (Tarjan SCC)\n"
        "≥ 3 members · ≥ 2 laps · leg value floor",
        fill=FILL_2, lw=2.0, fs=8.2)

    footnote(ax, "Structure alone cannot separate a genuine friend group from a ring; "
                 "both look equally closed.", y=0.055)
    save(fig, "fig_social.png")




# ══════════════════════════════════════════════ Fig 7: Sequence diagram
def fig_sequence():
    fig, ax = canvas(11.6, 9.2, "Sequence — Post · Offer · Accept · Deliver · Settle",
                     "the settlement path is asynchronous: money moves only on an "
                     "ORDER_COMPLETED event, and only once")

    actors = [
        (0.075, "Requester"), (0.212, "API"), (0.348, "Matching"),
        (0.484, "Ledger"), (0.620, "Runner"), (0.756, "Outbox\n+ Kafka"),
        (0.905, "Settlement\nconsumer"),
    ]
    TOP, BOT = 0.878, 0.058
    for x, name in actors:
        box(ax, x - 0.062, TOP, 0.124, 0.052, name, fs=7.8, bold=True)
        ax.plot([x, x], [BOT, TOP], color=LINE, lw=0.9, ls=(0, (4, 4)), zorder=0)

    R, A, M, L, U, K, S = [a[0] for a in actors]

    def msg(y, x1, x2, text, ls="solid", fs=7.2):
        arrow(ax, (x1, y), (x2, y), ls=ls)
        mid = (x1 + x2) / 2
        ax.text(mid, y + 0.014, text, ha="center", va="bottom", fontsize=fs,
                color=INK, zorder=4,
                bbox=dict(boxstyle="round,pad=0.16", fc=WHITE, ec="none"))

    def selfmsg(y, x, text, fs=7.2):
        ax.plot([x, x + 0.052, x + 0.052, x], [y, y, y - 0.026, y - 0.026],
                color=BLACK, lw=1.0, zorder=1)
        arrow(ax, (x + 0.030, y - 0.026), (x, y - 0.026))
        ax.text(x + 0.062, y - 0.013, text, ha="left", va="center", fontsize=fs,
                color=INK, zorder=4,
                bbox=dict(boxstyle="round,pad=0.16", fc=WHITE, ec="none"))

    msg(0.836, R, A, "POST /errands")
    msg(0.800, A, L, "place_hold  (reward + items)")
    selfmsg(0.766, L, "lock wallet row · balance ≥ total · write HOLD debit")
    msg(0.708, A, M, "dispatch round 1")
    selfmsg(0.674, M, "Redis GEO · drop co-ringed · score · ε-explore?")
    msg(0.616, M, U, "offer  (fan-out, ≤ 2 hops for 45 s)")
    selfmsg(0.582, M, "write OFFER LOG  ·  candidates + terms + explored?")

    ax.plot([0.045, 0.960], [0.540, 0.540], color=LINE, lw=0.8, ls="dotted", zorder=0)
    ax.text(0.045, 0.548, "first runner to accept wins the Redis lock", fontsize=7,
            color=GREY, style="italic", ha="left")

    msg(0.508, U, A, "POST /accept")
    selfmsg(0.474, A, "SET NX lock · row lock · ACCEPTED")
    msg(0.416, A, M, "stamp accepted_runner on the offer round")
    msg(0.380, U, A, "picked up  →  delivered")
    msg(0.344, R, A, "confirm handoff")
    msg(0.308, A, K, "ORDER_COMPLETED  (same transaction)", ls="dashed")
    msg(0.272, K, S, "consume", ls="dashed")
    selfmsg(0.238, S, "judge price claims · eligible vs withheld")
    msg(0.188, S, L, "release_hold  (reward + reimbursement)")
    selfmsg(0.158, L, "REWARD + REIMBURSE credits · surplus refunded")

    box(ax, 0.640, 0.066, 0.330, 0.040,
        "withheld > 0  →  hold stays PENDING_REVIEW", fill=FILL_2, lw=1.4, fs=7.2)

    footnote(ax, "Dashed arrows cross the asynchronous boundary. The event is written "
                 "to the outbox in the same transaction as the status change, so it can "
                 "never be lost or phantom.", y=0.014)
    save(fig, "fig_sequence.png")


# ═══════════════════════════════════════════════════ Fig 1: Gantt chart
def fig_gantt():
    import matplotlib.dates as mdates
    from datetime import date

    tasks = [
        ("Requirement study & SRS", date(2026, 7, 6), date(2026, 7, 26), 0),
        ("Architecture & schema design", date(2026, 7, 20), date(2026, 8, 9), 0),
        ("Sprint 1 - auth, profiles, campus", date(2026, 8, 3), date(2026, 8, 16), 1),
        ("Sprint 2 - errands, geo matching", date(2026, 8, 10), date(2026, 8, 30), 1),
        ("Sprint 3 - escrow ledger, wallet", date(2026, 8, 24), date(2026, 9, 13), 1),
        ("Sprint 4 - social graph, trust rank", date(2026, 9, 7), date(2026, 9, 27), 1),
        ("Sprint 5 - fraud detection, LLM", date(2026, 9, 21), date(2026, 10, 11), 1),
        ("Sprint 6 - offer log & exploration", date(2026, 10, 5), date(2026, 10, 18), 1),
        ("Evaluation & ablation study", date(2026, 10, 12), date(2026, 10, 25), 2),
        ("Report & documentation", date(2026, 10, 19), date(2026, 10, 31), 2),
    ]
    fills = {0: WHITE, 1: FILL_2, 2: FILL_3}

    fig, ax = plt.subplots(figsize=(11.0, 5.0))
    for i, (name, s, e, kind) in enumerate(tasks):
        y = len(tasks) - i - 1
        ax.barh(y, (e - s).days, left=s, height=0.52, color=fills[kind],
                edgecolor=BLACK, linewidth=1.1, zorder=3)
        ax.text(mdates.date2num(s) + (e - s).days / 2, y, f"{(e - s).days} d",
                ha="center", va="center", fontsize=6.8, color=GREY, zorder=4)

    ax.set_yticks(range(len(tasks)))
    ax.set_yticklabels([t[0] for t in reversed(tasks)], fontsize=8.2)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.tick_params(axis="x", labelsize=7.6, rotation=0)
    ax.grid(axis="x", color=LINE, lw=0.6, ls="dotted", zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(LINE)
    ax.set_title("Project Plan — Agile, six sprints", fontsize=11.5,
                 fontweight="bold", color=BLACK, pad=14)
    ax.set_xlim(date(2026, 7, 1), date(2026, 11, 5))
    fig.text(0.5, -0.02,
             "White = analysis and design.   Light = implementation sprints.   "
             "Dark = evaluation and write-up.   Sprints overlap by one week for "
             "review and carry-over.",
             ha="center", fontsize=7.2, color=GREY, style="italic")
    fig.savefig(OUT / "fig_gantt.png")
    plt.close(fig)
    print("  fig_gantt.png")


if __name__ == "__main__":
    print("figures ->", OUT)
    fig_gantt()          # Fig. 1  project plan
    fig_architecture()   # Fig. 2  system architecture
    fig_matching()       # Fig. 3  matching + exploration
    fig_fraud()          # Fig. 4  fraud detection
    fig_escrow()         # Fig. 5  escrow and ledger
    fig_social()         # Fig. 6  social graph / ring detection
    fig_sequence()       # Fig. 7  end-to-end sequence
