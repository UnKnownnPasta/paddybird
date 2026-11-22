"""Draw the diagrams used in the study notebooks (white background so they read in light and dark themes)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from pathlib import Path

OUT = Path(__file__).parent
INK, ORANGE, GREY = "#1f1f1e", "#eb6834", "#6b6a63"


def box(ax, x, y, w, h, text, fc, fs=10, bold=False):
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0.02,rounding_size=0.12",
                                fc=fc, ec=INK, lw=1.2))
    ax.text(x, y, text, ha="center", va="center", fontsize=fs, color=INK, fontweight="bold" if bold else "normal")


def arrow(ax, x0, y0, x1, y1):
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0), arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.4))


def s2_pipeline():
    fig, ax = plt.subplots(figsize=(8.6, 7.6), dpi=170)
    fig.patch.set_facecolor("white"); ax.set_xlim(0, 10); ax.set_ylim(0, 10.4); ax.axis("off")
    box(ax, 5, 9.7, 3.6, 0.8, "Radar chip (VV, VH in dB)", "#e8f0fb", bold=True)
    box(ax, 1.75, 7.6, 3.0, 1.1, "Baseline:\nOtsu on VV\n(hard 0 or 1)", "#f1f0ea", fs=9.5)
    box(ax, 5.0, 7.6, 2.9, 1.1, "Predictor 1:\nrule stack\n(soft score p1)", "#e3f6ee", fs=9.5)
    box(ax, 8.25, 7.6, 2.9, 1.1, "Predictor 2:\nboosted pixel model\n(probability p2)", "#e3f6ee", fs=9.5)
    for x in (1.75, 5.0, 8.25):
        arrow(ax, 5 + (x - 5) * 0.35, 9.3, x, 8.2)
    ax.text(1.75, 6.85, "the thing to beat,\nscored at the end", ha="center", va="top", fontsize=9, color=ORANGE, style="italic")
    arrow(ax, 5.0, 7.0, 4.4, 6.05); arrow(ax, 8.25, 7.0, 5.6, 6.05)
    box(ax, 5, 5.55, 5.6, 0.95, "Fusion: logistic regression, per land cover\n(fitted on validation only)", "#e8f0fb")
    box(ax, 5, 4.0, 6.0, 0.95, "Calibration: identity / temperature / isotonic\n(chosen on validation, identity won)", "#e8f0fb")
    arrow(ax, 5, 5.07, 5, 4.48)
    box(ax, 5, 2.55, 5.0, 0.85, "x paddy mask (WorldCover cropland proxy)", "#fdeee5")
    arrow(ax, 5, 3.52, 5, 2.98)
    box(ax, 5, 1.1, 5.6, 0.95, "p_flooded_paddy\n(+ duration maps, semi-synthetic)", "#fbe6d9", bold=True)
    arrow(ax, 5, 2.12, 5, 1.58)
    ax.text(5, 0.25, "Layer 2: radar chip to calibrated probability of flooded paddy", ha="center", fontsize=9, color=GREY)
    fig.savefig(OUT / "s2_pipeline.png", bbox_inches="tight", facecolor="white"); plt.close(fig)


if __name__ == "__main__":
    s2_pipeline()
    print("wrote", [p.name for p in OUT.glob("*.png")])
