#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
"""
Generate paper figures from docs/benchmark/analysis/summary.json.
Output: docs/benchmark/figures/ (300 dpi, white background, colorblind-friendly palette).

Figures:
  1. delta_by_difficulty.png   — line chart delta specialized − baseline by difficulty
  2. size_vs_score.png         — scatter model size × mean score + regression line
  3. interjudge_stdev_by_difficulty.png  — boxplot inter-judge variance by difficulty
  4. judge_generator_matrix.png          — heatmap 4×4 judge × generator scores
"""

import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

SUMMARY = Path("docs/benchmark/analysis/summary.json")
OUTPUT = Path("docs/benchmark/figures")

# Okabe-Ito colorblind-safe palette
CB = {
    "orange":   "#E69F00",
    "sky":      "#56B4E9",
    "green":    "#009E73",
    "yellow":   "#F0E442",
    "blue":     "#0072B2",
    "vermil":   "#D55E00",
    "purple":   "#CC79A7",
    "black":    "#000000",
}

DIFF_ORDER   = ["easy", "medium", "adversarial", "hard"]
DIFF_LABELS  = {"easy": "Easy", "medium": "Medium", "adversarial": "Adversarial", "hard": "Hard"}
MODEL_LABELS = {
    "gemma3-4b":  "gemma3:4b (4B)",
    "mistral-7b": "mistral:7b (7B)",
    "phi4-mini":  "phi4-mini (3.8B)",
    "qwen3-1.7b": "qwen3:1.7b (1.7B)",
}
MODEL_COLORS = {
    "gemma3-4b":  CB["blue"],
    "mistral-7b": CB["vermil"],
    "phi4-mini":  CB["green"],
    "qwen3-1.7b": CB["orange"],
}

DPI = 300
FIGSIZE_SINGLE = (6, 4)
FIGSIZE_MATRIX = (6, 5)


def base_style():
    plt.rcParams.update({
        "figure.facecolor": "white",
        "axes.facecolor":   "white",
        "axes.edgecolor":   "#444444",
        "axes.labelcolor":  "#222222",
        "xtick.color":      "#444444",
        "ytick.color":      "#444444",
        "text.color":       "#222222",
        "grid.color":       "#dddddd",
        "grid.linestyle":   "--",
        "grid.linewidth":   0.6,
        "font.family":      "sans-serif",
        "font.size":        10,
        "axes.titlesize":   11,
        "axes.labelsize":   10,
        "legend.fontsize":  9,
    })


def savefig(fig, name: str):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / name
    fig.savefig(path, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  Saved: {path}")


# ── Figure 1 — Delta by difficulty ────────────────────────────────────────────

def fig1_delta_by_difficulty(data: dict):
    a1 = data["analysis_1_delta_specialized_vs_baseline"]["by_difficulty"]

    diffs  = [d for d in DIFF_ORDER if a1[d]["delta"] is not None]
    deltas = [a1[d]["delta"] for d in diffs]
    labels = [DIFF_LABELS[d] for d in diffs]

    fig, ax = plt.subplots(figsize=FIGSIZE_SINGLE)

    ax.plot(labels, deltas,
            marker="o", markersize=7, linewidth=2,
            color=CB["blue"], markerfacecolor=CB["orange"], markeredgecolor=CB["blue"],
            zorder=3)

    # Annotate values
    for x, (lbl, val) in enumerate(zip(labels, deltas)):
        offset = 0.004 if val >= 0 else -0.006
        ax.annotate(f"{val:+.3f}", (x, val + offset),
                    ha="center", va="bottom" if val >= 0 else "top",
                    fontsize=9, color=CB["blue"])

    # Zero reference
    ax.axhline(0, color="#888888", linewidth=1, linestyle=":")
    ax.fill_between(range(len(labels)), deltas, 0,
                    where=[v >= 0 for v in deltas],
                    alpha=0.12, color=CB["green"], label="Specialized > Baseline")
    ax.fill_between(range(len(labels)), deltas, 0,
                    where=[v < 0 for v in deltas],
                    alpha=0.12, color=CB["vermil"], label="Baseline > Specialized")

    ax.set_xlabel("Difficulty tier")
    ax.set_ylabel("Δ score  (specialized − baseline)")
    ax.set_title("Score gap: domain-specific profiles vs. quality baseline")
    ax.set_xlim(-0.4, len(labels) - 0.6)
    ax.grid(axis="y")
    ax.legend(loc="upper left", framealpha=0.9)

    fig.tight_layout()
    savefig(fig, "delta_by_difficulty.png")


# ── Figure 2 — Size vs score + regression ─────────────────────────────────────

def fig2_size_vs_score(data: dict):
    models_data = data["analysis_2_model_size_correlation"]["models"]
    pearson = data["analysis_2_model_size_correlation"]["pearson_size_vs_score"]

    models  = list(models_data.keys())
    sizes   = [models_data[m]["size_B"] for m in models]
    scores  = [models_data[m]["mean_score"] for m in models]
    stdevs  = [models_data[m]["stdev"] for m in models]

    fig, ax = plt.subplots(figsize=FIGSIZE_SINGLE)

    # Error bars (±1 std dev)
    for m, x, y, sd in zip(models, sizes, scores, stdevs):
        ax.errorbar(x, y, yerr=sd, fmt="none",
                    ecolor=MODEL_COLORS[m], elinewidth=1.2, capsize=4, alpha=0.5)

    # Scatter
    for m, x, y in zip(models, sizes, scores):
        ax.scatter(x, y, color=MODEL_COLORS[m], s=80, zorder=4,
                   label=MODEL_LABELS[m], edgecolors="white", linewidths=0.8)

    # Regression line
    n = len(sizes)
    mx, my = sum(sizes) / n, sum(scores) / n
    slope = sum((x - mx) * (y - my) for x, y in zip(sizes, scores)) / sum((x - mx) ** 2 for x in sizes)
    intercept = my - slope * mx
    x_line = [min(sizes) - 0.3, max(sizes) + 0.3]
    y_line = [slope * x + intercept for x in x_line]
    ax.plot(x_line, y_line, color="#888888", linewidth=1.2, linestyle="--",
            label=f"Linear fit  (r = {pearson:.2f})", zorder=2)

    ax.set_xlabel("Parameter count (B)")
    ax.set_ylabel("Mean composite score")
    ax.set_title("Generator model size vs. governance score")
    ax.legend(loc="lower right", framealpha=0.9)
    ax.grid(True)

    # Tight y-range
    y_min = min(scores) - max(stdevs) * 1.2
    y_max = max(scores) + max(stdevs) * 1.2
    ax.set_ylim(max(0, y_min), min(1.0, y_max))

    fig.tight_layout()
    savefig(fig, "size_vs_score.png")


# ── Figure 3 — Inter-judge stdev boxplot by difficulty ────────────────────────

def fig3_interjudge_stdev_by_difficulty(data: dict):
    all_prompts = data["analysis_3_interjudge_disagreement_by_prompt"]["all_prompts"]

    groups: dict[str, list[float]] = {d: [] for d in DIFF_ORDER}
    for pid, v in all_prompts.items():
        diff = v.get("difficulty")
        if diff in groups:
            sd = v.get("mean_interjudge_stdev")
            if sd is not None:
                groups[diff].append(sd)

    diffs_present = [d for d in DIFF_ORDER if groups[d]]
    box_data = [groups[d] for d in diffs_present]
    labels   = [DIFF_LABELS[d] for d in diffs_present]
    colors   = [CB["green"], CB["sky"], CB["orange"], CB["vermil"]]

    fig, ax = plt.subplots(figsize=FIGSIZE_SINGLE)

    bp = ax.boxplot(box_data, patch_artist=True, notch=False,
                    medianprops={"color": "white", "linewidth": 2},
                    whiskerprops={"linewidth": 1.2},
                    capprops={"linewidth": 1.2},
                    flierprops={"marker": "o", "markersize": 4,
                                "markeredgecolor": "#888888", "alpha": 0.6})

    for patch, c in zip(bp["boxes"], colors[:len(diffs_present)]):
        patch.set_facecolor(c)
        patch.set_alpha(0.75)

    ax.set_xticklabels(labels)
    ax.set_xlabel("Difficulty tier")
    ax.set_ylabel("Inter-judge σ  (std dev of composite scores)")
    ax.set_title("Judge disagreement by difficulty")
    ax.grid(axis="y")

    # Sample count annotation
    for i, (d, data_pts) in enumerate(zip(diffs_present, box_data), 1):
        ax.annotate(f"n={len(data_pts)}", (i, ax.get_ylim()[0]),
                    ha="center", va="bottom", fontsize=8, color="#666666")

    fig.tight_layout()
    savefig(fig, "interjudge_stdev_by_difficulty.png")


# ── Figure 4 — Judge × generator heatmap ──────────────────────────────────────

def fig4_judge_generator_matrix(data: dict):
    matrix = data["analysis_5_judge_generator_bias_matrix"]["matrix"]

    judges = sorted(matrix.keys())
    gens   = sorted(next(iter(matrix.values())).keys())

    grid = [[matrix[j][g]["mean_score"] for g in gens] for j in judges]

    fig, ax = plt.subplots(figsize=FIGSIZE_MATRIX)

    # Neutral blue: low score → light steel, high score → deep navy
    from matplotlib.colors import LinearSegmentedColormap, Normalize
    muted_cmap = LinearSegmentedColormap.from_list(
        "steel",
        ["#eef2f8", "#b8cce4", "#6e9dc0", "#2f6496", "#1a3a5c"],
    )

    all_vals = [matrix[j][g]["mean_score"] for j in judges for g in gens
                if matrix[j][g]["mean_score"] is not None]
    vmin, vmax = min(all_vals) - 0.002, max(all_vals) + 0.002
    norm = Normalize(vmin=vmin, vmax=vmax)

    im = ax.imshow(grid, cmap=muted_cmap, norm=norm, aspect="auto")

    # Labels
    ax.set_xticks(range(len(gens)))
    ax.set_xticklabels([MODEL_LABELS[g].split("(")[0].strip() for g in gens],
                       rotation=30, ha="right")
    ax.set_yticks(range(len(judges)))
    ax.set_yticklabels([MODEL_LABELS[j].split("(")[0].strip() for j in judges])

    ax.set_xlabel("Generator model")
    ax.set_ylabel("Judge model")
    ax.set_title("Mean composite score: judge × generator")

    def _text_color(val):
        """Black or white based on perceived luminance of the mapped cell color."""
        r, g, b, _ = muted_cmap(norm(val))
        lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
        return "#f5f8fb" if lum < 0.45 else "#1a1a2e"

    # Annotate cells
    for i, j_model in enumerate(judges):
        for k, g_model in enumerate(gens):
            val = matrix[j_model][g_model]["mean_score"]
            is_self = matrix[j_model][g_model]["is_self"]
            weight = "bold" if is_self else "normal"
            ax.text(k, i, f"{val:.3f}", ha="center", va="center",
                    fontsize=8.5, color=_text_color(val), fontweight=weight)
            if is_self:
                rect = plt.Rectangle((k - 0.5, i - 0.5), 1, 1,
                                     fill=False, edgecolor="#c0392b",
                                     linewidth=2.2, zorder=5)
                ax.add_patch(rect)

    cbar = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.04)
    cbar.set_label("Mean composite score", fontsize=9)

    # Legend for diagonal
    red_patch = mpatches.Patch(facecolor="none", edgecolor="#c0392b",
                                linewidth=2, label="Self-evaluation (judge = generator)")
    ax.legend(handles=[red_patch], loc="upper right",
              bbox_to_anchor=(1.0, -0.18), framealpha=0.9)

    fig.tight_layout()
    savefig(fig, "judge_generator_matrix.png")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    base_style()
    with open(SUMMARY, encoding="utf-8") as f:
        data = json.load(f)

    print("Generating figures …")
    fig1_delta_by_difficulty(data)
    fig2_size_vs_score(data)
    fig3_interjudge_stdev_by_difficulty(data)
    fig4_judge_generator_matrix(data)
    print("Done.")


if __name__ == "__main__":
    main()
