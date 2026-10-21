"""Draw the result figures for the paper from the experiment JSON files.

Black and white only: series are told apart by marker shape and line style,
never by shade alone, so the figures survive a photocopier. Error bars and
bands are 95% confidence intervals of the mean across seeds (t-based, as
computed by backend/evals/paper/common.ci95).

Run from the repository root:
    python docs/paper/ieee/figures/make_figures.py
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
RESULTS = HERE.parents[3] / "paper-artifacts" / "results"
PNG_DIR = HERE.parents[3] / "paper-artifacts" / "figures"
COL = 3.45  # IEEE single-column width, inches
DEPLOYED_EXPLORE = 0.05

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
    "mathtext.fontset": "stix",
    "font.size": 8, "axes.labelsize": 8, "axes.titlesize": 8,
    "legend.fontsize": 7, "xtick.labelsize": 7, "ytick.labelsize": 7,
    "axes.linewidth": 0.6, "lines.linewidth": 1.0, "lines.markersize": 4,
    "axes.edgecolor": "black", "axes.labelcolor": "black",
    "xtick.color": "black", "ytick.color": "black",
    "axes.grid": True, "grid.color": "0.88", "grid.linewidth": 0.4, "grid.linestyle": "-",
    "axes.axisbelow": True,
    "axes.spines.top": False, "axes.spines.right": False,
    "legend.frameon": False,
    "pdf.fonttype": 42, "ps.fonttype": 42,
    "savefig.bbox": "tight", "savefig.pad_inches": 0.02,
})

# One look per detector, used in every figure that shows it.
DET = {
    "find_rings": dict(linestyle="--", marker="o", markerfacecolor="white",
                       label="ring search alone"),
    "find_rings_policy": dict(linestyle=":", marker="^", markerfacecolor="white",
                              label="+ test, router scores"),
    "find_rings_policy_fitted": dict(linestyle="-", marker="s",
                                     label="+ test, fitted model (deployed)"),
}


def load(name):
    path = RESULTS / f"{name}.json"
    return json.loads(path.read_text())["results"] if path.exists() else None


def load_main():
    out = {}
    for path in sorted(RESULTS.glob("exp2_main*.json")):
        out.update(json.loads(path.read_text())["results"])
    return out


def load_sweeps():
    out = {}
    for part in ("explore", "weight_favours", "intensity_adaptive"):
        d = load(f"exp2_sweeps_{part}")
        if d:
            out.update(d)
    return out


def save(fig, name):
    """The PDF goes into the paper; a PNG copy goes into paper-artifacts so the
    figure can be seen on GitHub without building the manuscript."""
    fig.savefig(HERE / f"{name}.pdf")
    PNG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(PNG_DIR / f"{name}.png", dpi=200)
    plt.close(fig)
    print("wrote", name)


def _series(rows, key, det, metric):
    xs = [r[key] for r in rows]
    ms = [r["summary"][det][metric]["mean"] for r in rows]
    cs = [r["summary"][det][metric]["ci"] for r in rows]
    return xs, ms, cs


def _plot_dets(ax, rows, key, metric, dets=tuple(DET)):
    for det in dets:
        x, m, c = _series(rows, key, det, metric)
        ax.errorbar(x, m, yerr=c, color="black", capsize=2, **DET[det])


# --------------------------------------------------------------- policy z
def fig_z():
    d = load_main()
    if not d:
        return
    regimes = [("routine", "Routine"), ("busy", "Busy"), ("favours", "Favours"),
               ("coordinated", "Coordinated"), ("hard", "Hard")]
    regimes = [r for r in regimes if r[0] in d]
    fig, axes = plt.subplots(2, 1, figsize=(COL, 3.9), sharex=True)
    for ax, field, title in ((axes[0], "z", "(a) router's own scores (original test)"),
                             (axes[1], "z_fitted", "(b) fitted acceptance model (deployed)")):
        rng = random.Random(3)
        top = 0.0
        for x, (key, _label) in enumerate(regimes):
            zs_b, zs_r = [], []
            for t in d[key]["trials"]:
                for g in t["group_z"]:
                    z = g.get(field)
                    if z is None:
                        continue
                    (zs_r if g["kind"] == "ring" else zs_b).append(min(z, 40.0))
            top = max([top] + zs_b + zs_r)
            ax.scatter([x - 0.17 + rng.uniform(-0.09, 0.09) for _ in zs_b], zs_b, s=5,
                       facecolors="none", edgecolors="black", linewidths=0.4,
                       label="honest group" if x == 0 else None)
            ax.scatter([x + 0.17 + rng.uniform(-0.06, 0.06) for _ in zs_r], zs_r, s=7,
                       marker="s", color="black", linewidths=0,
                       label="collusion ring" if x == 0 else None)
            nb = sum(z >= 3 for z in zs_b)
            nr = sum(z >= 3 for z in zs_r)
            ax.text(x, 41.5, f"{nb}/{len(zs_b)}\n{nr}/{len(zs_r)}", ha="center",
                    va="bottom", fontsize=5.5, linespacing=1.0)
        ax.axhline(3.0, color="black", linewidth=0.8)
        ax.set_ylim(-12, 48)
        ax.set_ylabel("policy excess $z$")
        ax.set_title(title, loc="left", pad=14)
    axes[1].set_xticks(range(len(regimes)), [r[1] for r in regimes])
    axes[1].set_xlim(-0.55, len(regimes) - 0.45)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, fontsize=6.5,
               bbox_to_anchor=(0.5, -0.01), handletextpad=0.3)
    fig.tight_layout(h_pad=0.6, rect=(0, 0.04, 1, 1))
    save(fig, "fig_z")


# --------------------------------------------------------------- sweeps
def fig_explore():
    d = load_sweeps()
    if not d.get("explore"):
        return
    coord = [r for r in d["explore"] if r["base"] == "coordinated"]
    busy = [r for r in d["explore"] if r["base"] == "busy"]
    fig, (a, b) = plt.subplots(1, 2, figsize=(COL, 1.9))
    if coord:
        _plot_dets(a, coord, "explore_rate", "recall")
    a.set_xlabel("exploration rate $\\varepsilon$")
    a.set_ylabel("recall")
    a.set_ylim(-0.03, 1.08)
    a.set_title("(a) coordinated rings", loc="left")
    if busy:
        _plot_dets(b, busy, "explore_rate", "fp")
    b.set_xlabel("exploration rate $\\varepsilon$")
    b.set_ylabel("false positives per trial")
    b.set_title("(b) busy campus", loc="left")
    b.set_ylim(bottom=0)
    for ax in (a, b):
        ax.axvline(DEPLOYED_EXPLORE, color="0.4", linewidth=0.6, linestyle=(0, (1, 1.5)))
    a.text(DEPLOYED_EXPLORE + 0.008, 0.62, "deployed\n5%", fontsize=5.5, color="0.3",
           va="center", ha="left")
    handles, labels = a.get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, fontsize=6,
               bbox_to_anchor=(0.5, -0.06), columnspacing=0.8, handlelength=2.0)
    fig.tight_layout(w_pad=1.0, rect=(0, 0.08, 1, 1))
    save(fig, "fig_explore")


def fig_sweeps():
    d = load_sweeps()
    if not d.get("favours") or not d.get("intensity"):
        return
    fig, (a, b) = plt.subplots(1, 2, figsize=(COL, 1.9))
    _plot_dets(a, d["favours"], "favours_per_member", "fp")
    a.set_xlabel("honest favours per member")
    a.set_ylabel("honest students flagged")
    a.set_title("(a) favour-trading groups", loc="left")
    a.set_ylim(bottom=0)
    x, m, c = _series(d["intensity"], "farm_per_member", "find_rings", "recall")
    b.errorbar(x, m, yerr=c, color="black", capsize=2, linestyle="--", marker="o",
               markerfacecolor="white", label="routine rings, ring search")
    if d.get("adaptive"):
        x, m, c = _series(d["adaptive"], "farm_per_member", "find_rings_policy_fitted",
                          "recall")
        b.errorbar(x, m, yerr=c, color="black", capsize=2, marker="s",
                   label="coordinated rings, deployed")
    b.set_xlabel("farmed errands per member")
    b.set_ylabel("recall")
    b.set_title("(b) farming intensity", loc="left")
    b.set_ylim(-0.03, 1.08)
    b.legend(loc="upper left", fontsize=5.5, handlelength=1.8, borderaxespad=0.1)
    b.set_ylim(-0.03, 1.35)
    b.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    handles, labels = a.get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, fontsize=6,
               bbox_to_anchor=(0.5, -0.06), columnspacing=0.8, handlelength=2.0)
    fig.tight_layout(w_pad=1.0, rect=(0, 0.08, 1, 1))
    save(fig, "fig_sweeps")


# --------------------------------------------------------------- reference prices
def _band(trajs):
    import statistics
    n = len(trajs)
    weeks = range(len(trajs[0]))
    mean = [statistics.fmean(t[w] for t in trajs) for w in weeks]
    lo = [sorted(t[w] for t in trajs)[int(0.05 * (n - 1))] for w in weeks]
    hi = [sorted(t[w] for t in trajs)[int(round(0.95 * (n - 1)))] for w in weeks]
    return list(weeks), mean, lo, hi


def fig_reference():
    d = load("exp3_reference")
    if not d:
        return
    styles = [
        ("mean_unflagged", dict(linestyle=":", marker="^", markerfacecolor="white"),
         "mean of claims"),
        ("robust", dict(linestyle="--", marker="o", markerfacecolor="white"),
         "one vote per runner"),
        ("robust_band", dict(linestyle=(0, (5, 1.5)), marker="v", markerfacecolor="white"),
         "one vote per runner + band"),
        ("production", dict(linestyle="-", marker="s"), "deployed"),
    ]
    fig, ax = plt.subplots(figsize=(COL, 2.2))
    for name, st, label in styles:
        tr = next((t for t in d["trajectories"] if t["estimator"] == name
                   and t["strategy"] == "line" and abs(t["attack_frac"] - 0.6) < 1e-9), None)
        if tr is None:
            continue
        weeks, mean, lo, hi = _band(tr["trajectories"])
        ax.fill_between(weeks, lo, hi, color="0.82", alpha=0.6, linewidth=0, zorder=1)
        ax.plot(weeks, mean, color="black", markevery=2, label=label, zorder=3, **st)
    ax.axhline(30, color="0.4", linewidth=0.5, linestyle=(0, (2, 2)))
    ax.axhline(15, color="0.4", linewidth=0.5, linestyle=(0, (2, 2)))
    ax.text(16.1, 30, "band", fontsize=5.5, color="0.3", va="center")
    ax.set_xlabel("week")
    ax.set_ylabel("reference price (Rs)")
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 115)
    ax.legend(loc="upper left", fontsize=6.3)
    save(fig, "fig_reference")


# --------------------------------------------------------------- farming
def fig_farming():
    d = load("exp5_farming")
    if not d:
        return
    honest = d["honest_20_strangers_all_five"]["production"]
    fig, (a, b) = plt.subplots(1, 2, figsize=(COL, 2.0), sharey=True)
    rows = d["penalised_3_friends"]
    xs = list(range(len(rows)))
    a.plot(xs, [r["raw_mean"] for r in rows], color="black", linestyle=":", marker="^",
           markerfacecolor="white", label="plain average")
    a.plot(xs, [r["per_rating"] for r in rows], color="black", linestyle="--", marker="o",
           markerfacecolor="white", label="weight per rating")
    a.plot(xs, [r["production"] for r in rows], color="black", marker="s",
           label="one vote per rater")
    a.set_xticks(xs, [str(r["farmed"]) for r in rows])
    a.set_xlabel("ratings from 3 friends\n(tick spacing not to scale)")
    a.set_ylabel("score used for ranking")
    a.set_title("(a) penalised runner", loc="left")
    br = d["breadth"]
    xb = list(range(len(br)))
    b.plot(xb, [r["production"] for r in br], color="black", marker="s")
    b.set_xticks(xb, [str(r["farmed"]) for r in br])
    b.set_xlabel("friends, one rating each\n(tick spacing not to scale)")
    b.set_title("(b) breadth attack", loc="left")
    for ax in (a, b):
        ax.axhline(honest, color="0.45", linewidth=0.6)
        ax.tick_params(axis="x", labelsize=5.5)
    b.text(0.0, honest + 0.06, "honest runner,\n20 strangers", fontsize=5.5, color="0.3",
           va="bottom")
    a.set_ylim(2.5, 5.3)
    handles, labels = a.get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, fontsize=6,
               bbox_to_anchor=(0.5, -0.04), columnspacing=0.8, handlelength=2.0)
    fig.tight_layout(w_pad=0.6, rect=(0, 0.07, 1, 1))
    save(fig, "fig_farming")


# --------------------------------------------------------------- escrow
def fig_escrow():
    d = load("exp7_escrow")
    if not d or "frontier" not in d:
        return
    fig, axes = plt.subplots(1, 2, figsize=(COL, 1.95), sharey=True)
    for ax, drift, title in ((axes[0], "assumed", "(a) assumed prices"),
                             (axes[1], "heavy", "(b) dearer counters")):
        for base, st, label in (("non_mrp", dict(marker="s"), "on loose-priced items"),
                                ("whole", dict(linestyle="--", marker="o",
                                               markerfacecolor="white"), "on whole order")):
            rows = [r for r in d["frontier"] if r["base"] == base and r["pct"] > 0
                    and r.get("drift", "assumed") == drift]
            if not rows:
                continue
            ax.errorbar([r["mean_unneeded_lock"]["mean"] for r in rows],
                        [100 * r["freeze_rate"]["mean"] for r in rows],
                        yerr=[100 * r["freeze_rate"]["ci"] for r in rows],
                        color="black", capsize=1.5, label=label, **st)
        prod = next((r for r in d["frontier"] if r["base"] == "non_mrp"
                     and abs(r["pct"] - 0.16) < 1e-9 and r.get("drift", "assumed") == drift),
                    None)
        if prod:
            ax.annotate("16%", (prod["mean_unneeded_lock"]["mean"],
                                100 * prod["freeze_rate"]["mean"]),
                        xytext=(10, 8), textcoords="offset points", fontsize=6,
                        arrowprops=dict(arrowstyle="-", linewidth=0.5))
        ax.set_title(title, loc="left")
        ax.set_xlabel("locked, not needed (Rs/order)")
    axes[0].set_ylabel("payouts frozen (%)")
    axes[0].set_ylim(bottom=-0.5)
    axes[0].legend(loc="upper right", fontsize=5.5, title="headroom", title_fontsize=5.5)
    fig.tight_layout(w_pad=0.6)
    save(fig, "fig_escrow")


if __name__ == "__main__":
    for f in (fig_z, fig_explore, fig_sweeps, fig_reference, fig_farming, fig_escrow):
        f()
