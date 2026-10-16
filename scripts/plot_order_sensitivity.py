#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
"""
Order sensitivity figure — global ground truth agreement per judge across the
three question orderings (original, reversed, permuted), from validity.json.

Reproduces the paper figure `judge_order_sensitivity` (4 judges) and extends it
to any judge in docs/benchmark/models.json that has results for the orderings.

Usage:
    python scripts/plot_order_sensitivity.py                  # all judges with 3 orderings
    python scripts/plot_order_sensitivity.py --models paper   # the 4 judges of the paper figure
    python scripts/plot_order_sensitivity.py --allow-partial  # also draw judges with < 3 orderings

Writes docs/ground_truth/figures/judge_order_sensitivity{_suffix}.{png,pdf}.
Requires matplotlib.
"""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from model_registry import select, label, color

VALIDITY = Path("docs/ground_truth/validity.json")
OUTPUT = Path("docs/ground_truth/figures")
ORDERS = ["original", "reversed", "permuted"]
ORDER_LABELS = {"original": "Original", "reversed": "Reversed", "permuted": "Permuted\n(q2→q4→q1→q3)"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", default="all")
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()

    v = json.loads(VALIDITY.read_text(encoding="utf-8"))
    judges = [j for j in select(args.models) if j in v["validity"]]
    rows = {}
    for j in judges:
        ys = [v["by_order"].get(o, {}).get(j, {}).get("global") for o in ORDERS]
        if all(y is not None for y in ys) or (args.allow_partial and any(y is not None for y in ys)):
            rows[j] = ys
    skipped = [j for j in judges if j not in rows]

    plt.rcParams.update({"font.family": "sans-serif", "font.size": 10, "axes.edgecolor": "#444444"})
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    x = list(range(len(ORDERS)))
    for j, ys in sorted(rows.items(), key=lambda kv: -(kv[1][0] or 0)):
        pts = [(xi, y * 100) for xi, y in zip(x, ys) if y is not None]
        ax.plot([p[0] for p in pts], [p[1] for p in pts], marker="o", linewidth=2, markersize=6,
                color=color(j), markeredgecolor="#444444", markeredgewidth=0.5, label=label(j))

    # Value labels: when two judges are within 1.5 pp at the same ordering, put the
    # lower one's label below its marker so they don't overlap.
    for xi in x:
        col = sorted(((ys[xi] * 100, j) for j, ys in rows.items() if ys[xi] is not None), reverse=True)
        prev = None
        for y, j in col:
            below = prev is not None and prev - y < 1.5
            ax.annotate(f"{y:.1f}", (xi, y), textcoords="offset points", xytext=(6, -10 if below else 2),
                        fontsize=7.5, color="#333333")
            prev = y

    ax.set_xticks(x)
    ax.set_xticklabels([ORDER_LABELS[o] for o in ORDERS])
    ax.set_xlim(-0.3, len(ORDERS) - 0.6)
    ax.set_ylabel("Global agreement with ground truth (%)")
    ax.set_title("Judge agreement by question ordering (49 cases)")
    ax.grid(axis="y", color="#dddddd", linestyle="--", linewidth=0.6)
    ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), frameon=False)
    fig.tight_layout()

    OUTPUT.mkdir(parents=True, exist_ok=True)
    suffix = "" if args.models == "paper" else f"_{args.models}"
    for ext in ("png", "pdf"):
        path = OUTPUT / f"judge_order_sensitivity{suffix}.{ext}"
        fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="white")
        print(f"  Saved: {path}")
    plt.close(fig)
    if skipped:
        print(f"  Skipped (fewer than 3 orderings; use --allow-partial): {', '.join(skipped)}")


if __name__ == "__main__":
    main()
