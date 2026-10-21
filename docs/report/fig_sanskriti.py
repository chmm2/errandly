"""Figures for Sanskriti's Review-2 slides.

    python docs/report/fig_sanskriti.py

Two diagrams and one chart, all monochrome, all computed from the constants the
deployed system uses so they cannot drift from the code.

The decay figure is the important one: it has to show not just THAT trust decays
with age, but that it is the NEWEST edge on a path that decides — which is the
part the surveyed literature does not model.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse

from figures import (
    BLACK, FILL_2, FILL_3, GREY, INK, LINE, WHITE, arrow, box, canvas, save,
)

# mirrors app/modules/social/service.py
HOP_DECAY = 0.45
MATURITY_DAYS = 30.0
NEW_FLOOR = 0.40
SOCIAL_WEIGHT_M = 1500.0


def maturity(days):
    if days >= MATURITY_DAYS:
        return 1.0
    return NEW_FLOOR + (1.0 - NEW_FLOOR) * (max(0.0, days) / MATURITY_DAYS)


def _node(ax, x, y, label, ar, r=0.030, bold=False):
    ax.add_patch(Ellipse((x, y), width=2 * r * ar, height=2 * r,
                         facecolor=WHITE, edgecolor=BLACK,
                         linewidth=1.8 if bold else 1.2, zorder=3))
    ax.text(x, y, label, ha="center", va="center", fontsize=9,
            fontweight="bold" if bold else "normal", zorder=4)


# ══════════════════════════════════════════ which edge decides, and the ramp
def fig_newest_edge():
    fig, ax = canvas(11.4, 5.4, "Trust Decays With The AGE Of The Newest Link",
                     "not the average age of the path — the most recently "
                     "created edge on it")
    ar = 5.4 / 11.4

    # ── left: two paths, same length, different newest edge
    ax.text(0.245, 0.795, "SAME  PATH  LENGTH,  DIFFERENT  ANSWER",
            ha="center", fontsize=9, fontweight="bold", color=GREY)

    # path 1 — both edges old
    y = 0.660
    for x, lab in ((0.075, "you"), (0.245, "B"), (0.415, "C")):
        _node(ax, x, y, lab, ar)
    ax.plot([0.075, 0.245], [y, y], color=BLACK, lw=1.4)
    ax.plot([0.245, 0.415], [y, y], color=BLACK, lw=1.4)
    ax.text(0.160, y + 0.048, "2 years", ha="center", fontsize=8, color=GREY)
    ax.text(0.330, y + 0.048, "1 year", ha="center", fontsize=8, color=GREY)
    ax.text(0.470, y, "trust  0.45", ha="left", va="center", fontsize=9.5,
            fontweight="bold")
    ax.text(0.470, y - 0.055, "675 m", ha="left", va="center", fontsize=8.5,
            color=GREY)

    # path 2 — one fresh edge
    y = 0.455
    for x, lab in ((0.075, "you"), (0.245, "B"), (0.415, "C")):
        _node(ax, x, y, lab, ar)
    ax.plot([0.075, 0.245], [y, y], color=BLACK, lw=1.4)
    ax.plot([0.245, 0.415], [y, y], color=BLACK, lw=3.0)
    ax.text(0.160, y + 0.048, "2 years", ha="center", fontsize=8, color=GREY)
    ax.text(0.330, y + 0.048, "1 DAY", ha="center", fontsize=8.5,
            fontweight="bold", color=INK)
    ax.text(0.470, y, "trust  0.19", ha="left", va="center", fontsize=9.5,
            fontweight="bold")
    ax.text(0.470, y - 0.055, "284 m", ha="left", va="center", fontsize=8.5,
            color=GREY)

    # No pointer arrow here: it ran straight through the "1 DAY" label, and the
    # heavier line already carries the emphasis.
    ax.text(0.245, 0.290,
            "One fresh link drags the whole path down.\n"
            "A chain of trust is only as established as its newest link.",
            ha="center", va="top", fontsize=9, color=INK, linespacing=1.5)

    ax.plot([0.575, 0.575], [0.135, 0.800], color=LINE, lw=0.9, ls="dashed")

    # ── right: the ramp
    ax.text(0.800, 0.795, "HOW  A  FRIENDSHIP  MATURES",
            ha="center", fontsize=9, fontweight="bold", color=GREY)

    x0, x1 = 0.645, 0.960
    y0, y1 = 0.240, 0.700
    ax.plot([x0, x1], [y0, y0], color=LINE, lw=1.0)
    ax.plot([x0, x0], [y0, y1], color=LINE, lw=1.0)

    def px(d):      # 0..45 days -> x
        return x0 + (min(d, 45) / 45) * (x1 - x0)

    def py(w):      # 0..1 weight -> y
        return y0 + w * (y1 - y0)

    days = [d / 2 for d in range(0, 91)]
    ax.plot([px(d) for d in days], [py(maturity(d)) for d in days],
            color=BLACK, lw=2.2)
    ax.plot([x0, x1], [py(1.0), py(1.0)], color=LINE, lw=0.8, ls="dotted")
    ax.plot([px(30), px(30)], [y0, py(1.0)], color=LINE, lw=0.8, ls="dotted")

    for d in (0, 30):
        ax.plot([px(d)], [py(maturity(d))], "o", color=BLACK, ms=6)
    ax.text(px(0) + 0.010, py(maturity(0)) - 0.045, "0.40\nbrand new",
            fontsize=8.5, color=INK, linespacing=1.4)
    # Above the gridline rather than on it.
    ax.text(px(30) - 0.008, py(1.0) + 0.028, "1.00   full weight",
            ha="right", fontsize=8.5, color=INK)
    ax.text((x0 + x1) / 2, y0 - 0.062, "age of the newest link  (days)",
            ha="center", fontsize=8.5, color=GREY)
    ax.text(x0 - 0.012, (y0 + y1) / 2, "weight", ha="center", va="center",
            fontsize=8.5, color=GREY, rotation=90)
    ax.text(px(30), y0 - 0.030, "30", ha="center", fontsize=8, color=GREY)
    ax.text(px(0), y0 - 0.030, "0", ha="center", fontsize=8, color=GREY)

    ax.text(0.800, 0.105,
            "Old edges are never decayed — age makes a friendship\n"
            "stronger evidence, not weaker.",
            ha="center", va="top", fontsize=9, color=INK, linespacing=1.5)

    save(fig, "fig_sk_decay.png")


# ═══════════════════════════════════════════════════ how far trust reaches
def fig_hops():
    fig, ax = canvas(11.0, 5.6, "How Far Trust Reaches",
                     "a friend is worth 1500 metres of walking; everything else "
                     "is a fraction of that")
    ar = 5.6 / 11.0

    xs = [0.100, 0.290, 0.480, 0.670, 0.860]
    labels = ["you", "friend", "friend of\na friend", "3 hops", "4 hops"]
    trusts = [None, 1.0, 0.45, 0.2025, 0.0911]
    y = 0.620

    for i, (x, lab) in enumerate(zip(xs, labels)):
        # labelled beneath, not inside — "you" overflowed the circle
        _node(ax, x, y, "", ar, r=0.034, bold=(i <= 1))
        if i:
            ax.plot([xs[i - 1], x], [y, y], color=BLACK, lw=1.4, zorder=1)
        ax.text(x, y - 0.090, lab if i else "", ha="center", va="top",
                fontsize=8.6, color=INK, linespacing=1.35)

    ax.text(0.100, y - 0.090, "you", ha="center", va="top", fontsize=8.6,
            fontweight="bold")

    for x, t in zip(xs[1:], trusts[1:]):
        ax.text(x, 0.375, f"{t:.2f}", ha="center", fontsize=11,
                fontweight="bold")
        ax.text(x, 0.310, f"{t * SOCIAL_WEIGHT_M:.0f} m", ha="center",
                fontsize=9, color=GREY)

    ax.text(0.100, 0.375, "trust", ha="center", fontsize=9, color=GREY)
    ax.text(0.100, 0.310, "head start", ha="center", fontsize=9, color=GREY)

    box(ax, 0.075, 0.115, 0.400, 0.130,
        "Each hop keeps 45% of the last.\n"
        "By four hops it is about 9% — enough to\n"
        "prefer a connected stranger over a total one.",
        fs=8.8)
    box(ax, 0.525, 0.115, 0.400, 0.130,
        "Past four hops, a path exists but means\n"
        "nothing. Those candidates are treated\n"
        "as strangers.",
        fill=FILL_2, lw=1.6, fs=8.8)

    ax.text(0.5, 0.045,
            "Offers are also withheld beyond two hops for the first 45 seconds — "
            "that, not the sort order, is what gives someone you know first "
            "refusal.",
            ha="center", fontsize=8.8, color=GREY, style="italic")
    save(fig, "fig_sk_hops.png")


# ═══════════════════════════════════════════ what the attack costs, before/after
def fig_attack_cost():
    fig, ax = plt.subplots(figsize=(9.6, 3.6))

    rows = [
        ("befriend them TODAY", 630),
        ("after one week", 810),
        ("after one month", 1500),
    ]
    y = list(range(len(rows)))[::-1]
    for (label, m), yy in zip(rows, y):
        ax.barh(yy, m, height=0.5, facecolor=FILL_3 if m < 1500 else WHITE,
                edgecolor=BLACK, lw=1.3)
        ax.text(m + 30, yy, f"{m} m", va="center", fontsize=10,
                fontweight="bold")

    ax.set_yticks(y)
    ax.set_yticklabels([r[0] for r in rows], fontsize=10)
    ax.set_xlim(0, 1850)
    ax.set_xticks([0, 500, 1000, 1500])
    ax.set_xlabel("head start the friendship is worth, in metres", fontsize=9.5)
    ax.tick_params(labelsize=9)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(LINE)
    ax.set_title("What a same-day friendship actually buys",
                 fontsize=12, fontweight="bold", pad=14)
    fig.text(0.5, -0.04,
             "A friendship made this morning is worth 630 m, not 1500 m — "
             "enough to matter between comparable candidates, not enough to "
             "beat a genuinely nearby stranger.",
             ha="center", fontsize=8.5, color=GREY, style="italic")
    fig.savefig("figures/fig_sk_attack.png", dpi=200, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)
    print("  fig_sk_attack.png")


if __name__ == "__main__":
    print("figures ->")
    fig_newest_edge()
    fig_hops()
    fig_attack_cost()
