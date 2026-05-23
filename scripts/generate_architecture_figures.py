"""Generate architecture figures for paper1.tex (Figures 1, 2, 3)."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from pathlib import Path

OUT = Path(__file__).parent.parent / "docs" / "arxiv" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

# ── Palette (matches LaTeX govllm colours) ─────────────────────────────────
PURPLE_F = '#EEEDFE'; PURPLE_E = '#534AB7'
GREEN_F  = '#E1F5EE'; GREEN_E  = '#1D9E75'
GRAY_F   = '#F1EFE8'; GRAY_E   = '#888780'
RED_F    = '#FCEAEA'; RED_E    = '#D85A30'
ORANGE_F = '#FEF3E2'; ORANGE_E = '#D97706'
TEXT_DARK = '#1a1a1a'


# ── Helpers ────────────────────────────────────────────────────────────────
def box(ax, cx, cy, w, h, label, fc, ec, fs=8.5, lw=1.4):
    p = FancyBboxPatch((cx - w/2, cy - h/2), w, h,
                       boxstyle='round,pad=0.04', fc=fc, ec=ec, lw=lw, zorder=2)
    ax.add_patch(p)
    ax.text(cx, cy, label, ha='center', va='center', fontsize=fs,
            color=TEXT_DARK, zorder=3, linespacing=1.5)


def arrow(ax, x1, y1, x2, y2, label='', color=GRAY_E, dashed=False,
          lpos=0.5, ldy=0.15, ldx=0.0):
    ls = (0, (4, 3)) if dashed else 'solid'
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->', color=color, lw=1.2,
                                linestyle=ls),
                zorder=1)
    if label:
        lx = x1 + (x2 - x1) * lpos + ldx
        ly = y1 + (y2 - y1) * lpos + ldy
        ax.text(lx, ly, label, ha='center', va='center', fontsize=6.5,
                color='#555550')


def elbow_arrow(ax, pts, label='', color=GRAY_E, dashed=False,
                lpos=0.5, ldy=0.15):
    """Draw a multi-segment (elbow) arrow through a list of (x,y) points."""
    ls = (0, (4, 3)) if dashed else 'solid'
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    ax.plot(xs[:-1], ys[:-1], color=color, lw=1.2, linestyle=ls, zorder=1)
    ax.annotate('', xy=pts[-1], xytext=pts[-2],
                arrowprops=dict(arrowstyle='->', color=color, lw=1.2,
                                linestyle=ls),
                zorder=1)
    if label:
        idx = max(1, int(len(pts) * lpos))
        lx = (pts[idx-1][0] + pts[idx][0]) / 2 + ldy
        ly = (pts[idx-1][1] + pts[idx][1]) / 2
        ax.text(lx, ly, label, ha='left', va='center', fontsize=6.5,
                color='#555550')


# ══════════════════════════════════════════════════════════════════════════
# Figure 1 — Microservice architecture
# ══════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(10, 6.5))
ax.set_xlim(0, 10); ax.set_ylim(0, 6.5)
ax.axis('off')

# Frontend
box(ax, 5, 6.0, 9.6, 0.7, 'Frontend  ·  Vue 3  ·  TypeScript', GREEN_F, GREEN_E, fs=9)

# Services (y=4.6)
box(ax, 1.4, 4.5, 2.6, 0.75, 'llm-gateway\n:8001', PURPLE_F, PURPLE_E)
box(ax, 5.0, 4.5, 2.6, 0.75, 'observability\n:8002', PURPLE_F, PURPLE_E)
box(ax, 8.6, 4.5, 2.6, 0.75, 'evaluation\n:8003', PURPLE_F, PURPLE_E)

# Infrastructure (y=3.0)
box(ax, 1.4, 3.0, 2.4, 0.7, 'Redis', GRAY_F, GRAY_E)
box(ax, 5.0, 3.0, 2.4, 0.7, 'Langfuse', GRAY_F, GRAY_E)
box(ax, 8.6, 3.0, 2.4, 0.7, 'PostgreSQL', GRAY_F, GRAY_E)

# Ollama (y=1.55)
box(ax, 5.0, 1.55, 9.6, 0.7,
    'Ollama   ·   phi4-mini   ·   mistral:7b   ·   gemma3:4b   ·   qwen3:1.7b',
    GRAY_F, GRAY_E, fs=8.5)

# Shared (y=0.6)
box(ax, 5.0, 0.6, 9.6, 0.65,
    'shared  —  Pydantic schemas  ·  config  ·  Langfuse wrapper  (uv workspace)',
    GREEN_F, GREEN_E, fs=7.8)

# ── Arrows ─────────────────────────────────────────────────────────────────
# Frontend → llm-gateway
elbow_arrow(ax, [(2.8, 5.65), (1.4, 5.65), (1.4, 4.87)],
            label='POST /chat', ldy=0.12)
# Frontend → observability
arrow(ax, 5.0, 5.65, 5.0, 4.87, label='GET /metrics · /traces', ldy=0.16)
# Frontend → evaluation
elbow_arrow(ax, [(7.2, 5.65), (8.6, 5.65), (8.6, 4.87)],
            label='POST /eval/score', ldy=0.12)

# llm-gateway → Redis
arrow(ax, 1.4, 4.12, 1.4, 3.35, label='pub LLMEvent', ldy=0.14)
# observability → Langfuse
arrow(ax, 5.0, 4.12, 5.0, 3.35, label='read traces', ldy=0.14)
# evaluation → PostgreSQL
arrow(ax, 8.6, 4.12, 8.6, 3.35, label='write', ldy=0.14)
# evaluation → Langfuse (push score, elbow from evaluation box)
elbow_arrow(ax, [(8.6, 4.12), (8.6, 3.65), (6.2, 3.65), (6.2, 3.35)],
            label='push score', ldy=0.15)
# Redis → observability (config, dashed horizontal)
arrow(ax, 2.6, 3.0, 3.8, 3.0, label='config', lpos=0.5, ldy=0.16, dashed=True)

# llm-gateway → Ollama (inference)
elbow_arrow(ax, [(1.4, 2.65), (1.4, 1.9)], label='  inference', ldy=0.0)
# evaluation → Ollama (judge)
elbow_arrow(ax, [(8.6, 2.65), (8.6, 1.9)], label='  judge', ldy=0.0)

fig.tight_layout(pad=0.2)
fig.savefig(OUT / 'architecture_microservices.png', dpi=220, bbox_inches='tight')
plt.close(fig)
print("OK Figure 1: architecture_microservices.png")


# ══════════════════════════════════════════════════════════════════════════
# Figure 2 — Evaluation pipeline
# ══════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(10, 5.5))
ax.set_xlim(0, 10); ax.set_ylim(0, 5.5)
ax.axis('off')

# ── Chat path (top row, y=4.5) ─────────────────────────────────────────────
ax.text(0.2, 5.1, '① Chat path', fontsize=8.5, color=PURPLE_E, fontweight='bold')

box(ax, 1.0, 4.5, 1.5, 0.65, 'Frontend', GREEN_F, GREEN_E)
box(ax, 3.2, 4.5, 2.1, 0.65, 'llm-gateway\n:8001', PURPLE_F, PURPLE_E)
box(ax, 6.0, 4.5, 1.8, 0.65, 'Ollama\n(LLM)', GRAY_F, GRAY_E)
box(ax, 8.8, 4.5, 1.8, 0.65, 'response\n→ SSE', GREEN_F, GREEN_E)

arrow(ax, 1.75, 4.5, 2.15, 4.5, label='POST /chat', ldy=0.2)
arrow(ax, 4.25, 4.5, 5.1, 4.5, label='inference', ldy=0.2)
arrow(ax, 6.9, 4.5, 7.9, 4.5, label='stream', ldy=0.2)
arrow(ax, 9.7, 4.5, 9.7, 3.2, label='triggers ②', ldy=0.0, ldx=0.3)

# llm-gateway → Redis (governance context)
elbow_arrow(ax, [(3.2, 4.17), (3.2, 3.5)],
            label='  pub LLMEvent', ldy=0.0)
box(ax, 3.2, 3.0, 1.8, 0.65, 'Redis', GRAY_F, GRAY_E)
ax.text(3.2, 2.55, 'governance config cache', ha='center', va='top',
        fontsize=6.5, color='#666660', style='italic')

# ── Eval path (bottom row, y=1.8) ──────────────────────────────────────────
ax.text(0.2, 2.6, '② Evaluation path', fontsize=8.5, color=PURPLE_E, fontweight='bold')

box(ax, 1.0, 1.8, 1.5, 0.65, 'Frontend', GREEN_F, GREEN_E)
box(ax, 3.2, 1.8, 2.2, 0.65, 'evaluation\n:8003', PURPLE_F, PURPLE_E)
box(ax, 6.0, 1.8, 1.8, 0.65, 'Ollama\n(judge)', GRAY_F, GRAY_E)

arrow(ax, 1.75, 1.8, 2.1, 1.8, label='POST /eval/score', ldy=0.22)
arrow(ax, 4.3, 1.8, 5.1, 1.8, label='judge call', ldy=0.2)
arrow(ax, 6.9, 1.8, 7.9, 1.8)

# Outputs from evaluation
box(ax, 8.5, 2.55, 1.8, 0.55, 'Redis\n(TTL 7 d)', GRAY_F, GRAY_E, fs=8)
box(ax, 8.5, 1.8,  1.8, 0.55, 'Langfuse\n(trace score)', GRAY_F, GRAY_E, fs=8)
box(ax, 8.5, 1.05, 1.8, 0.55, 'Chat + Matrix\n(display)', GREEN_F, GREEN_E, fs=8)
ax.annotate('', xy=(7.6, 2.55), xytext=(7.6, 1.45),
            arrowprops=dict(arrowstyle='->', color=GRAY_E, lw=1.2), zorder=1)
ax.annotate('', xy=(7.6, 1.05), xytext=(7.6, 1.45),
            arrowprops=dict(arrowstyle='->', color=GRAY_E, lw=1.2), zorder=1)
ax.plot([7.6, 7.6], [1.45, 2.55], color=GRAY_E, lw=1.2, zorder=1)
arrow(ax, 7.6, 2.55, 7.6, 1.05)

# Connect Redis (governance config) → evaluation (reads active profile)
elbow_arrow(ax, [(2.3, 3.0), (2.3, 1.8)],
            label='  reads active profile', ldy=0.0, dashed=True)

# separator
ax.axhline(3.1, xmin=0.02, xmax=0.98, color=GRAY_E, lw=0.6, ls='--', alpha=0.5)

fig.tight_layout(pad=0.2)
fig.savefig(OUT / 'evaluation_pipeline.png', dpi=220, bbox_inches='tight')
plt.close(fig)
print("OK Figure 2: evaluation_pipeline.png")


# ══════════════════════════════════════════════════════════════════════════
# Figure 3 — Lifecycle qualification cycle
# ══════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(10, 4.0))
ax.set_xlim(0, 10); ax.set_ylim(0, 4.0)
ax.axis('off')

# ── 4 zone boxes ───────────────────────────────────────────────────────────
Z = {
    'test':       (1.4,  2.0, GRAY_F,   GRAY_E,   'TEST'),
    'validation': (3.8,  2.0, ORANGE_F, ORANGE_E, 'VALIDATION'),
    'production': (6.2,  2.0, GREEN_F,  GREEN_E,  'PRODUCTION'),
    'quarantine': (8.6,  2.0, RED_F,    RED_E,    'QUARANTINE'),
}

for name, (cx, cy, fc, ec, label) in Z.items():
    box(ax, cx, cy, 2.0, 0.9, label, fc, ec, fs=9.5, lw=1.6)
    # sub-label
    sublabels = {
        'test':       'synthetic\nbenchmark',
        'validation': 'human\nreview',
        'production': 'continuous\nmonitoring',
        'quarantine': 'suspended\npending re-eval',
    }
    ax.text(cx, cy - 0.75, sublabels[name], ha='center', va='top',
            fontsize=7, color='#666660', style='italic', linespacing=1.4)

# ── Forward arrows (top path) ──────────────────────────────────────────────
fwd = [
    (2.4, 2.0, 2.8, 2.0, 'SAS passes'),
    (4.8, 2.0, 5.2, 2.0, 'human validates'),
    (7.2, 2.0, 7.6, 2.0, 'drift detected'),
]
for x1, y1, x2, y2, lbl in fwd:
    arrow(ax, x1, y1, x2, y2, label=lbl, ldy=0.26)

# ── Return arrow: QUARANTINE → TEST (bottom arc) ───────────────────────────
elbow_arrow(ax, [
    (8.6, 1.55),
    (8.6, 0.75),
    (1.4, 0.75),
    (1.4, 1.55),
], label='  SAS passes → requalification', ldy=0.0, lpos=0.5)

# Auto-quarantine note
ax.text(5.0, 0.35, 'drift watcher runs every 15 min in production  ·  operator can trigger Validate / Quarantine manually',
        ha='center', va='center', fontsize=6.5, color='#666660', style='italic')

# AI Act reference
ax.text(5.0, 3.7,
        'Governed model lifecycle  —  implements AI Act art. 9 (continuous risk management) and art. 14 (human oversight)',
        ha='center', va='center', fontsize=7.2, color=GRAY_E)

fig.tight_layout(pad=0.2)
fig.savefig(OUT / 'lifecycle.png', dpi=220, bbox_inches='tight')
plt.close(fig)
print("OK Figure 3: lifecycle.png")
print("\nAll figures saved to", OUT)
