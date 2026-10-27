"""Figures for Chris's Review-2 slides.

    python docs/report/fig_chris.py

Monochrome, no decoration. Every number is either measured on the running stack
or produced by the simulation whose parameters are stated on the slide.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from figures import (
    BLACK, FILL_1, FILL_2, FILL_3, GREY, INK, LINE, WHITE,
    arrow, box, canvas, save,
)


# ═══════════════════════════════════════════ the boost blinds the detector
def fig_boost():
    """The centrepiece of the flaw slide: the ring never changes, we do."""
    fig, ax = plt.subplots(figsize=(10.6, 4.6))

    rows = [
        ("no boost", 40),
        ("medium\n750 m", 88),
        ("OURS\n1500 m", 99),
        ("very high\n2500 m", 100),
    ]
    y = list(range(len(rows)))[::-1]

    for (label, given), yy in zip(rows, y):
        # what the app hands them anyway
        ax.barh(yy, given, height=0.5, facecolor=FILL_3, edgecolor=BLACK, lw=1.2)
        # what the ring adds on top
        ax.barh(yy, 100 - given, left=given, height=0.5, facecolor=WHITE,
                edgecolor=BLACK, lw=1.2, hatch="///")
        ax.text(given / 2, yy, f"{given}", ha="center", va="center", fontsize=9.5)
        if 100 - given >= 6:
            ax.text(given + (100 - given) / 2, yy, f"+{100 - given}",
                    ha="center", va="center", fontsize=9.5, fontweight="bold")
        else:
            ax.text(101.5, yy, f"+{100 - given}", ha="left", va="center",
                    fontsize=9.5, fontweight="bold")
        verdict = "obvious" if 100 - given >= 12 else "invisible"
        ax.text(118, yy, verdict, ha="left", va="center", fontsize=9,
                color=INK if verdict == "obvious" else GREY,
                fontweight="bold" if verdict == "invisible" else "normal")

    ax.set_yticks(y)
    ax.set_yticklabels([r[0] for r in rows], fontsize=9.5)
    ax.set_xlim(0, 140)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xlabel("out of every 100 errands the group posts", fontsize=9.5)
    ax.tick_params(labelsize=9)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(LINE)

    ax.set_title("The ring always takes 100.  Only our own routing changes.",
                 fontsize=12, fontweight="bold", pad=26)
    # Legend as a figure-level line under the title: placing it in data
    # coordinates put it on top of the title.
    fig.text(0.5, 0.925,
             "grey = what our app hands them anyway        "
             "hatched = the extra they caused",
             ha="center", fontsize=8.5, color=GREY)

    fig.text(0.5, -0.03,
             "Simulation: 60 students, 6000 errands, six honest friend groups, "
             "one ring taking each other's errands 85% of the time.",
             ha="center", fontsize=8, color=GREY, style="italic")
    fig.savefig("figures/fig_boost.png", dpi=200, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)
    print("  fig_boost.png")


# ═══════════════════════════════════════════════════ exploration restores it
def fig_explore():
    fig, ax = plt.subplots(figsize=(9.0, 3.4))
    rows = [("no exploration", 99), ("5% blind", 96), ("10% blind", 93)]
    y = list(range(len(rows)))[::-1]

    for (label, given), yy in zip(rows, y):
        ax.barh(yy, given, height=0.48, facecolor=FILL_3, edgecolor=BLACK, lw=1.2)
        ax.barh(yy, 100 - given, left=given, height=0.48, facecolor=WHITE,
                edgecolor=BLACK, lw=1.2, hatch="///")
        ax.text(given / 2, yy, f"{given}", ha="center", va="center", fontsize=9.5)
        ax.text(101.5, yy, f"+{100 - given}", ha="left", va="center",
                fontsize=9.5, fontweight="bold")
        ax.text(112, yy, "invisible" if 100 - given < 3 else "we can see it",
                ha="left", va="center", fontsize=9,
                fontweight="bold" if 100 - given >= 3 else "normal",
                color=GREY if 100 - given < 3 else INK)

    ax.set_yticks(y)
    ax.set_yticklabels([r[0] for r in rows], fontsize=9.5)
    ax.set_xlim(0, 145)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xlabel("out of every 100 errands, at our own 1500 m setting", fontsize=9.5)
    ax.tick_params(labelsize=9)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(LINE)
    ax.set_title("Exploration does not change the ring. It lowers what we hand them.",
                 fontsize=11.5, fontweight="bold", pad=16)
    fig.savefig("figures/fig_explore.png", dpi=200, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)
    print("  fig_explore.png")


# ═══════════════════════════════════════════════════════════ rating farming
def fig_farming():
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.0))
    fig.subplots_adjust(wspace=0.32)

    # left: the gap
    ax = axes[0]
    people = ["Karan\n(farming)", "Meera\n(genuinely liked)"]
    friends = [5.0, 4.7]
    strangers = [3.4, 4.7]
    x = [0, 1]
    w = 0.34
    ax.bar([i - w / 2 for i in x], friends, width=w, facecolor=FILL_3,
           edgecolor=BLACK, lw=1.3, label="friends say")
    ax.bar([i + w / 2 for i in x], strangers, width=w, facecolor=WHITE,
           edgecolor=BLACK, lw=1.3, label="strangers say")
    for i, (f, s) in enumerate(zip(friends, strangers)):
        ax.text(i - w / 2, f + 0.08, f"{f:.1f}", ha="center", fontsize=9)
        ax.text(i + w / 2, s + 0.08, f"{s:.1f}", ha="center", fontsize=9)
        gap = f - s
        ax.text(i, 5.75, f"gap {gap:.1f}", ha="center", fontsize=9.5,
                fontweight="bold" if gap >= 0.8 else "normal",
                color=INK if gap >= 0.8 else GREY)
        ax.text(i, 5.45, "FLAGGED" if gap >= 0.8 else "clean", ha="center",
                fontsize=9, color=INK if gap >= 0.8 else GREY,
                fontweight="bold" if gap >= 0.8 else "normal")
    ax.set_xticks(x)
    ax.set_xticklabels(people, fontsize=9.5)
    ax.set_ylim(0, 6.3)
    ax.set_ylabel("stars", fontsize=9.5)
    ax.set_title("Same number of friend ratings.\nOnly the gap differs.",
                 fontsize=11, fontweight="bold", pad=10)
    ax.legend(fontsize=8.5, frameon=False, loc="lower right")
    ax.tick_params(labelsize=9)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(LINE)
    ax.spines["bottom"].set_color(LINE)

    # right: a few ratings barely move you
    ax = axes[1]
    votes = [0.25, 1, 2, 4, 8, 20, 50]
    scores = [3.55, 3.67, 3.80, 4.00, 4.25, 4.57, 4.79]
    ax.plot(range(len(votes)), scores, color=BLACK, lw=1.8, marker="o", ms=5)
    ax.axhline(3.5, color=LINE, lw=0.9, ls="dotted")
    ax.text(0.1, 3.42, "neutral 3.5", fontsize=8.5, color=GREY)
    for i, (v, s) in enumerate(zip(votes, scores)):
        ax.annotate(f"{s:.2f}", (i, s), textcoords="offset points",
                    xytext=(0, 8), ha="center", fontsize=8.5)
    ax.plot([0], [3.55], "o", color=BLACK, ms=9, mfc=WHITE, mew=1.8)
    ax.annotate("10 fake ratings\nfrom one friend\nland here",
                (0, 3.55), textcoords="offset points", xytext=(18, -34),
                fontsize=8.5, color=INK,
                arrowprops=dict(arrowstyle="->", color=BLACK, lw=1.0))
    ax.set_xticks(range(len(votes)))
    ax.set_xticklabels([str(v) for v in votes], fontsize=9)
    ax.set_xlabel("how many people effectively rated them", fontsize=9.5)
    ax.set_ylabel("score matching sees", fontsize=9.5)
    ax.set_ylim(3.3, 5.1)
    ax.set_title("Everyone here has a perfect 5.0 average.",
                 fontsize=11, fontweight="bold", pad=10)
    ax.tick_params(labelsize=9)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(LINE)
    ax.spines["bottom"].set_color(LINE)

    fig.savefig("figures/fig_farming.png", dpi=200, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)
    print("  fig_farming.png")


# ══════════════════════════════════════════════════════════ the offer log
def fig_offerlog():
    fig, ax = canvas(10.8, 5.0, "One Row Of The Offer Log",
                     "written on every dispatch round, read by nothing on the "
                     "request path")

    hdr = ["runner", "distance", "friend bonus", "rating", "penalty", "score", ""]
    rows = [
        ["Ujjwal  (friend)", "695 m", "− 750 m", "0", "0", "− 55", "took it"],
        ["stranger A", "31 m", "0", "0", "0", "31", ""],
        ["stranger B", "1200 m", "0", "− 400", "0", "800", ""],
    ]
    xs = [0.055, 0.255, 0.375, 0.520, 0.625, 0.730, 0.845]
    for x, h in zip(xs, hdr):
        ax.text(x, 0.735, h, fontsize=8.6, fontweight="bold", color=INK)
    ax.plot([0.045, 0.960], [0.712, 0.712], color=BLACK, lw=1.1)
    for i, row in enumerate(rows):
        y = 0.655 - i * 0.075
        for x, v in zip(xs, row):
            ax.text(x, y, v, fontsize=8.6, color=INK,
                    fontweight="bold" if i == 0 and v in ("− 55", "took it") else "normal")
    ax.plot([0.045, 0.960], [0.415, 0.415], color=LINE, lw=0.8)

    box(ax, 0.055, 0.255, 0.400, 0.115,
        "WITH the friend bonus\nUjjwal scores −55  →  he wins",
        fill=FILL_2, lw=1.8, fs=9.5, bold=True)
    box(ax, 0.545, 0.255, 0.400, 0.115,
        "WITHOUT it\nUjjwal scores 695  →  stranger A wins",
        lw=1.8, fs=9.5, bold=True)
    arrow(ax, (0.455, 0.312), (0.545, 0.312))

    ax.text(0.5, 0.175,
            "So the app caused that pairing. It is not evidence of anything.",
            ha="center", fontsize=10, fontweight="bold", color=INK)
    ax.text(0.5, 0.085,
            "Saving only the final score would make this question unanswerable — "
            "you cannot take −55 apart again.",
            ha="center", fontsize=8.6, color=GREY, style="italic")
    save(fig, "fig_offerlog.png")


# ══════════════════════════════════════════════════════════════════ the LLM
def fig_llm():
    fig, ax = canvas(11.0, 5.6, "What The Language Model Is For",
                     "structure and money answer who and how much — neither "
                     "answers what for")

    from matplotlib.patches import Ellipse
    ar = 5.6 / 11.0        # axes are 0..1 both ways on a non-square canvas

    ax.text(0.255, 0.870, "THREE  ROOMMATES", ha="center", fontsize=9.5,
            fontweight="bold")
    ax.text(0.745, 0.870, "THREE  FARMERS", ha="center", fontsize=9.5,
            fontweight="bold")
    ax.plot([0.5, 0.5], [0.255, 0.845], color=LINE, lw=0.9, ls="dashed")

    for cx in (0.255, 0.745):
        pts = {"A": (cx - 0.070, 0.775), "B": (cx + 0.070, 0.775),
               "C": (cx, 0.680)}
        for a, b in (("A", "B"), ("B", "C"), ("A", "C")):
            ax.plot(*zip(pts[a], pts[b]), color=BLACK, lw=1.2, zorder=1)
        for x, y in pts.values():
            ax.add_patch(Ellipse((x, y), width=2 * 0.022 * ar, height=2 * 0.022,
                                 facecolor=WHITE, edgecolor=BLACK, lw=1.2,
                                 zorder=3))
    ax.text(0.5, 0.615, "identical shape  ·  identical money circulating",
            ha="center", fontsize=9, color=GREY, style="italic")

    box(ax, 0.045, 0.300, 0.410, 0.275,
        "THEIR  ERRANDS\n\n"
        "Tue 17:05   Foodys   samosa x2\n"
        "  “get the small one”\n"
        "Fri 09:20   Xerox shop   record sheets\n"
        "Sun 22:40   Health Centre   medicines\n\n"
        "different shops, odd hours, real notes",
        fs=8.6)
    box(ax, 0.545, 0.300, 0.410, 0.275,
        "THEIR  ERRANDS\n\n"
        "Tue 17:00   Foodys   snacks x1\n"
        "Tue 17:00   Foodys   snacks x1\n"
        "Tue 17:00   Foodys   snacks x1\n\n\n"
        "one shop, same wording, same hour",
        fill=FILL_2, lw=1.8, fs=8.6)

    box(ax, 0.235, 0.105, 0.530, 0.130,
        "MODEL'S ANSWER   (real output, qwen2.5:7b, run locally)\n"
        "reads_as_genuine: false  ·  coherence 35  ·  diversity 45\n"
        "“Near-identical titles and intervals”",
        fill=FILL_3, lw=1.8, fs=8.6, bold=True)
    arrow(ax, (0.700, 0.300), (0.660, 0.235))

    ax.text(0.5, 0.048,
            "Advisory only. It raises no flag, withholds no money, and cannot "
            "change a severity.",
            ha="center", fontsize=8.6, color=GREY, style="italic")
    save(fig, "fig_llm.png")


# ═════════════════════════════════════════════════════════════ penalisation
def fig_penalty():
    fig, ax = canvas(11.2, 5.8, "What A Flag Actually Does",
                     "one row, read by four different parts of the app — and a "
                     "human decides")

    box(ax, 0.290, 0.735, 0.420, 0.135,
        "ONE  ROW\nperson · rule · severity · status = OPEN\nmembers = [A, B, C]",
        fill=FILL_2, lw=2.2, fs=9.5, bold=True)

    outs = [
        (0.030, "Reputation\nalready discounted",
         "users.effective_reputation\nautomatic, no flag needed"),
        (0.278, "Pushed down\nthe queue",
         "700 m (farming) or 1200 m (ring)\nfades to 0 over 30 days"),
        (0.526, "Removed from\neach other's errands",
         "reads members list\nring flags only"),
        (0.774, "Shown to\nan admin",
         "the console lists OPEN flags"),
    ]
    for x, title, detail in outs:
        box(ax, x, 0.375, 0.196, 0.135, title, lw=1.6, fs=9, bold=True)
        ax.text(x + 0.098, 0.345, detail, ha="center", va="top", fontsize=7.6,
                color=GREY, linespacing=1.4)
    for x, _, _ in outs:
        arrow(ax, (0.500, 0.735), (x + 0.098, 0.510),
              rad=0.10 if x < 0.5 else -0.10)

    box(ax, 0.230, 0.120, 0.540, 0.100,
        "ADMIN:  dismiss  →  status becomes DISMISSED\n"
        "all four stop at once, because each only matches OPEN or UPHELD",
        fill=FILL_3, lw=1.8, fs=9, bold=True)
    # down the LEFT of the caption text, which sits centred under the box
    arrow(ax, (0.782, 0.375), (0.772, 0.222))

    ax.text(0.5, 0.048,
            "A severity-3 penalty is 1200 m — less than the 1500 m a friendship "
            "is worth. Suspicion demotes; it can never exclude.",
            ha="center", fontsize=8.8, color=INK, style="italic")
    save(fig, "fig_penalty.png")


if __name__ == "__main__":
    print("figures ->")
    fig_boost()
    fig_explore()
    fig_farming()
    fig_offerlog()
    fig_llm()
    fig_penalty()
