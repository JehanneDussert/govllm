"""
Generate three architecture figures for the govllm arXiv paper.
Output: docs/arxiv/figures/{architecture_microservices,evaluation_pipeline,lifecycle}.pdf
"""

import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "arxiv", "figures")
os.makedirs(OUT_DIR, exist_ok=True)

# ── Colour palette ────────────────────────────────────────────────────────────
C_PURPLE   = "#534AB7"
C_GREEN    = "#1D9E75"
C_GRAY     = "#888780"
C_LGRAY    = "#F1EFE8"
C_MGRAY    = "#D8D6CF"
C_WHITE    = "#FFFFFF"
C_LBLUE    = "#E8ECF8"
C_LGREEN   = "#E1F5EE"
C_LRED     = "#FCE8E8"
C_ORANGE   = "#E88030"
C_LORANGE  = "#FEF0E0"

FONT = "DejaVu Sans"
plt.rcParams.update({
    "font.family":    FONT,
    "font.size":      9,
    "axes.linewidth": 0.5,
})

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def box(ax, x, y, w, h, label, sublabel=None,
        fc=C_LBLUE, ec=C_PURPLE, lw=1.0, fontsize=9, bold=False,
        radius=0.015):
    """Draw a rounded rectangle with centred text."""
    rect = FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0,rounding_size={radius}",
        linewidth=lw, edgecolor=ec, facecolor=fc, zorder=2,
    )
    ax.add_patch(rect)
    weight = "bold" if bold else "normal"
    cy = y + h / 2 + (0.012 if sublabel else 0)
    ax.text(x + w / 2, cy, label,
            ha="center", va="center", fontsize=fontsize,
            fontweight=weight, color="#1A1A2E", zorder=3)
    if sublabel:
        ax.text(x + w / 2, y + h / 2 - 0.018, sublabel,
                ha="center", va="center", fontsize=fontsize - 1.5,
                color=C_GRAY, zorder=3)


def arrow(ax, x0, y0, x1, y1, label="", label_side="right",
          color=C_GRAY, lw=1.0, ls="-", fontsize=7.5,
          connectionstyle="arc3,rad=0"):
    """Draw an annotated arrow."""
    ax.annotate(
        "", xy=(x1, y1), xytext=(x0, y0),
        arrowprops=dict(
            arrowstyle="-|>", color=color, lw=lw,
            linestyle=ls,
            connectionstyle=connectionstyle,
        ),
        zorder=4,
    )
    if label:
        mx = (x0 + x1) / 2
        my = (y0 + y1) / 2
        if label_side == "right":
            ax.text(mx + 0.012, my, label,
                    ha="left", va="center", fontsize=fontsize,
                    color="#333333", zorder=5)
        elif label_side == "left":
            ax.text(mx - 0.012, my, label,
                    ha="right", va="center", fontsize=fontsize,
                    color="#333333", zorder=5)
        elif label_side == "above":
            ax.text(mx, my + 0.018, label,
                    ha="center", va="bottom", fontsize=fontsize,
                    color="#333333", zorder=5)
        elif label_side == "below":
            ax.text(mx, my - 0.018, label,
                    ha="center", va="top", fontsize=fontsize,
                    color="#333333", zorder=5)


def section_label(ax, x, y, text, fontsize=8.5):
    ax.text(x, y, text, ha="center", va="center",
            fontsize=fontsize, fontweight="bold",
            color=C_GRAY, zorder=3)


# ═════════════════════════════════════════════════════════════════════════════
# Figure 1 — Architecture microservice
# ═════════════════════════════════════════════════════════════════════════════

def fig_architecture():
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.axis("off")

    # ── Column headers ────────────────────────────────────────────────────
    col_x  = [0.04, 0.35, 0.68]   # left edges
    col_w  = 0.24
    hdr_y  = 0.90
    hdr_h  = 0.06

    headers = ["Frontend", "Services", "Infrastructure"]
    hdr_fc  = [C_LGRAY, C_LGRAY, C_LGRAY]
    hdr_ec  = [C_GRAY,  C_GRAY,  C_GRAY]
    for i, (hdr, fc, ec) in enumerate(zip(headers, hdr_fc, hdr_ec)):
        box(ax, col_x[i], hdr_y, col_w, hdr_h, hdr,
            fc=fc, ec=ec, bold=True, fontsize=10, radius=0.01)

    # ── Frontend block ─────────────────────────────────────────────────────
    fe_y = 0.16; fe_h = 0.68
    box(ax, col_x[0], fe_y, col_w, fe_h, "Vue 3 / TypeScript\nFrontend",
        fc=C_LBLUE, ec=C_PURPLE, bold=False, fontsize=9)

    # ── Services column ─────────────────────────────────────────────────
    svc = [
        ("llm-gateway :8001",    "chat · streaming · Redis pub", 0.67, 0.13, C_LBLUE, C_PURPLE),
        ("observability :8002",  "metrics · Langfuse traces",    0.48, 0.13, C_LGREEN, C_GREEN),
        ("evaluation :8003",     "judge · benchmark · arena\nlifecycle · ground truth",
                                                                  0.24, 0.18, C_LORANGE, C_ORANGE),
    ]
    for label, sub, sy, sh, fc, ec in svc:
        box(ax, col_x[1], sy, col_w, sh, label, sublabel=sub,
            fc=fc, ec=ec, fontsize=8.5, radius=0.01)

    # ── Infrastructure column ────────────────────────────────────────────
    infra = [
        ("Redis",       "pub/sub · config cache",   0.72, 0.10, C_LGRAY,   C_GRAY),
        ("Langfuse v2", "traces · scores",           0.58, 0.10, C_LGRAY,   C_GRAY),
        ("PostgreSQL",  "arena · lifecycle · GT",    0.44, 0.10, C_LGRAY,   C_GRAY),
        ("Ollama",      "phi4-mini · mistral · …",   0.28, 0.12, C_LGRAY,   C_GRAY),
    ]
    for label, sub, iy, ih, fc, ec in infra:
        box(ax, col_x[2], iy, col_w, ih, label, sublabel=sub,
            fc=fc, ec=ec, fontsize=8.5, radius=0.01)

    # ── Shared library bar ────────────────────────────────────────────────
    box(ax, 0.04, 0.04, col_x[1] + col_w - 0.04, 0.09,
        "shared/  —  Pydantic schemas · config · LangfuseClient",
        fc=C_MGRAY, ec=C_GRAY, fontsize=8, radius=0.008)

    # ── Arrows: Frontend → gateway ────────────────────────────────────────
    fe_right = col_x[0] + col_w
    gw_left  = col_x[1]
    gw_cy    = 0.67 + 0.13 / 2   # centre y of llm-gateway
    obs_cy   = 0.48 + 0.13 / 2
    ev_cy    = 0.24 + 0.18 / 2

    # POST /chat
    arrow(ax, fe_right, gw_cy + 0.025,
              gw_left,  gw_cy + 0.025,
          label="POST /chat", label_side="above",
          color=C_PURPLE, lw=1.2, fontsize=7.5)

    # POST /eval/score
    arrow(ax, fe_right, ev_cy,
              gw_left,  ev_cy,
          label="POST /eval/score", label_side="above",
          color=C_ORANGE, lw=1.2, fontsize=7.5)

    # GET traces / metrics
    arrow(ax, fe_right, obs_cy,
              gw_left,  obs_cy,
          label="GET /traces · /metrics", label_side="above",
          color=C_GREEN, lw=1.0, fontsize=7.5)

    # ── Arrows: gateway → infrastructure ─────────────────────────────────
    svc_right = col_x[1] + col_w
    redis_left = col_x[2]
    redis_cy   = 0.72 + 0.10 / 2
    langf_cy   = 0.58 + 0.10 / 2
    pg_cy      = 0.44 + 0.10 / 2
    ollama_cy  = 0.28 + 0.12 / 2

    arrow(ax, svc_right, gw_cy,
              redis_left, redis_cy,
          label="pub LLMEvent", label_side="right",
          color=C_PURPLE, lw=1.0, fontsize=7.5)

    arrow(ax, svc_right, obs_cy,
              redis_left, langf_cy,
          label="read traces", label_side="right",
          color=C_GREEN, lw=1.0, fontsize=7.5)

    arrow(ax, svc_right, ev_cy + 0.04,
              redis_left, pg_cy,
          label="write sessions / GT", label_side="right",
          color=C_ORANGE, lw=1.0, fontsize=7.5)

    arrow(ax, svc_right, ev_cy - 0.01,
              redis_left, ollama_cy,
          label="LiteLLM → inference", label_side="right",
          color=C_ORANGE, lw=1.0, fontsize=7.5)

    # push score: evaluation → Langfuse
    arrow(ax, svc_right, ev_cy + 0.055,
              redis_left, langf_cy,
          label="push score", label_side="right",
          color=C_ORANGE, lw=0.8, ls="--", fontsize=7.5)

    ax.set_title("Figure 1 — govllm microservice architecture",
                 fontsize=10, pad=6, color="#1A1A2E")

    path = os.path.join(OUT_DIR, "architecture_microservices.pdf")
    fig.savefig(path, dpi=300, bbox_inches="tight", format="pdf")
    plt.close(fig)
    print(f"  OK  {path}")


# ═════════════════════════════════════════════════════════════════════════════
# Figure 2 — Evaluation pipeline
# ═════════════════════════════════════════════════════════════════════════════

def fig_pipeline():
    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.axis("off")

    # Horizontal divider
    ax.axhline(0.50, color=C_MGRAY, lw=0.8, ls="--", zorder=1)

    # Path labels
    ax.text(0.01, 0.75, "①  Chat path",
            ha="left", va="center", fontsize=9, fontweight="bold",
            color=C_PURPLE)
    ax.text(0.01, 0.26, "②  Evaluation path",
            ha="left", va="center", fontsize=9, fontweight="bold",
            color=C_ORANGE)

    # ── Chat path (top) ───────────────────────────────────────────────────
    BW = 0.14; BH = 0.13

    # Frontend
    box(ax, 0.03, 0.62, BW, BH, "Frontend",
        fc=C_LBLUE, ec=C_PURPLE, fontsize=8.5, bold=True)

    # llm-gateway
    box(ax, 0.26, 0.62, BW, BH, "llm-gateway\n:8001",
        fc=C_LBLUE, ec=C_PURPLE, fontsize=8.5)

    # Ollama
    box(ax, 0.49, 0.62, BW, BH, "Ollama\n(LiteLLM)",
        fc=C_LGRAY, ec=C_GRAY, fontsize=8.5)

    # Redis (publish)
    box(ax, 0.72, 0.70, 0.13, 0.10, "Redis\npub/sub",
        fc=C_LGRAY, ec=C_GRAY, fontsize=8)

    # SSE streaming response back to Frontend
    arrow(ax, 0.26 + BW, 0.68 + 0.03, 0.26, 0.68 + 0.03,
          label="streaming SSE response", label_side="above",
          color=C_PURPLE, lw=1.1, fontsize=7.5)

    arrow(ax, 0.03 + BW, 0.685, 0.26, 0.685,
          label="POST /chat", label_side="above",
          color=C_PURPLE, lw=1.2, fontsize=7.5)

    arrow(ax, 0.26 + BW, 0.685, 0.49, 0.685,
          label="LiteLLM call", label_side="above",
          color=C_PURPLE, lw=1.1, fontsize=7.5)

    arrow(ax, 0.49 + BW, 0.73, 0.72, 0.73,
          label="pub LLMEvent", label_side="above",
          color=C_GRAY, lw=0.9, fontsize=7.5)

    # governance config dashed from Redis to gateway (left of gateway)
    ax.annotate(
        "", xy=(0.26 + 0.01, 0.62), xytext=(0.72, 0.71),
        arrowprops=dict(
            arrowstyle="-|>", color=C_GRAY, lw=0.8,
            linestyle="--",
            connectionstyle="arc3,rad=0.35",
        ), zorder=4,
    )
    ax.text(0.50, 0.58, "governance config cache", ha="center",
            va="top", fontsize=7, color=C_GRAY, style="italic")

    # ── Evaluation path (bottom) ──────────────────────────────────────────
    BH2 = 0.13

    # Frontend (reused visual — just label POST /eval/score)
    box(ax, 0.03, 0.15, BW, BH2, "Frontend",
        fc=C_LBLUE, ec=C_PURPLE, fontsize=8.5, bold=True)

    # evaluation service
    box(ax, 0.26, 0.15, BW, BH2, "evaluation\n:8003",
        fc=C_LORANGE, ec=C_ORANGE, fontsize=8.5)

    # Judge (Ollama)
    box(ax, 0.49, 0.15, BW, BH2, "Judge model\n(Ollama)",
        fc=C_LGRAY, ec=C_GRAY, fontsize=8.5)

    # Right-side outputs: Redis TTL, Langfuse, Chat+Matrix
    box(ax, 0.72, 0.34, 0.13, 0.10, "Redis (7-day TTL)\nhot cache",
        fc=C_LGRAY, ec=C_GRAY, fontsize=7.5)
    box(ax, 0.72, 0.20, 0.13, 0.10, "Langfuse v2\ntrace scores",
        fc=C_LGRAY, ec=C_GRAY, fontsize=7.5)
    box(ax, 0.72, 0.06, 0.13, 0.10, "Chat & Matrix\nviews",
        fc=C_LBLUE, ec=C_PURPLE, fontsize=7.5)

    arrow(ax, 0.03 + BW, 0.215, 0.26, 0.215,
          label="POST /eval/score", label_side="above",
          color=C_ORANGE, lw=1.2, fontsize=7.5)

    arrow(ax, 0.26 + BW, 0.215, 0.49, 0.215,
          label="judge prompt", label_side="above",
          color=C_ORANGE, lw=1.1, fontsize=7.5)

    arrow(ax, 0.49 + BW, 0.215, 0.72, 0.39,
          label="write scores", label_side="right",
          color=C_ORANGE, lw=1.0, fontsize=7.5)

    arrow(ax, 0.72 + 0.065, 0.34, 0.72 + 0.065, 0.30,
          label="push score", label_side="right",
          color=C_ORANGE, lw=0.9, fontsize=7.5)

    arrow(ax, 0.72 + 0.065, 0.20, 0.72 + 0.065, 0.16,
          label="surface", label_side="right",
          color=C_ORANGE, lw=0.9, fontsize=7.5)

    # 202 response back to Frontend
    arrow(ax, 0.26, 0.17, 0.03 + BW, 0.17,
          label="202 Accepted + trace_id", label_side="below",
          color=C_GRAY, lw=0.9, fontsize=7.5)

    ax.set_title("Figure 2 — govllm evaluation pipeline",
                 fontsize=10, pad=6, color="#1A1A2E")

    path = os.path.join(OUT_DIR, "evaluation_pipeline.pdf")
    fig.savefig(path, dpi=300, bbox_inches="tight", format="pdf")
    plt.close(fig)
    print(f"  OK  {path}")


# ═════════════════════════════════════════════════════════════════════════════
# Figure 3 — Model lifecycle
# ═════════════════════════════════════════════════════════════════════════════

def fig_lifecycle():
    fig, ax = plt.subplots(figsize=(11, 4.8))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.axis("off")

    # Zone positions
    zones = [
        ("TEST",        C_LGRAY,   C_GRAY,   0.04),
        ("VALIDATION",  C_LORANGE, C_ORANGE, 0.27),
        ("PRODUCTION",  C_LGREEN,  C_GREEN,  0.50),
        ("QUARANTINE",  C_LRED,    "#C0392B", 0.73),
    ]
    BW = 0.20; BH = 0.18; BY = 0.55

    for label, fc, ec, bx in zones:
        box(ax, bx, BY, BW, BH, label,
            fc=fc, ec=ec, bold=True, fontsize=10, lw=1.4, radius=0.012)

    # Sub-annotations below each zone
    ann = [
        "synthetic benchmark\n(SAS run)",
        "human gate\n(human validates)",
        "continuous monitoring\n(drift watcher)",
        "suspended\npending re-eval",
    ]
    for (_, fc, ec, bx), txt in zip(zones, ann):
        box(ax, bx + 0.01, BY - 0.20, BW - 0.02, 0.16, txt,
            fc=C_LGRAY, ec=C_MGRAY, fontsize=7.5, lw=0.6, radius=0.008)
        # Thin connector line
        ax.plot([bx + BW / 2, bx + BW / 2],
                [BY, BY - 0.04],
                color=C_MGRAY, lw=0.7, zorder=1)

    # Forward arrows between zones
    transitions = [
        (0, 1, "SAS passes"),
        (1, 2, "human validates"),
        (2, 3, "drift detected"),
    ]
    for i, j, lbl in transitions:
        bx_i = zones[i][3]; bx_j = zones[j][3]
        x0 = bx_i + BW + 0.003; x1 = bx_j - 0.003
        cy = BY + BH / 2
        arrow(ax, x0, cy, x1, cy,
              label=lbl, label_side="above",
              color=C_GRAY, lw=1.2, fontsize=7.5)

    # Return arc: QUARANTINE → TEST (re-qualification)
    # Draw arc below the annotation boxes
    from matplotlib.patches import FancyArrowPatch
    arc = FancyArrowPatch(
        posA=(zones[3][3] + BW / 2, BY - 0.20),
        posB=(zones[0][3] + BW / 2, BY - 0.20),
        arrowstyle="-|>",
        connectionstyle="arc3,rad=0.45",
        color=C_GRAY, lw=1.0, linestyle="--",
        zorder=5,
    )
    ax.add_patch(arc)
    ax.text(0.50, 0.08, "SAS passes → requalification",
            ha="center", va="center", fontsize=7.5,
            color=C_GRAY, style="italic")

    # Legend boxes at bottom
    leg_y = 0.03; leg_h = 0.065; leg_w = 0.36
    box(ax, 0.04, leg_y, leg_w, leg_h,
        "drift watcher runs every 15 min",
        fc=C_LGRAY, ec=C_MGRAY, fontsize=7.5, lw=0.6)
    box(ax, 0.60, leg_y, leg_w, leg_h,
        "operator can trigger Validate / Quarantine manually",
        fc=C_LGRAY, ec=C_MGRAY, fontsize=7.5, lw=0.6)

    ax.set_title("Figure 3 — govllm model lifecycle qualification cycle",
                 fontsize=10, pad=6, color="#1A1A2E")

    path = os.path.join(OUT_DIR, "lifecycle.pdf")
    fig.savefig(path, dpi=300, bbox_inches="tight", format="pdf")
    plt.close(fig)
    print(f"  OK  {path}")


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Generating arXiv figures ...")
    fig_architecture()
    fig_pipeline()
    fig_lifecycle()
    print("Done.")
