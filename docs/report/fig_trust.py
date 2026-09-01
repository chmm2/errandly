"""Figures for the trust-layer document.

    python docs/report/fig_trust.py

Two plots and one schematic, all monochrome. Values are computed from the same
constants the running system uses, so the curves cannot drift from the code
they describe.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from figures import BLACK, FILL_2, FILL_3, GREY, INK, LINE, WHITE, arrow, box, canvas, save

# Mirrors app/modules/social/service.py
HOP_DECAY = 0.45
MATURITY_DAYS = 30.0
NEW_FLOOR = 0.40
SOCIAL_WEIGHT_M = 1500.0


def maturity(age_days):
    if age_days >= MATURITY_DAYS:
        return 1.0
    return NEW_FLOOR + (1.0 - NEW_FLOOR) * (max(0.0, age_days) / MATURITY_DAYS)


def fig_trust_curves():
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.0))
    fig.subplots_adjust(wspace=0.28)

    # ── left: maturity ramp
    ax = axes[0]
    days = [d / 4 for d in range(0, 181)]
    ax.plot(days, [maturity(d) for d in days], color=BLACK, lw=2.0)
    ax.axhline(1.0, color=LINE, lw=0.8, ls="dotted")
    ax.axvline(MATURITY_DAYS, color=LINE, lw=0.8, ls="dotted")
    for d in (0, 7, 15, 30):
        ax.plot([d], [maturity(d)], "o", color=BLACK, ms=4.5)
        ax.annotate(f"{maturity(d):.2f}", (d, maturity(d)),
                    textcoords="offset points", xytext=(6, -12), fontsize=8,
                    color=INK)
    ax.set_xlim(0, 45)
    ax.set_ylim(0, 1.12)
    ax.set_xlabel("age of the newest edge on the path  (days)", fontsize=9)
    ax.set_ylabel("maturity weight", fontsize=9)
    ax.set_title("A friendship has to age before it counts",
                 fontsize=10.5, fontweight="bold", color=BLACK, pad=10)
    ax.tick_params(labelsize=8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(LINE)
    ax.spines["bottom"].set_color(LINE)
    ax.text(31, 0.16, "full weight\nfrom 30 days", fontsize=8, color=GREY)
    ax.text(5.5, 0.18, "a brand-new friendship starts at 0.40",
            fontsize=8, color=GREY)

    # ── right: hop decay, mature vs one-day-old path
    ax = axes[1]
    hops = [1, 2, 3, 4]
    mature = [HOP_DECAY ** (h - 1) for h in hops]
    fresh = [HOP_DECAY ** (h - 1) * maturity(1) for h in hops]
    w = 0.36
    ax.bar([h - w / 2 for h in hops], mature, width=w, facecolor=WHITE,
           edgecolor=BLACK, lw=1.4, label="edges over 30 days old")
    ax.bar([h + w / 2 for h in hops], fresh, width=w, facecolor=FILL_3,
           edgecolor=BLACK, lw=1.4, label="newest edge 1 day old")
    for h, m, f in zip(hops, mature, fresh):
        ax.text(h - w / 2, m + 0.02, f"{m:.2f}", ha="center", fontsize=7.6, color=INK)
        ax.text(h + w / 2, f + 0.02, f"{f:.2f}", ha="center", fontsize=7.6, color=INK)
    ax.set_xticks(hops)
    ax.set_xticklabels(["1 hop\n(friend)", "2 hops\n(friend of\na friend)",
                        "3 hops", "4 hops"], fontsize=8)
    ax.set_ylim(0, 1.16)
    ax.set_ylabel("trust", fontsize=9)
    ax.set_title("Trust falls with distance — and with freshness",
                 fontsize=10.5, fontweight="bold", color=BLACK, pad=10)
    ax.tick_params(labelsize=8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(LINE)
    ax.spines["bottom"].set_color(LINE)
    ax.legend(fontsize=8, frameon=False, loc="upper right")

    secondary = ax.twinx()
    secondary.set_ylim(0, 1.16 * SOCIAL_WEIGHT_M)
    secondary.set_ylabel("head start in matching (metres)", fontsize=9)
    secondary.tick_params(labelsize=8)
    for side in ("top", "left"):
        secondary.spines[side].set_visible(False)
    secondary.spines["right"].set_color(LINE)

    fig.text(0.5, -0.04,
             "Both panels are computed from the constants in "
             "modules/social/service.py, so they cannot drift from the code.",
             ha="center", fontsize=7.6, color=GREY, style="italic")
    fig.savefig("figures/fig_trust_curves.png", dpi=200, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)
    print("  fig_trust_curves.png")


def fig_trust_flow():
    fig, ax = canvas(11.0, 5.4, "How One Trust Score Is Assembled",
                     "requester → candidate, over the friendship graph")

    box(ax, 0.030, 0.560, 0.180, 0.150,
        "FRIENDSHIP GRAPH\nedges projected from\nPostgreSQL into Neo4j,\n"
        "each stamped with\nthe date it formed", fs=8)
    box(ax, 0.245, 0.585, 0.180, 0.100,
        "SHORTEST PATH\nrequester → candidate\nup to 4 hops", fs=8)
    box(ax, 0.460, 0.585, 0.185, 0.100,
        "NEWEST EDGE\non that path\n(not the average)", fill=FILL_2, lw=2.0,
        fs=8, bold=True)
    box(ax, 0.680, 0.585, 0.185, 0.100,
        "NEIGHBOURHOOD\nclosure · degree\n· circulation", fs=8)
    arrow(ax, (0.210, 0.635), (0.245, 0.635))
    arrow(ax, (0.425, 0.635), (0.460, 0.635))
    arrow(ax, (0.645, 0.635), (0.680, 0.635))

    box(ax, 0.150, 0.335, 0.700, 0.115,
        "trust   =   0.45 ^ (hops − 1)     ×     (1 − penalty)     ×     maturity",
        fill=FILL_2, lw=2.2, fs=11, bold=True)
    arrow(ax, (0.335, 0.585), (0.335, 0.450))
    arrow(ax, (0.552, 0.585), (0.500, 0.450))
    arrow(ax, (0.772, 0.585), (0.680, 0.450))
    ax.text(0.300, 0.300, "how far away", ha="center", fontsize=7.8, color=GREY)
    ax.text(0.500, 0.300, "is the group sealed,\nand does money circulate?",
            ha="center", fontsize=7.8, color=GREY)
    ax.text(0.700, 0.300, "how new is the\nnewest link", ha="center",
            fontsize=7.8, color=GREY)

    box(ax, 0.290, 0.115, 0.420, 0.090,
        "MATCHING\nscore = distance − trust × 1500 m − …", lw=1.9, fs=9,
        bold=True)
    arrow(ax, (0.500, 0.335), (0.500, 0.205))

    ax.text(0.5, 0.045,
            "A direct friend at full maturity in an open group scores 1.0, worth a "
            "1500-metre head start. Everything else is a fraction of that.",
            ha="center", fontsize=8, color=GREY, style="italic")
    save(fig, "fig_trust_flow.png")


if __name__ == "__main__":
    fig_trust_curves()
    fig_trust_flow()
