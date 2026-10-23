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
    ├── mistral-7b_permuted.json
    ├── phi4-mini_fewshot.json      # 24 evaluable cases, few-shot calibration (original order)
    ├── gemma3-4b_fewshot.json
    ├── qwen3-1.7b_fewshot.json
    └── mistral-7b_fewshot.json
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

## Candidate judge models (2026-08)

Four additional candidate judges evaluated on the full 49-case corpus, original order — `ministral-3:8b` and `granite4` as replacements for underperforming `mistral:7b`/`gemma3:4b`; `gemma4:e4b` and `lfm2.5:1.2b-thinking` as smaller/newer alternatives. Both `gemma4:e4b` and `lfm2.5:1.2b-thinking` initially failed on every case (empty response / unclosed `<think>` block respectively) due to a hardcoded 400-token budget in the checklist call path — see `CONTRIBUTING.md` ("Adding a new judge model") for the fix and the `model_quirks.json` mechanism it introduced.

Original order (per criterion), plus reversed / permuted / pooled for the two candidates also run in those orderings (2026-10):

| Judge | data_privacy | human_oversight | non_manipulation | prompt_injection | transparency | Original | Reversed | Permuted | **3 orderings** |
|---|---|---|---|---|---|---|---|---|---|
| gemma4:e4b | 82.5% | 77.5% | 85.0% | 83.3% | 90.0% | 83.7% | 83.2% | 82.1% | **83.0%** |
| ministral-3:8b | 62.5% | 80.0% | 85.0% | 80.6% | 90.0% | 79.6% | 84.2% | 84.2% | **82.7%** |
| granite4 | 75.0% | 62.5% | 80.0% | 58.3% | 82.5% | 71.9% | — | — | — |
| lfm2.5:1.2b-thinking | 47.2%* | 40.0% | 62.5% | 83.3% | 37.5% | 53.6%* | — | — | — |

*lfm2.5:1.2b-thinking: 48/49 cases (1 case failed all 3 retries even with the extended token budget — a sensitive-content prompt).

**Over three orderings**, `gemma4:e4b` (83.0%, 95% case-level CI [76.4, 89.1]) and `ministral-3:8b` (82.7%, [76.5, 88.3]) are **tied**: their difference is +0.3 pp (Bonferroni CI [−5.1, +5.8], Holm p = 0.89; family = the 5 paired differences with the top judge). Both are clearly ahead of the best historical judge, `phi4-mini` (69.0%; gemma4 − phi4-mini +13.9 pp, Bonferroni CI [+3.4, +26.0], Holm p = 0.001). Both are **robust to question order**: none of their four order effects is significant (|Δ| ≤ 4.6 pp, family of 12 judge × ordering comparisons). `granite4` and `lfm2.5:1.2b-thinking` were run in original order only: in that condition gemma4 − granite4 = +11.7 pp (Bonferroni CI [+1.5, +23.0], Holm p = 0.008, family of 7). The 79.4% sometimes quoted for `phi4-mini` was measured on the earlier 34-case corpus and is not comparable. `lfm2.5:1.2b-thinking` is the weakest, comparable to `mistral:7b` (51.5%).

Call parameters differ for two candidates: `gemma4:e4b` and `lfm2.5` run with `max_tokens=6144` / `num_ctx=8192` (via `model_quirks.json`); with the default 400 tokens they return no JSON at all.

> **Do not put `lfm2.5:1.2b-thinking` in a production judge panel without a warning.** In production (multi-criterion) mode it returns a flattened JSON (`{"relevance": 0.9, ..., "flag": ..., "reason": ...}`) instead of per-criterion objects. A fallback in `jobs/eval_runner.py` / `services/judge.py` recovers the scores, but copies the single shared `flag` and `reason` to every criterion — so its per-criterion flags and reasons are not independent judgments.

## Few-shot calibration (Finding 10)

A supplementary experiment injects 5 annotated examples per criterion into the checklist prompt (one per score tier: 0.0 · 0.25 · 0.5 · 0.75 · 1.0). 24 cases are evaluable (49 − 5 held-out examples per criterion × 5 criteria = 25 held out). Original order only.

| Judge | Baseline (24 cases) | Few-shot | Δ |
|---|---|---|---|
| gemma3:4b | 64.2% | 76.0% | **+11.8 pp** |
| phi4-mini | 65.0% | 73.2% | **+8.3 pp** |
| mistral:7b | 56.2% | 61.3% | **+5.1 pp** |
| qwen3:1.7b | 60.5% | 60.2% | −0.2 pp |

Point estimates are largest for structurally inconsistent judges (gemma3:4b) and absent for context-sensitive ones (qwen3:1.7b), but **none of the gains is statistically significant** with 24 cases (paired CIs and Holm correction in *Statistics and figures* below). Results in `results/{judge}_fewshot.json`.

Candidate judges added 2026-08 (see "Candidate judge models" above) — same protocol, same 24 cases:

| Judge | Baseline (24 cases) | Few-shot | Δ |
|---|---|---|---|
| lfm2.5:1.2b-thinking | 53.3% | 63.6% | **+10.4 pp** |
| ministral-3:8b | 75.0% | 78.1% | +3.1 pp |
| gemma4:e4b | 82.3% | 83.3% | +1.0 pp |
| granite4 | 71.9% | 71.9% | +0.0 pp |

lfm2.5:1.2b-thinking benefits most (consistent with its weak baseline calibration); granite4 shows no gain (already well-calibrated).

Baseline is recomputed on the same 24 evaluable cases from the original-order run (the 5 held-out examples are excluded from both).

## Statistics and figures

All from the exported files in `results/`, models from `docs/benchmark/models.json`:

```bash
python scripts/export_groundtruth_results.py --order original --judges gemma4-e4b   # DB -> results/*.json, then validity.json
python scripts/export_groundtruth_results.py --validity-only                       # rebuild validity.json from results/ only
python scripts/groundtruth_stats.py --condition original    # agreement CIs, paired diffs, few-shot CIs, forest plot
python scripts/groundtruth_stats.py                         # same, pooled over the 3 orderings
python scripts/plot_order_sensitivity.py --models paper     # paper figure (4 judges)
python scripts/plot_order_sensitivity.py                    # every judge with 3 orderings
```

- `validity.json` is now rebuilt by script. It matches the published version to within one rounding step (qwen3 prompt_injection 0.371 → 0.370), and globals are stored to 4 decimals. phi4-mini's 3-order agreement is **69.05%** (101.5/147 case-runs). The 69.1% quoted elsewhere comes from rounding per-criterion values to 3 decimals before averaging, and 69.0% is the correctly rounded value. Globals are stored with 6 decimals so that displayed values are rounded only once (gemma3:4b permuted = 32.5/47 = 69.149% → 69.1%, as published).
- Confidence intervals use a case-level cluster bootstrap (all orderings of a case are resampled together).
- Few-shot gains are **paired** (same cases, case-weighted). The table above, produced by `run_fewshot_groundtruth.py`, averages the 5 per-criterion means and does not restrict the baseline to cases with a few-shot result, hence small differences (e.g. gemma3:4b +12.5 pp paired vs +11.8 pp). **No few-shot gain is significant after correction for multiple comparisons** with n ≤ 24. Largest: gemma3:4b +12.5 pp, Bonferroni CI [−2.1, +28.1], Holm p = 0.16 over the 4 paper judges (`groundtruth_stats_paper.json`); Holm p = 0.32 over all 8 judges (`groundtruth_stats.json`).
- **Convention for intervals.** For any comparison that belongs to a family of tests (few-shot gains, order effects, paired differences with the top judge, self-preference across judges, difficulty tiers), we report the **Bonferroni-adjusted CI** (level 1 − 0.05/k) and the **Holm-adjusted p**. Unadjusted 95% CIs are used only for single comparisons (the specialised panel) and for agreement estimates themselves (forest plots), which are not comparisons. The JSON files keep the unadjusted `ci95` for reference. Each comparison has its own named seed, so adding a judge doesn't shift other judges' numbers.
- Order effects are tested as one family of 12 comparisons: the 6 judges run in three orderings × {reversed, permuted} (choice made on 2026-10-16). The largest effect, phi4-mini permuted (−11.2 pp), is **not significant** after correction (Bonferroni CI [−24.5, 0.0], Holm p = 0.058); no other effect comes close. For reference only, restricted to the 4 paper judges (family of 8) it would have been significant (Holm p = 0.04) — which is why the family is always stated.
- Historical `*_original/reversed/permuted.json` files were exported from the DB in May. The current results API returns neither `score` nor `created_at`, so the exporter recomputes `score` from the answers and leaves `created_at` null; use `--judges` to avoid rewriting those files.

## Repeated runs (`run_label`)

Every stored result carries a `run_label`. `main` is the set every analysis reads (validity, best judges, order sensitivity, incoherence, `GET /groundtruth/results` by default, hence the exports and statistics). Any other label is a separate repetition, stored alongside and excluded from those analyses: pass `run_label` to `POST /groundtruth/run/{case_id}` and `GET /groundtruth/results/{case_id}` (`all` returns every run), or `--run-label` to `groundtruth.py run` (the per-judge skip is per label, so a labelled run resumes where it stopped). Each row also records the Ollama digest of the model that answered (`model_digest`), with `created_at`, `latency_ms` and the raw response.

**Test-retest run** (protocol of 2026-10-23): `back/evaluation/scripts/retest.py` runs the 8 judges on the 49 cases at temperature 0 under nine labels: `retest-orig-r1..r5` (original order, K = 5), `retest-rev-r1..r2` and `retest-perm-r1..r2` (order control, same permutation q2→q4→q1→q3 as the main runs), interleaved, unloading each judge from Ollama at the end of its block. Safe to interrupt and relaunch (`python scripts/retest.py` in the container; `--dry-run` prints the plan; last line `ALL_DONE`).

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

Few-shot calibration (from project root, services running — see "Few-shot calibration" above):
```bash
python scripts/run_fewshot_groundtruth.py                                   # all 4 default judges
python scripts/run_fewshot_groundtruth.py --judges ollama/phi4-mini         # single judge
python scripts/run_fewshot_groundtruth.py --criterion transparency          # single criterion
python scripts/run_fewshot_groundtruth.py --dry-run                         # print prompts only
```
`--judges` accepts any model registered in `infra/litellm_config.yaml`, not just the 4 defaults in `ALL_JUDGES`. Before running a new model here, check whether it needs a call-quirk override — see "Adding a new judge model" in `CONTRIBUTING.md`.

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
