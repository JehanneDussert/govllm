# Ground Truth Corpus — govllm

Validity assessment of LLM judges against a manually annotated corpus grounded in CNIL decisions, ANSSI guidelines, and EU AI Act provisions.

## Structure

```
docs/ground_truth/
├── README.md            # this file
├── criteria.md          # sub-question definitions per criterion
├── corpus.json          # 49 annotated cases (prompt + response + ground truth)
├── validity.json        # aggregated agreement rates per judge × criterion (all 3 orders)
└── results/
    ├── phi4-mini_original.json     # 49 cases, original question order
    ├── phi4-mini_reversed.json     # 49 cases, reversed question order
    ├── phi4-mini_permuted.json     # 49 cases, permuted order (q2→q4→q1→q3)
    ├── qwen3-1.7b_original.json
    ├── qwen3-1.7b_reversed.json
    ├── qwen3-1.7b_permuted.json
    ├── gemma3-4b_original.json
    ├── gemma3-4b_reversed.json     # 48 cases (1 missing — persistent gemma3 JSON formatting issue)
    ├── gemma3-4b_permuted.json     # 47 cases (2 missing — persistent gemma3 JSON formatting issue)
    ├── mistral-7b_original.json
    ├── mistral-7b_reversed.json
    └── mistral-7b_permuted.json
```

## Corpus

**49 cases** across 5 governance criteria, sourced from real regulatory contexts.  
**Bilingual** — 45 cases in English, 4 cases in French (realistic CNIL/ANSSI regulatory scenarios).

| Criterion | Cases | Legal anchor |
|---|---|---|
| `data_privacy` | 10 | GDPR Art. 5, 6, 9, 22 |
| `human_oversight` | 10 | EU AI Act Art. 14, ANSSI R9 |
| `non_manipulation` | 10 | EU AI Act Art. 5(1)(a)(b), UCPD Art. 6–8 |
| `prompt_injection` | 9 | ANSSI-PA-102 §4, OWASP LLM Top 10 LLM01 |
| `transparency` | 10 | EU AI Act Art. 50(1), Art. 13 |

Each case contains:
- `prompt` — user input to the AI system
- `response` — AI-generated response being evaluated
- `source` — regulatory anchor for the ground truth
- `language` — `"en"` or `"fr"`
- `expected` — ground truth answers `{q1: bool, q2: bool, q3: bool, q4: bool}` (true = compliant, false = violation)

The sub-questions per criterion are defined in [`criteria.md`](criteria.md).

## Evaluation method

Each case was submitted to 4 judge models in **checklist mode**: the judge answers binary sub-questions (true/false) per criterion rather than producing a continuous score. Agreement is computed as the fraction of sub-questions answered correctly against the ground truth.

Three question orderings were tested to measure **position bias** (see §5.4 of the paper):
- `original` — questions in canonical order (q1→q2→q3→q4)
- `reversed` — questions in reverse order (q4→q3→q2→q1)
- `permuted` — interleaved order (q2→q4→q1→q3)

## Results

### Agreement rate by judge × criterion (weighted mean across all 3 orders)

| Judge | data_privacy | human_oversight | non_manipulation | prompt_injection | transparency | **global** |
|---|---|---|---|---|---|---|
| phi4-mini | 70.8% | 65.8% | 78.3% | 81.5% | 50.0% | **69.1%** |
| gemma3:4b | 55.2% | 63.8% | 76.7% | 72.2% | 63.8% | **66.3%** |
| qwen3:1.7b | 65.0% | 66.7% | 63.3% | 37.1% | 66.7% | **60.2%** |
| mistral:7b | 52.5% | 40.0% | 52.5% | 72.2% | 42.5% | **51.5%** |

### Per-order breakdown

| Judge | orig global | rev global | perm global |
|---|---|---|---|
| phi4-mini | 71.9% | 74.5% | 60.7% |
| gemma3:4b | 65.8% | 64.1% | 69.1%* |
| qwen3:1.7b | 65.3% | 58.2% | 57.1% |
| mistral:7b | 51.5% | 51.5% | 51.5% |

*47/49 cases for gemma3:4b permuted, 48/49 for gemma3:4b reversed (3 persistent JSON formatting failures total).

**Key findings:**
- **phi4-mini** best judge overall on original/reversed (71.9–74.5%), but degrades significantly on permuted (60.7%, −11.2 pp) — strongest position bias on `data_privacy` (−25 pp)
- **mistral:7b** weakest judge (51.5% flat across all 3 orderings), insensitive to question order — structural miscalibration, not positional
- **prompt_injection** hardest criterion for qwen3:1.7b (41.7% original, 27.8% reversed) — model interprets legitimate system prompt references as disclosure violations
- **gemma3:4b** improves on permuted for 3/5 criteria (data_privacy +14 pp, human_oversight +12 pp, non_manipulation +10 pp)
- No single judge dominates across all criteria and orderings

### Position bias (significant deltas ≥ 10 pp)

| Judge | Criterion | original | reversed | permuted | Max Δ |
|---|---|---|---|---|---|
| phi4-mini | data_privacy | 77.5% | 82.5% | **52.5%** | −25.0 pp |
| phi4-mini | non_manipulation | 82.5% | 82.5% | **70.0%** | −12.5 pp |
| phi4-mini | transparency | 52.5% | 55.0% | **42.5%** | −10.0 pp |
| qwen3:1.7b | non_manipulation | **72.5%** | 60.0% | 57.5% | −15.0 pp |
| qwen3:1.7b | human_oversight | **70.0%** | 72.5% | 57.5% | −12.5 pp |
| qwen3:1.7b | transparency | **75.0%** | 60.0% | 65.0% | −10.0 pp |
| gemma3:4b | data_privacy | 47.5% | 57.5% | **61.1%** | +13.6 pp |
| gemma3:4b | human_oversight | 57.5% | 65.0% | **69.4%** | +11.9 pp |
| gemma3:4b | non_manipulation | 70.0% | 80.0% | **80.0%** | +10.0 pp |
| gemma3:4b | transparency | **80.0%** | 55.6% | 55.0% | −25.0 pp |

## Reproducibility

The unified entry point is `back/evaluation/scripts/groundtruth.py`. Run from inside the evaluation container or via `make gt-*` targets from the project root.

```bash
# Seed the corpus (drops and recreates tables; reads docs/ground_truth/corpus.json)
make gt-seed

# Run all 4 judges — 3 orderings (per-judge skip logic: safe to interrupt and resume)
make gt-run           # original order  → /tmp/gt_run_original.log
make gt-run-reversed  # reversed order  → /tmp/gt_run_reversed.log
make gt-run-permuted  # permuted order  → /tmp/gt_run_permuted.log

# Export results to JSON files (docs/ground_truth/results/)
python back/evaluation/scripts/groundtruth.py run --compare   # compare original vs reversed

# View live summary
make gt-summary
```

Direct script usage (inside container):
```bash
python groundtruth.py seed                            # DROP+CREATE + 49 cases from corpus.json
python groundtruth.py run                             # original order
python groundtruth.py run --order reversed            # reversed
python groundtruth.py run --order permuted            # permuted (q2→q4→q1→q3)
python groundtruth.py run --criterion transparency    # filter by criterion
python groundtruth.py run --judges ollama/qwen3:1.7b  # filter by judge
python groundtruth.py extend new_cases.json           # add cases from JSON + evaluate
```

Results are stored in the PostgreSQL `govllm` schema (`groundtruth_cases`, `groundtruth_results` tables) and exposed via:
- `GET /groundtruth/validity` — agreement rates per judge × criterion × sub-question
- `GET /groundtruth/order-sensitivity` — flip rate and Δ agreement per judge × criterion
- Frontend: **Arena → Corpus tab**

## Infrastructure notes

- Ollama is single-threaded (`OLLAMA_NUM_PARALLEL=1`) — judges run sequentially
- qwen3:1.7b requires `think: false` via LiteLLM to disable thinking mode (prevents unbounded token generation)
- LiteLLM timeout set to 600s per model (`infra/litellm_config.yaml`)
- Per-judge skip logic: `groundtruth.py run` checks `(case_id, question_order, judge_model)` before submitting — granular resume after crash
- `timeout=None` in the run client — no client-side timeout; the service handles its own 300s per Ollama call
