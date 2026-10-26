# govllm

> ⚠️ *Personal project — not affiliated with, funded by, or endorsed by any French public administration.*

> How do you justify a model choice six months after go-live?

Self-hosted LLM governance monitoring for regulated environments. Continuous scoring against EU AI Act, GDPR, and ANSSI — not a one-shot benchmark.

Built out of a question I couldn't find a good answer to, working on LLM deployment in the French public sector. Directly applicable to AI Act Article 9 requirements (ongoing risk management) and NIS2 operational continuity constraints.

[![License: EUPL-1.2](https://img.shields.io/badge/License-EUPL--1.2-00d4b8.svg)](LICENSE)
[![Paper](https://img.shields.io/badge/arXiv-2605.24737-b31b1b.svg)](https://arxiv.org/abs/2605.24737)
[![Dataset](https://img.shields.io/badge/HuggingFace-Dataset-yellow)](https://huggingface.co/datasets/JehanneDussert/govllm-compliance-corpus)
[![Stack](https://img.shields.io/badge/stack-FastAPI%20%7C%20Vue%203%20%7C%20Ollama-3a3a3a)](https://github.com/JehanneDussert/govllm)

![govllm demo](docs/screenshots/govllm-demo.gif)

---

## What it does

govllm scores LLM outputs continuously against configurable governance profiles. Each response is evaluated by a local LLM-as-a-judge across criteria mapped to regulatory frameworks. The best-performing model per use case is selected automatically — based on your governance criteria, not raw performance metrics.

```
Request → Governance profile → LLM-as-a-judge scoring → Dynamic routing → Model A / B / C / D
                    ↑                                          |
                    └──────────── metrics refine criteria ─────┘
```

No data leaves your infrastructure. Local models via Ollama. Observable via Grafana and Prometheus.

---

## Research

This project is accompanied by a preprint:

**Who Judges the Judges? Governance from Metrics: A Runtime Framework for Continuous LLM Compliance Monitoring**
Jehanne Dussert · arXiv:2605.24737 · May 2026

Key findings: small-judge validity varies widely (51.5%–69.0% agreement with a 49-case ground truth, averaged over three question orderings) · question order may matter for some judges (phi4-mini: −11 pp when sub-questions are permuted, but not significant after correction over the 12 judge × ordering comparisons of the 6 judges run in three orderings: Bonferroni-adjusted 95% CI [−24.5, 0.0], Holm-adjusted p = 0.058) · parameter count is a poor proxy for governance quality. A specialised per-criterion judge panel and few-shot calibration gave positive but not statistically significant gains (details below).

[Read the paper →](https://arxiv.org/abs/2605.24737) · [Annotated corpus (49 cases)](https://github.com/JehanneDussert/govllm/blob/main/docs/ground_truth/corpus.json)

---

## Architecture

```
User
│
▼
Frontend :5173 (Vue 3 + ECharts)
│
├──► llm-gateway :8001 ──► LiteLLM ──► Ollama (qwen / gemma / mistral / phi)
│         │
│         └──── Redis pub/sub
│
├──► observability :8002 ──► Prometheus / Grafana / Langfuse
│
└──► evaluation :8003 ──► Local judge (Ollama) ──► Benchmark · Matrix · Score
```

Three independent FastAPI microservices share a `back/shared/` layer (Pydantic schemas + config).  
→ See [back/README.md](back/README.md) for full API reference and service structure.

---

## Screenshots

### Model × use case matrix
![Matrix view](docs/screenshots/matrix.png)
*Score heatmap per model and use case — auto-routes traffic to best performer per governance profile.*

### Governance profiles & judge configuration
![Judge settings](docs/screenshots/judge-settings.png)
*Activate a full compliance profile in one click. Criteria, weights and use cases are configurable from the UI.*

---

## Quickstart

**Prerequisites:** Docker, docker compose, uv.

```bash
git clone https://github.com/JehanneDussert/govllm
cd govllm

cp infra/.env.example infra/.env
# Fill in Langfuse keys

make dev        # hot reload — code changes reflected immediately
# or
make prod       # built images + static front container + Caddy reverse proxy

make pull-models
```

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| Gateway | http://localhost:8001/docs |
| Observability | http://localhost:8002/docs |
| Evaluation | http://localhost:8003/docs |
| Langfuse | http://localhost:3000 |
| Grafana | http://localhost:3001 |
| Prometheus | http://localhost:9090 |

---

## Governance profiles

Four built-in profiles, each activating a targeted set of criteria and weights:

| Profile | Frameworks | Focus |
|---|---|---|
| **AI Act Compliance** | EU AI Act Art. 5, 13, 14 | Transparency, human oversight, non-manipulation |
| **Data Protection** | GDPR, ANSSI | Data privacy, leakage prevention, traceability |
| **Security** | ANSSI, OWASP LLM Top 10 | Prompt injection, robustness, adversarial inputs |
| **Accessibility & Inclusion** | RGAA, FALC | Language clarity, cognitive load, inclusive design |

Profiles are applied at runtime — switching a profile updates which criteria are active and their weights without restarting any service. Custom profiles can be created from the Settings view.

**Experimental — Identity & Access Governance.** A fifth profile (`identity_access_governance`) applies the same checklist judging to account access logs instead of LLM outputs: scope, volume and temporal conformity, session geo-consistency, and sensitive export justification (ANSSI, GDPR Art. 9/32, NIS2 Art. 21). A rolling per-account baseline flags candidate windows, which are then judged via `POST /identity-access/evaluate`. Its 5 criteria are disabled by default; there is no annotated corpus yet, so no validity figures are reported for it.

---

## Judge criteria

14 criteria across quality, ethics, compliance, accessibility, and security. All configurable from the UI.

| Criterion | Regulatory anchor | Default |
|---|---|---|
| Relevance | Quality baseline | ✅ |
| Factual reliability | AI Act | ✅ |
| Prompt injection | OWASP LLM01, ANSSI | ✅ |
| Data leakage | OWASP LLM02, ANSSI | ✅ |
| Ethical refusal | ANSSI, ethics | ✅ |
| Non-manipulation | AI Act Art. 5 | — |
| Human oversight | AI Act Art. 14 | — |
| Explicability | AI Act Art. 13 | — |
| Transparency | AI Act | — |
| Data privacy | GDPR | — |
| Language clarity | RGAA, FALC | — |
| Cognitive load | RGAA | — |
| Fairness | AI Act, ethics | — |
| Robustness | ANSSI | — |

The judge model runs locally (`ollama/ministral-3:8b` by default, see *Default judge* below). Evaluation calls are filtered from the traces view so only user interactions appear.

---

## Ground truth validity

Arena metrics (variance, incoherence rate, bias matrix) measure judge **reliability**. To measure **validity** — does the judge actually detect regulatory violations? — govllm uses a curated binary-checklist corpus of **49 annotated cases** (English and French) anchored to CNIL decisions, ANSSI guidelines, and EU AI Act provisions.

Each case is evaluated across three question orderings (original, reversed, permuted) to quantify position bias in small LLM judges. Agreement ranges from 51.5% (mistral:7b) to 69.0% (phi4-mini), averaged across all three orderings. The permuted ordering changes phi4-mini's agreement by −11.2 pp (49 cases), the largest order effect observed, but it is not significant after correction for multiple comparisons over the 12 judge × ordering comparisons of the 6 judges run in three orderings (these 4 judges plus two newer candidate judges): Bonferroni-adjusted 95% CI [−24.5, 0.0], Holm-adjusted p = 0.058. No other order effect comes close; the two newer judges are insensitive to order (|Δ| ≤ 4.6 pp). Per-criterion drops look larger (−25 pp on `data_privacy`) but rest on 10 cases and are not statistically significant. mistral:7b is flat at 51.5% across all three orderings, confirming structural miscalibration rather than positional sensitivity.

**Unusable judge answers are data, not gaps.** Every judge call is stored, including those whose output cannot be turned into a complete true/false vector, with an explicit status (`call_error`, `json_error`, `empty`, `parse_error`) and the raw response. One parsing rule applies to every judge model (accepted shapes: the documented `{"answers": {...}}` object, a positional list, `q1..qN` keys at the top level, and the prompt label echoed back, e.g. `"true (compliant)"`). Agreement is computed on usable answers; `scripts/groundtruth_stats.py` also reports the usable-answer rate per judge and ordering, and the agreement when every unusable answer counts as a full disagreement.

→ See [docs/ground_truth/README.md](docs/ground_truth/README.md) for corpus details, empirical results, and reproducibility commands.

---

## Benchmark

48 prompts across 6 use cases and 4 difficulty levels (2 easy · 2 medium · 2 adversarial · 2 hard each). Fixed-output evaluation: all judges score the same model answers, making cross-judge comparison valid. 768 scored entries (48 × 4 generators × 4 judges), 32 per (model, use case) cell.

Completed analyses: domain-specific profiles vs the quality-baseline profile on hard prompts (+5.7 pp; Bonferroni-adjusted 95% CI [−0.9, +12.2], Holm-adjusted p = 0.12 across the 4 difficulty tiers, so not significant; only 12 prompts from different use cases), model size vs score correlation (Pearson r = −0.39, n=4), inter-judge disagreement per prompt (top discriminator: `ana_hard_01`, σ=0.256), family bias matrix (no significant self-preference among these 4 models), and judge reliability classification.

A specialised per-criterion judge panel (each criterion assigned to its most valid judge) scores 72.6% against 69.0% for the best single judge on the ground truth. The +3.5 pp difference is not statistically significant (95% CI [−0.9, +9.0], case-level bootstrap; a single comparison, so no multiplicity correction applies), and the panel was selected on the same data it is evaluated on, so it should be confirmed on held-out cases.

A preliminary few-shot calibration experiment (5 annotated examples per criterion injected into the checklist judge prompt) shows positive point estimates for 3 of 4 judges (gemma3:4b, phi4-mini, mistral:7b) and none for qwen3:1.7b. With 24 evaluable cases, none of these gains is statistically significant after correction for multiple comparisons across the 4 judges. The largest, gemma3:4b +12.5 pp (paired), has a Bonferroni-adjusted 95% CI of [−2.1, +28.1] (Holm-adjusted p = 0.16). Treat few-shot calibration as a direction to test on a larger corpus, not an established improvement. Results in `docs/ground_truth/results/{judge}_fewshot.json`.

→ See [docs/benchmark/README.md](docs/benchmark/README.md) for pipeline, file formats, and analysis results.

---

## Stack

| Layer | Technology |
|---|---|
| Inference | Ollama — phi4-mini · gemma3:4b · mistral:7b · qwen3:1.7b |
| Proxy | LiteLLM |
| Backend | FastAPI · Python 3.11 · uv |
| Tracing | Langfuse v2 |
| Metrics | Prometheus + Grafana |
| Event bus | Redis |
| Reverse proxy | Caddy |
| Frontend | Vue 3 · TypeScript · ECharts |
| Infra | Docker Compose |

---

## Project structure

```
govllm/
├── back/                    # three FastAPI microservices + shared layer
│   └── README.md            # API reference + service structure
├── docs/
│   ├── benchmark/           # prompts, model references, judge results
│   │   └── README.md        # pipeline + file schemas
│   └── ground_truth/        # annotated validity corpus
│       └── README.md        # corpus, empirical results, reproducibility
├── front/                   # Vue 3 frontend
│   └── README.md            # views documentation
├── scripts/                 # benchmark pipeline scripts
│   └── run_full_benchmark.py
└── infra/                   # Docker Compose, LiteLLM config, Prometheus, Grafana
```

---

## Key design decisions

**Governance from metrics.** Model selection is driven by governance criteria, not performance alone. The score matrix accumulates from real production usage — not synthetic benchmarks.

**Local evaluation judge.** Scoring runs on Ollama — sovereign and usable in air-gapped or regulated environments (public sector, healthcare, finance). No response data sent to external APIs.

**Profile-driven routing.** Switching a governance profile at runtime updates which criteria are active and their weights. The routing layer reads the active profile from Redis at inference time and recommends the best-scoring model for that profile and use case.

**No self-judging.** A model should not evaluate its own answers. The Chat view warns when the current generator (auto-routed or picked manually) is one of the judges that will score it under the active profile: a panel member with active criteria, or the global judge for the criteria the panel does not cover. Judges are also tagged in the model scoreboard. Settings flags the same conflict per profile against each use case's preferred model.

**Default judge: `ministral-3:8b`.** It is versioned in `DEFAULT_JUDGE_MODEL` (`back/evaluation/services/judge_config.py`). Why this model:
- **Tied best on the ground truth**: 82.7% agreement over three question orderings (49 cases), against 83.0% for `gemma4:e4b`. The +0.3 pp difference is not significant (Bonferroni CI [−5.1, +5.8]).
- **Robust to question order**: none of its order effects is significant.
- **Measured self-preference**: it rates its own outputs higher than judges from other families do (score bias +0.053, Bonferroni CI [+0.018, +0.091]). It must therefore **not also be used as the generator**.

**Judges are excluded from AUTO routing.** `GET /matrix/routing` never recommends an effective judge of the active profile: the global judge, plus panel members that hold active criteria. The same rule as the evaluation dispatch applies (`services/routing.py`, mirrored in `front/src/utils/judges.ts`). With the default config, `ministral-3:8b` therefore stays in the routing pool (`BENCHMARK_MODELS`) but is never auto-selected as the generator. Judges are flagged `is_judge` in the response and tagged in the Chat scoreboard.
- **Manual selection** is kept: you can still pick a judge by hand, and the Chat view warns that it will judge its own answers.
- **Fallback**: if excluding the judges leaves nothing to recommend for the use case (every model in the pool is a judge, or with the `strict` strategy only judges pass the thresholds), routing keeps its usual choice, returns `judge_exclusion_fallback: true`, and the Chat view shows a warning.

A different `judge_model` saved in Redis (for example left over by a benchmark run) is reported in the evaluation service logs at startup and in Settings → Judge (`GET /config/judge/defaults`). `scripts/run_full_benchmark.py` now restores the judge config it found when it ends, even on error.

**Shared schema layer.** All three microservices share `back/shared/src/shared/` for Pydantic schemas and config — single source of truth for data contracts.

**Governance context injection.** The gateway reads the active profile and use case from Redis on every chat call and prepends a system message (`"Task type: X. Governance framework: Y."`) before passing messages to the model. The caller can override this by sending its own `system` message.

**Judge traces filtered.** Evaluation calls to LiteLLM are excluded from the traces view so only user interactions appear.

**Dev/prod parity via compose overrides.** `make dev` mounts source volumes with `--reload`. `make prod` builds images and serves the front as a static container (nginx inside, served through Caddy as reverse proxy). Same base compose file, no drift.

---


## Relevant standards and resources

**Regulatory texts**
- [EU AI Act](https://artificialintelligenceact.eu/ai-act-explorer/) — Art. 5, 9, 13, 14
- [GDPR Art. 22](https://gdpr-info.eu/art-22-gdpr/) — automated decision-making
- [ANSSI SecNumCloud](https://cyber.gouv.fr/offre-de-service/solutions-certifiees-et-qualifiees/services-de-securite-evalue/solutions-en-cours-de-qualification/prestataires-secnumcloud/)
- [NIS2 Directive](https://digital-strategy.ec.europa.eu/en/policies/nis2-directive)

**Evaluation and benchmarking**
- [COMPL-AI](https://compl-ai.org) — AI Act compliance benchmarking (ETH Zurich)
- [LM Evaluation Harness](https://github.com/EleutherAI/lm-evaluation-harness) — EleutherAI
- [OWASP LLM Top 10](https://owasp.org/www-project-top-10-for-large-language-model-applications/)

**LLM observability landscape**

govllm is positioned on two axes: sovereign/on-premise deployment and governance-first scoring (regulatory criteria, not just performance metrics).

- [Langfuse](https://langfuse.com) — open-source tracing, self-hostable. Used as govllm's tracing layer.
- [Giskard](https://giskard.ai) — LLM testing and red-teaming, EU-based.
- [Arize AI](https://arize.com) — production LLM observability. Cloud-first.
- [Fiddler AI](https://fiddler.ai) — enterprise ML + LLM monitoring, regulated industries.
- [LatticeFlow AI](https://latticeflow.ai) — AI Act compliance validation. Closed, enterprise.
- [Holistic AI](https://holisticai.com) — AI governance and risk management. Audit-oriented.

govllm's differentiator: fully local inference, governance criteria mapped to EU/French regulatory frameworks, and profile-driven routing based on production scores — not pre-deployment benchmarks.

**French public sector context**
- [DINUM Albert](https://www.numerique.gouv.fr/offre-accompagnement/expertise-albert-ia-etat/) — French government's sovereign LLM
- [CNIL AI guidance](https://www.cnil.fr/fr/intelligence-artificielle)
- [Projet PANAME](https://www.cnil.fr/fr/projet-paname-participez-aux-tests-dun-outil-daudit-rgpd-des-modeles-dia) — CNIL's GDPR audit tool for AI models
- [AI Charters Portal for Public Administration](https://alliance.numerique.gouv.fr/ressources/portail-des-chartes-ia-dans-ladministration/)

**On AI ethics charters**

Where charters articulate what should be done, govllm provides a technical layer to verify that it is actually being done, continuously, in production. Principles need observability to become practice.

---

## Contributing

Contributions welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for local setup, monorepo structure, development conventions, running the ground truth tests, and how to propose a new governance profile or criterion. Self-contained starting points are tagged [`good first issue`](https://github.com/JehanneDussert/govllm/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22).

---

## Backups

`scripts/backup_db.sh` makes a daily `pg_dump` of the govllm and Langfuse schemas, with hashes and row counts.
- **Rotation:** 7 daily and 4 weekly copies.
- **Restore test:** every weekly copy is restore-tested in a throwaway PostgreSQL.
- **Off-PC copy:** encrypted, made only when the operator configures it.

`scripts/backup_restore_test.sh` checks any backup. Restore and scheduling: [docs/backups.md](docs/backups.md).

## Development notes

Some documentation and automation scripts were generated with [Claude Code](https://claude.ai/code) — specifically the benchmark pipeline (`scripts/run_full_benchmark.py`) and the ground truth corpus scripts (`back/evaluation/scripts/`). The core architecture, governance framework, and evaluation design are original work.

---

## License

EUPL-1.2
