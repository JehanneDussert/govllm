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

Planned analyses once all result files are complete — see `docs/benchmark/analysis/` (to be created):

- Specialised panel vs single judge delta
- Model size vs score correlation
- Inter-judge disagreement per prompt (top 10 most discriminating prompts)
- Intra-judge variance per domain
- Family bias — judge × generator matrix
- Self-evaluation vs cross-evaluation (leniency bias)
