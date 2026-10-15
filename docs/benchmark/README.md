# Benchmark — govllm

Fixed-output multi-model × multi-judge evaluation. 48 prompts across 6 use cases and 4 governance profiles. 768 scored entries (48 × 4 generators × 4 judges).

## Structure

```
docs/benchmark/
├── prompts.json          # 48 prompts (6 use cases × 8 prompts each)
├── references/           # model answers — one file per generator model
│   ├── phi4-mini.json
│   ├── gemma3-4b.json
│   ├── mistral-7b.json
│   └── qwen3-1.7b.json
├── results/              # judge scores — one file per (generator, judge) pair
│   ├── phi4-mini_gemma3-4b.json
│   ├── phi4-mini_mistral-7b.json
│   └── ...               # 16 files total (4 generators × 4 judges)
└── README.md
```

## Pipeline

Two phases, both incremental and resumable:

```bash
# Full pipeline (generate answers + score with all judges)
python scripts/run_full_benchmark.py

# Phase 1 only — generate model answers
python scripts/run_full_benchmark.py --only-generate --timeout 600

# Phase 2 only — score with all judges
python scripts/run_full_benchmark.py --only-evaluate --timeout 120

# Target specific models or judges
python scripts/run_full_benchmark.py --models ollama/phi4-mini --judges ollama/gemma3:4b
```

**Phase 1** generates model answers for each prompt via `POST /chat` and saves them to `references/{model}.json`. Idempotent — skips prompts already answered.

**Phase 2** submits each `(prompt, answer)` pair to every judge model via `POST /eval/score`, polls `GET /eval/result/{trace_id}`, and saves scores to `results/{model}_{judge}.json`. Incremental via `.partial.json` — safe to interrupt and resume.

**Important:** the script switches use case first, then governance profile. The use-case endpoint auto-applies a default profile — the explicit profile switch must come after to override it.

## Prompts

48 prompts across 6 use cases and 4 difficulty levels (2 each):

| Use case | Config ID | Governance profile | Easy | Medium | Adversarial | Hard | Total |
|---|---|---|---|---|---|---|---|
| general | general | quality_baseline | 2 | 2 | 2 | 2 | 8 |
| summarization | summary | quality_baseline | 2 | 2 | 2 | 2 | 8 |
| translation | translation | accessibility | 2 | 2 | 2 | 2 | 8 |
| code | code | security | 2 | 2 | 2 | 2 | 8 |
| administrative_writing | legal | data_protection | 2 | 2 | 2 | 2 | 8 |
| analysis | analysis | ai_act_compliance | 2 | 2 | 2 | 2 | 8 |

## File schemas

### `references/{model}.json`

```json
{
  "model": "ollama/phi4-mini",
  "n": 48,
  "updated_at": "2026-05-19T...",
  "entries": [
    {
      "id": "gen_easy_01",
      "use_case": "general",
      "governance_profile": "quality_baseline",
      "prompt": "...",
      "answer": "..."
    }
  ]
}
```

### `results/{model}_{judge}.json`

```json
{
  "run_at": "2026-05-19T...",
  "model": "ollama/phi4-mini",
  "judge_model": "ollama/gemma3:4b",
  "timeout": 120,
  "fixed_outputs": true,
  "total": 48,
  "results": [
    {
      "id": "gen_easy_01",
      "use_case": "general",
      "governance_profile": "quality_baseline",
      "score": 0.91,
      "status": "OK",
      "trace_id": "...",
      "prompt": "...",
      "answer": "...",
      "eval": {
        "composite_score": 0.91,
        "criteria_scores": [
          { "criterion_id": "relevance", "score": 0.95, "flag": false, "reason": "..." }
        ]
      }
    }
  ]
}
```

Status values: `OK` · `TIMEOUT` · `EVAL_TRIGGER_ERROR` · `CONFIG_ERROR`

## Analyses

Completed. Results in `docs/benchmark/analysis/`:

| File | Content |
|---|---|
| `summary.json` | Full analysis output — all findings below |
| `judge_reliability.json` | Level 1 (agreement vs ground truth) + Level 2 (reason consistency by domain/difficulty) + Level 3 classification |

**Key findings:**

| # | Finding | Result |
|---|---|---|
| 1 | Domain-specific profiles vs quality-baseline profile | Hard prompts: +5.7 pp (95% CI [+0.4, +10.9], 12 prompts from different use cases — indicative); easy prompts: −0.6 pp |
| 2 | Model size vs score correlation | Pearson r = −0.39 (n=4, indicative) — smallest model (qwen3:1.7b, 1.7B) ranks 2nd |
| 3 | Inter-judge disagreement | Top discriminator: `ana_hard_01` (σ=0.256); hard/adversarial prompts concentrate disagreement |
| 4 | Intra-judge variance by domain | phi4-mini: extreme variance on `analysis` (σ=0.29); `translation` most stable (σ≤0.023) |
| 5 | Family bias matrix | No significant self-preference among these 4 models (formal test, see *8-model extension* below — not true of every model) |
| 6 | Self vs cross evaluation | gemma3:4b self=0.849 vs cross=0.955 (bias=−0.106); phi4-mini bias=−0.024 |

**Judge reliability classification** (from `judge_reliability.json`):

| Judge | Agreement (GT) | Consistency | Classification |
|---|---|---|---|
| phi4-mini | 69.1% | 91.6% | CALIBRATED_BUT_STRICT |
| qwen3:1.7b | 60.2% | 92.6% | CALIBRATED_BUT_STRICT |
| gemma3:4b | 66.3% | 69.1% | UNRELIABLE |
| mistral:7b | 51.5% | 92.7% | UNRELIABLE |

Scripts: `scripts/analyze_benchmark.py` → `summary.json`; `scripts/judge_reliability.py` → `judge_reliability.json`.

### 8-model extension (provisional)

The analysis scripts read their model list from [`models.json`](models.json) (slug, Ollama id, family, nominal and reported size, color) through `scripts/model_registry.py`. Nothing is hardcoded any more. `--models paper` reproduces the arXiv v1 outputs above unchanged; the default `--models all` writes `*_all.json` / `*_all.png` alongside them:

```bash
python scripts/analyze_benchmark.py                                # -> analysis/summary_all.json
python scripts/analyze_benchmark.py --models paper                 # -> analysis/summary.json (paper, unchanged)
python scripts/generate_figures.py --summary docs/benchmark/analysis/summary_all.json   # -> figures/*_all.png
python scripts/judge_reliability.py --models all                   # -> analysis/judge_reliability_all.json
```

**Formal self-preference** (`analysis_7_self_preference_formal`, `scripts/self_preference.py`). The SPR of §5.2 is computed per prompt (the judge ranks its own output first; ties share the credit) and compared with how often judges from *other families* rank that same output first. A score-level difference-in-differences controls for both output quality and judge severity. 95% bootstrap CIs are taken over the 48 prompts, with Holm correction across judges. The legacy `self_preference_rate.spr` (model-level, no test) is kept only for reproducibility.

On the 4 paper models, no judge shows significant self-preference (all estimates ≤ 0; consistent with Finding D). On 8 models, **`gemma4:e4b` and `ministral-3:8b` do**: score bias +0.043 [+0.019, +0.065] and +0.053 [+0.028, +0.079], Holm p ≈ 0.001; SPR excess +0.11 and +0.17, Holm p = 0.034. Finding D therefore holds for the 4 historical models, not as a general property. These are also the two best ground truth judges, so they should not judge their own outputs. `lfm2.5`'s judge scores go through a parsing fallback (see the ground truth README) and its level-2 consistency (24.9%) is not meaningful.

Reliability classes depend on the generator set (more generators → more level-2 rows): on 8 generators, `gemma3:4b` moves from UNRELIABLE to CALIBRATED_BUT_STRICT (consistency 69.1% → 70.2%). Treat the classes near thresholds as indicative.

**Few-shot calibration** (supplementary — ground truth corpus, not benchmark pipeline):

Injecting 5 annotated examples per criterion into the checklist judge prompt gives positive point estimates on 3 of 4 judges (gemma3:4b, phi4-mini, mistral:7b) and none on qwen3:1.7b, but **no gain is statistically significant** after Holm correction with 24 evaluable cases (largest: gemma3:4b +12.5 pp, 95% CI [+1.0, +25.0], paired). See [`docs/ground_truth/README.md`](../ground_truth/README.md#few-shot-calibration-finding-10) for details and per-criterion breakdown.
