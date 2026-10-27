"""Hand-drawn diagrams for the review deck.

One spec, two outputs:

  * ``figures_sketch/<name>.png``   - rendered here, embedded straight into the
    deck. Wobbled strokes and a handwriting face, so it reads as drawn rather
    than plotted.
  * ``excalidraw/<name>.excalidraw`` - the same scene as a real Excalidraw
    file. Open it at excalidraw.com to move a box or reword a label, export a
    PNG, and drop it over the rendered one.

The two are generated from the same coordinates, so a tweak in Excalidraw is a
tweak to the diagram people already saw, not a redraw.

Why not matplotlib's usual output: the earlier figures were geometrically
perfect, evenly spaced and hairline-ruled, which is exactly what makes a
diagram look machine-made. `path.sketch` perturbs every stroke, so parallel
lines stop being parallel and corners stop being square.
"""

from __future__ import annotations

import json
import pathlib
import random

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

HERE = pathlib.Path(__file__).parent
PNG_DIR = HERE / "figures_sketch"
EXC_DIR = HERE / "excalidraw"
PNG_DIR.mkdir(parents=True, exist_ok=True)
EXC_DIR.mkdir(parents=True, exist_ok=True)

# Excalidraw's own pastels. Restrained on purpose - fills carry meaning here
# (shaded == our contribution), they are not decoration.
WHITE = "#ffffff"
CREAM = "#fff3bf"      # our work
VIOLET = "#d0bfff"     # the novel pieces
TEAL = "#c3fae8"       # storage
BLUE = "#a5d8ff"       # inputs
GREEN = "#b2f2bb"      # good outcome
RED = "#ffc9c9"        # blocked / bad outcome
GREY_T = "#757575"
INK = "#1e1e1e"

FONT = "Ink Free"

_rand = random.Random(7)


def _seed() -> int:
    return _rand.randint(1, 2**31 - 1)


# ───────────────────────────────────────────────── excalidraw serialisation

def _base(kind: str, x: float, y: float, w: float, h: float, **kw) -> dict:
    el = {
        "id": kw.pop("id"),
        "type": kind,
        "x": x, "y": y, "width": w, "height": h,
        "angle": 0,
        "strokeColor": kw.pop("strokeColor", INK),
        "backgroundColor": kw.pop("backgroundColor", "transparent"),
        "fillStyle": "solid",
        "strokeWidth": kw.pop("strokeWidth", 2),
        "strokeStyle": kw.pop("strokeStyle", "solid"),
        "roughness": 1,
        "opacity": kw.pop("opacity", 100),
        "groupIds": [],
        "frameId": None,
        "roundness": kw.pop("roundness", None),
        "seed": _seed(),
        "version": 1,
        "versionNonce": _seed(),
        "isDeleted": False,
        "boundElements": kw.pop("boundElements", None),
        "updated": 1,
        "link": None,
        "locked": False,
    }
    el.update(kw)
    return el


def _text_el(tid: str, x: float, y: float, text: str, fs: float,
             color: str, container: str | None = None) -> dict:
    lines = text.split("\n")
    w = max(len(ln) for ln in lines) * fs * 0.55
    h = len(lines) * fs * 1.25
    el = _base("text", x, y, w, h, id=tid, strokeColor=color)
    el.update({
        "text": text,
        "originalText": text,
        "fontSize": fs,
        "fontFamily": 1,           # 1 = Virgil, Excalidraw's hand-drawn face
        "textAlign": "center" if container else "left",
        "verticalAlign": "middle" if container else "top",
        "containerId": container,
        "lineHeight": 1.25,
        "baseline": fs,
    })
    return el


class Scene:
    """A diagram, buildable once and emittable twice."""

    def __init__(self, name: str, width: int, height: int,
                 title: str | None = None, subtitle: str | None = None):
        self.name = name
        self.w = width
        self.h = height
        self.elements: list[dict] = []
        self._n = 0
        # Drawn onto the matplotlib canvas separately so the handwriting face
        # can be sized independently of the body text.
        self._mpl: list[tuple] = []
        if title:
            self.text(width / 2, 26, title, fs=30, anchor="center")
        if subtitle:
            self.text(width / 2, 66, subtitle, fs=17, color=GREY_T,
                      anchor="center")

    def _id(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}{self._n}"

    # ─────────────────────────────────────────────────────────── primitives

    def box(self, x, y, w, h, text="", fill=WHITE, fs=18, rounded=True,
            stroke=INK, lw=2, opacity=100):
        bid = self._id("b")
        el = _base("rectangle", x, y, w, h, id=bid,
                   backgroundColor=fill, strokeColor=stroke, strokeWidth=lw,
                   opacity=opacity,
                   roundness={"type": 3} if rounded else None)
        if text:
            tid = self._id("t")
            el["boundElements"] = [{"type": "text", "id": tid}]
            self.elements.append(el)
            self.elements.append(
                _text_el(tid, x, y, text, fs, INK, container=bid))
        else:
            self.elements.append(el)
        self._mpl.append(("box", x, y, w, h, text, fill, fs, rounded, stroke,
                          lw, opacity))
        return bid

    def ellipse(self, x, y, w, h, text="", fill=WHITE, fs=18, stroke=INK, lw=2):
        eid = self._id("e")
        el = _base("ellipse", x, y, w, h, id=eid,
                   backgroundColor=fill, strokeColor=stroke, strokeWidth=lw)
        if text:
            tid = self._id("t")
            el["boundElements"] = [{"type": "text", "id": tid}]
            self.elements.append(el)
            self.elements.append(
                _text_el(tid, x, y, text, fs, INK, container=eid))
        else:
            self.elements.append(el)
        self._mpl.append(("ellipse", x, y, w, h, text, fill, fs, stroke, lw))
        return eid

    def arrow(self, x1, y1, x2, y2, head=True, dashed=False, stroke=INK, lw=2):
        aid = self._id("a")
        el = _base("arrow", x1, y1, x2 - x1, y2 - y1, id=aid,
                   strokeColor=stroke, strokeWidth=lw,
                   strokeStyle="dashed" if dashed else "solid")
        el.update({
            "points": [[0, 0], [x2 - x1, y2 - y1]],
            "startArrowhead": None,
            "endArrowhead": "arrow" if head else None,
            "startBinding": None,
            "endBinding": None,
            "lastCommittedPoint": None,
            "elbowed": False,
        })
        self.elements.append(el)
        self._mpl.append(("arrow", x1, y1, x2, y2, head, dashed, stroke, lw))
        return aid

    def line(self, x1, y1, x2, y2, stroke=INK, lw=2, dashed=False):
        return self.arrow(x1, y1, x2, y2, head=False, dashed=dashed,
                          stroke=stroke, lw=lw)

    def text(self, x, y, text, fs=17, color=INK, anchor="left"):
        tid = self._id("x")
        lines = text.split("\n")
        est_w = max(len(ln) for ln in lines) * fs * 0.55
        ex = x - est_w / 2 if anchor == "center" else x
        self.elements.append(_text_el(tid, ex, y, text, fs, color))
        self._mpl.append(("text", x, y, text, fs, color, anchor))
        return tid

    # ───────────────────────────────────────────────────────────── emitters

    def _write_excalidraw(self) -> pathlib.Path:
        doc = {
            "type": "excalidraw",
            "version": 2,
            "source": "errandly-review-deck",
            "elements": self.elements,
            "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"},
            "files": {},
        }
        path = EXC_DIR / f"{self.name}.excalidraw"
        path.write_text(json.dumps(doc, indent=1), encoding="utf-8")
        return path

    def _render_png(self, dpi_width=2100) -> pathlib.Path:
        # The wobble. Applied globally rather than per-artist so every stroke
        # in the figure is perturbed by the same hand.
        plt.rcParams["path.sketch"] = (1.6, 110, 14)
        plt.rcParams["font.family"] = FONT

        fig_w = 12.0
        fig_h = fig_w * self.h / self.w
        fig, ax = plt.subplots(figsize=(fig_w, fig_h))
        ax.set_xlim(0, self.w)
        ax.set_ylim(self.h, 0)          # y grows downward, as in Excalidraw
        ax.axis("off")
        fig.subplots_adjust(0, 0, 1, 1)

        # Points are in scene units; convert a font size in scene units to
        # matplotlib points using the figure's own scale.
        scale = fig_w * dpi_width / 12.0 / self.w
        px_per_pt = dpi_width / (fig_w * 72)

        def fs_pt(fs):
            return fs * scale / px_per_pt

        for item in self._mpl:
            kind = item[0]
            if kind == "box":
                _, x, y, w, h, text, fill, fs, rounded, stroke, lw, op = item
                pad = min(12, h / 4)
                ax.add_patch(FancyBboxPatch(
                    (x + pad, y + pad), w - 2 * pad, h - 2 * pad,
                    boxstyle=f"round,pad={pad}" if rounded
                             else f"square,pad={pad}",
                    linewidth=lw, edgecolor=stroke,
                    facecolor="none" if fill == "transparent" else fill,
                    alpha=op / 100, mutation_aspect=1))
                if text:
                    ax.text(x + w / 2, y + h / 2, text, ha="center",
                            va="center", fontsize=fs_pt(fs), color=INK,
                            linespacing=1.3, zorder=5)
            elif kind == "ellipse":
                _, x, y, w, h, text, fill, fs, stroke, lw = item
                from matplotlib.patches import Ellipse
                ax.add_patch(Ellipse((x + w / 2, y + h / 2), w, h,
                                     linewidth=lw, edgecolor=stroke,
                                     facecolor="none" if fill == "transparent"
                                     else fill))
                if text:
                    ax.text(x + w / 2, y + h / 2, text, ha="center",
                            va="center", fontsize=fs_pt(fs), color=INK,
                            zorder=5)
            elif kind == "arrow":
                _, x1, y1, x2, y2, head, dashed, stroke, lw = item
                ax.add_patch(FancyArrowPatch(
                    (x1, y1), (x2, y2),
                    arrowstyle="-|>" if head else "-",
                    mutation_scale=18, linewidth=lw, color=stroke,
                    linestyle="--" if dashed else "-",
                    shrinkA=0, shrinkB=0, zorder=4))
            elif kind == "text":
                _, x, y, text, fs, color, anchor = item
                ha = {"left": "left", "center": "center"}[anchor]
                ax.text(x, y, text, ha=ha, va="top", fontsize=fs_pt(fs),
                        color=color, linespacing=1.3, zorder=6)

        path = PNG_DIR / f"{self.name}.png"
        fig.savefig(path, dpi=dpi_width / fig_w, facecolor="white")
        plt.close(fig)
        plt.rcParams["path.sketch"] = None
        return path

    def save(self):
        p1 = self._render_png()
        p2 = self._write_excalidraw()
        print(f"  {p1.name:22s} + {p2.name}")
