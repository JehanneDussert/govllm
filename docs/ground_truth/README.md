# Ground Truth Corpus — govllm

Validity assessment of LLM judges against a manually annotated corpus grounded in CNIL decisions, ANSSI guidelines, and EU AI Act provisions.

## Structure

```
docs/ground_truth/
├── README.md            # this file
├── criteria.md          # sub-question definitions per criterion
├── corpus.json          # 34 annotated cases (prompt + response + ground truth)
├── validity.json        # aggregated agreement rates per judge × criterion
└── results/
    ├── phi4-mini_original.json     # 34 cases, original question order
    ├── phi4-mini_reversed.json     # 34 cases, reversed question order
    ├── qwen3-1.7b_original.json
    ├── qwen3-1.7b_reversed.json
    ├── gemma3-4b_original.json
    ├── gemma3-4b_reversed.json
    ├── mistral-7b_original.json
    └── mistral-7b_reversed.json
```

## Corpus

**34 cases** across 5 governance criteria, sourced from real regulatory contexts:

| Criterion | Cases | Legal anchor |
|---|---|---|
| `data_privacy` | 7 | GDPR Art. 5, 6, 9, 22 |
| `human_oversight` | 7 | EU AI Act Art. 14, ANSSI R9 |
| `non_manipulation` | 7 | EU AI Act Art. 5(1)(a)(b), UCPD Art. 6–8 |
| `prompt_injection` | 6 | ANSSI-PA-102 §4, OWASP LLM Top 10 LLM01 |
| `transparency` | 7 | EU AI Act Art. 50(1), Art. 13 |

Each case contains:
- `prompt` — user input to the AI system
- `response` — AI-generated response being evaluated
- `source` — regulatory anchor for the ground truth
- `expected` — ground truth answers `{q1: bool, q2: bool, q3: bool, q4: bool}` (true = compliant, false = violation)

The sub-questions per criterion are defined in [`criteria.md`](criteria.md).

## Evaluation method

Each case was submitted to 4 judge models in **checklist mode**: the judge answers binary sub-questions (true/false) per criterion rather than producing a continuous score. Agreement is computed as the fraction of sub-questions answered correctly against the ground truth.

Two question orderings were tested to measure **position bias** (see §5.4 of the paper):
- `original` — questions in canonical order
- `reversed` — questions in reverse order

## Results

### Agreement rate by judge × criterion (original + reversed averaged)

| Judge | data_privacy | human_oversight | non_manipulation | prompt_injection | transparency | **global** |
|---|---|---|---|---|---|---|
| phi4-mini | 82.1% | 87.5% | 89.3% | 87.5% | 55.4% | **80.1%** |
| qwen3:1.7b | 69.6% | 82.1% | 69.6% | 35.4% | 69.6% | **66.2%** |
| gemma3:4b | 57.1% | 73.2% | 78.6% | 66.7% | 69.6% | **69.1%** |
| mistral:7b | 53.6% | 42.3% | 46.4% | 70.8% | 39.3% | **50.0%** |

**Key findings:**
- **phi4-mini** is the strongest judge overall (80.1%), consistent across criteria except `transparency` (55.4%)
- **mistral:7b** is the weakest judge (50.0%), performing near random on `transparency` (39.3%) and `human_oversight` (42.3%)
- **prompt_injection** is the hardest criterion for qwen3:1.7b (35.4%) — the model interprets legitimate system prompt references as disclosure violations
- No single judge dominates across all criteria

### Position bias (original vs reversed)

| Judge | Δ global | Most sensitive criterion |
|---|---|---|
| phi4-mini | +1.5 pp | stable across all |
| qwen3:1.7b | −10.3 pp | non_manipulation (−25 pp), transparency (−25 pp) |
| gemma3:4b | 0.0 pp | non_manipulation (+14 pp), transparency (−18 pp) offset |
| mistral:7b | +1.5 pp | insensitive but uniformly low |

Question order significantly affects qwen3:1.7b — reversing sub-questions degrades its agreement by up to 25 percentage points on individual criteria. phi4-mini is the most robust to ordering.

## Reproducibility

To re-run the evaluation from scratch:

```bash
# Seed the corpus (drops and recreates tables)
make gt-seed

# Run all 4 judges on original order
make gt-run

# Run all 4 judges on reversed order  
make gt-run-reversed

# View results
make gt-summary
```

Results are stored in the PostgreSQL `govllm` schema (`groundtruth_cases`, `groundtruth_results` tables) and exposed via:
- `GET /groundtruth/validity` — agreement rates per judge × criterion × sub-question
- `GET /groundtruth/order-sensitivity` — flip rate and Δ agreement per judge × criterion
- Frontend: **Arena → Corpus tab**
