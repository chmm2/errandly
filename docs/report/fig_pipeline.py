"""Fig. 8 — how a collusion flag is actually raised, end to end.

    python docs/report/fig_pipeline.py

Kept in its own module because it is the one figure that spans the whole
system: it is the answer to "what does the offer log actually DO", and it has
to show four tiers at once — every errand, the monthly sweep, the single row a
flag really is, and what reads that row afterwards.

Two things the earlier draft got wrong and this one fixes:

  * The top tier is a BRANCH, not a chain. An errand goes down the 95% path or
    the 5% path, never both. Drawing it as a sequence implied every errand was
    somehow explored.

  * The offer log feeds step 3 — the check on whether our own router already
    explains the group's behaviour. It is not read by the language model, and
    an arrow pointing at the model misstates where the evidence goes.
"""

from figures import (
    BLACK, FILL_2, FILL_3, GREY, INK, arrow, band, box, canvas, save,
)


def fig_pipeline():
    fig, ax = canvas(12.4, 8.8, "How a Collusion Flag Is Actually Raised",
                     "the offer log and the 5% socially-blind rounds supply the "
                     "evidence; a human supplies the verdict")

    band(ax, 0.762, 0.148, "EVERY ERRAND")
    band(ax, 0.500, 0.240, "MONTHLY SWEEP")
    band(ax, 0.300, 0.178, "THE FLAG")
    band(ax, 0.120, 0.158, "CONSEQUENCES")

    # ── tier 1: every errand — a branch, not a chain
    box(ax, 0.098, 0.808, 0.160, 0.068, "Errand posted", bold=True, fs=8.4)
    box(ax, 0.308, 0.842, 0.225, 0.050,
        "95 %   normal   ·   friends +1500 m", fs=8)
    box(ax, 0.308, 0.780, 0.225, 0.050,
        "5 %   exploring   ·   no friend boost", fill=FILL_2, lw=2.0, fs=8,
        bold=True)
    box(ax, 0.585, 0.795, 0.200, 0.084,
        "OFFER  LOG\nwho was offered it,\nevery score, who took it",
        fill=FILL_2, lw=2.0, fs=7.8, bold=True)
    arrow(ax, (0.258, 0.850), (0.308, 0.867), rad=-0.10)
    arrow(ax, (0.258, 0.834), (0.308, 0.805), rad=0.10)
    arrow(ax, (0.533, 0.867), (0.585, 0.850), rad=0.10)
    arrow(ax, (0.533, 0.805), (0.585, 0.822), rad=-0.10)
    ax.text(0.420, 0.772, "one path or the other, never both", ha="center",
            va="top", fontsize=6.8, color=GREY, style="italic")

    # ── tier 2: the monthly sweep
    box(ax, 0.070, 0.632, 0.195, 0.074,
        "1.  Money circle?\nA pays B pays C pays A", fs=8)
    box(ax, 0.298, 0.632, 0.195, 0.074,
        "2.  Floors met?\n≥ 3 people · ≥ 2 laps\n· real money", fs=8)
    box(ax, 0.525, 0.616, 0.235, 0.104,
        "3.  Did OUR ROUTER\nalready explain it?\n\n"
        "expected vs observed\nin-group share  →  z",
        fill=FILL_2, lw=2.2, fs=8, bold=True)
    box(ax, 0.792, 0.632, 0.190, 0.074,
        "4.  LLM: do these\nerrands read as real?\nadvisory only", fs=8)
    arrow(ax, (0.265, 0.669), (0.298, 0.669))
    arrow(ax, (0.493, 0.669), (0.525, 0.669))
    arrow(ax, (0.760, 0.669), (0.792, 0.669))

    # The log is read HERE, and nowhere else.
    arrow(ax, (0.680, 0.795), (0.655, 0.720), ls="dashed")
    ax.text(0.694, 0.752, "read here", ha="left", va="center", fontsize=7,
            color=GREY, style="italic")

    box(ax, 0.070, 0.508, 0.330, 0.054,
        "honest friend group  →  cleared, no flag raised", fs=8)
    arrow(ax, (0.525, 0.640), (0.400, 0.548), rad=0.14)
    ax.text(0.398, 0.600, "z < 3   the router explains it", ha="right",
            va="center", fontsize=7.6, color=INK)

    # ── tier 3: the flag itself
    box(ax, 0.290, 0.334, 0.420, 0.102,
        "ONE  ROW  SAVED\nperson · rule = COLLUSION_RING · severity 3\n"
        "status = OPEN · members = [A, B, C]",
        fill=FILL_2, lw=2.2, fs=8.2, bold=True)
    arrow(ax, (0.565, 0.616), (0.525, 0.436))
    ax.text(0.578, 0.520, "z ≥ 3   unexplained", ha="left", va="center",
            fontsize=7.6, color=INK)

    # ── tier 4: what reads the row
    box(ax, 0.098, 0.146, 0.262, 0.096,
        "They stop being offered\neach other's errands\n→ the circle is broken",
        lw=1.9, fs=8)
    box(ax, 0.392, 0.146, 0.222, 0.096,
        "Pushed down the queue\nfor everyone else\n(+1200 m)", fs=8)
    box(ax, 0.646, 0.146, 0.262, 0.096,
        "Appears in the admin\nconsole for a human\nto review", fs=8)
    arrow(ax, (0.360, 0.334), (0.229, 0.242), rad=0.12)
    arrow(ax, (0.500, 0.334), (0.503, 0.242))
    arrow(ax, (0.640, 0.334), (0.777, 0.242), rad=-0.12)
    ax.text(0.5, 0.124,
            "all three simply READ that one row — and only while its status is "
            "OPEN or UPHELD",
            ha="center", va="top", fontsize=7.6, color=GREY, style="italic")

    box(ax, 0.270, 0.020, 0.460, 0.064,
        "ADMIN'S  VERDICT\ndismiss → DISMISSED, all three stop at once    ·    "
        "uphold → UPHELD, they continue",
        fill=FILL_3, lw=1.9, fs=8, bold=True)
    arrow(ax, (0.777, 0.146), (0.735, 0.092), rad=0.14)

    save(fig, "fig_pipeline.png")


if __name__ == "__main__":
    fig_pipeline()
