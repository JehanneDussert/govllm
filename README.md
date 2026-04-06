# govllm

> How do you justify a model choice six months after go-live?

Self-hosted LLM governance monitoring for regulated environments. Continuous scoring against EU AI Act, GDPR, and ANSSI — not a one-shot benchmark.

Built out of a question I couldn't find a good answer to, working on LLM deployment in the French public sector. Directly applicable to AI Act Article 9 requirements (ongoing risk management) and NIS2 operational continuity constraints.

[![License: EUPL-1.2](https://img.shields.io/badge/License-EUPL--1.2-00d4b8.svg)](LICENSE)
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

## Architecture

```
User
│
▼
Frontend :5173 (Vue 3 + ECharts)
│
├──► llm-gateway :8001 ──► LiteLLM ──► Ollama (qwen / gemma / llama / deepseek)
│         │
│         └──── Redis pub/sub
│
├──► observability :8002 ──► Prometheus / Grafana / Langfuse
│
└──► evaluation :8003 ──► Local judge (Ollama) ──► Benchmark · Matrix · Score
```

Three independent FastAPI microservices share a `back/shared/` layer (Pydantic schemas + config) and communicate via HTTP and Redis pub/sub.

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
make prod       # built images + nginx front

make pull-models
```

Services:

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

---

## Judge criteria

The evaluation layer runs a local LLM-as-a-judge after each response. The system prompt is displayed in full in the Settings view. All criteria are configurable from the UI; custom criteria can be added.

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

The judge model runs locally (`ollama/gemma3:1b` by default). Evaluation calls are filtered from the traces view so only user interactions appear.

---

## Model × use case matrix

Scores accumulate per use case in Redis. The matrix view shows which model performs best per task under the active governance profile:

```
                    qwen2.5:1.5b   llama3.2:3b   gemma3:1b   deepseek-r1:1.5b
Summary                 0.84           0.71          0.69           0.72
Translation             0.79           0.88          0.74           0.71
Code                    0.72           0.85          0.82           0.77
Administrative writing  0.88           0.82          0.71           —
```

→ gemma3 and llama3.2 lead on code, qwen2.5 on admin writing. The smart router reads this matrix at inference time and routes to the best-scoring model for the active profile and use case.

---

## Multi-model benchmark

```bash
curl http://localhost:8003/benchmark/results
```

```json
{
  "models": [
    { "model": "ollama/qwen2.5:1.5b",     "sample_size": 12, "avg_latency_ms": 4.2,  "avg_eval_score": 0.84 },
    { "model": "ollama/gemma3:1b",         "sample_size": 9,  "avg_latency_ms": 2.1,  "avg_eval_score": 0.82 },
    { "model": "ollama/llama3.2:3b",       "sample_size": 14, "avg_latency_ms": 8.7,  "avg_eval_score": 0.76 },
    { "model": "ollama/deepseek-r1:1.5b",  "sample_size": 7,  "avg_latency_ms": 5.3,  "avg_eval_score": 0.71 }
  ],
  "winner": "ollama/qwen2.5:1.5b",
  "window": "last 50 traces"
}
```

Winner is determined by eval score when available across all models, latency otherwise.

---

## Stack

| Layer | Technology |
|---|---|
| Inference | Ollama — qwen2.5:1.5b · gemma3:1b · llama3.2:3b · deepseek-r1:1.5b |
| Proxy | LiteLLM |
| Backend | FastAPI · Python 3.11 · uv |
| Tracing | Langfuse v2 |
| Metrics | Prometheus + Grafana |
| Event bus | Redis |
| Reverse proxy | Caddy |
| Frontend | Vue 3 · TypeScript · ECharts |
| Infra | Docker Compose |

---

## API endpoints

### llm-gateway — :8001
```
POST /chat          # chat completion (streaming SSE + non-streaming)
GET  /health
```

### observability — :8002
```
GET /metrics?window=24h    # latency p50/p95/p99, error rate, request count per model
GET /traces?limit=50       # production traces with eval scores (judge traces filtered)
```

### evaluation — :8003
```
GET  /benchmark/results         # multi-model benchmark across all configured models
GET  /matrix                    # use case × model score matrix
GET  /matrix/routing            # recommended model for active profile + use case
GET  /config/judge              # judge configuration
PUT  /config/judge              # update judge configuration
POST /config/judge/profile/{id} # activate a governance profile
POST /eval/score                # trigger async evaluation (returns 202 immediately)
GET  /eval/result/{trace_id}    # poll for evaluation result
```

---

## Project structure

```
govllm/
├── .env.example
├── Makefile
├── back/
│   ├── shared/src/shared/   # config.py, schemas.py
│   ├── llm-gateway/         # chat endpoint, Redis publisher
│   ├── observability/       # metrics, traces, Grafana proxy
│   └── evaluation/          # judge, benchmark, matrix, eval runner, profiles
├── front/
│   └── src/
│       ├── views/           # Chat, Metrics, Traces, Benchmark, Matrix, Settings
│       ├── components/      # MessageScore (async judge display)
│       ├── stores/          # chat.ts, judge.ts
│       └── api/client.ts
└── infra/
    ├── docker-compose.yml
    ├── docker-compose.dev.yml
    ├── docker-compose.prod.yml
    ├── litellm_config.yaml
    ├── prometheus.yml
    └── grafana/provisioning/
```

---

## Key design decisions

**Governance from metrics.** Model selection is driven by governance criteria, not performance alone. The score matrix accumulates from real production usage — not synthetic benchmarks.

**Local evaluation judge.** Scoring runs on Ollama — sovereign and usable in air-gapped or regulated environments (public sector, healthcare, finance). No response data sent to external APIs.

**Profile-driven routing.** Switching a governance profile at runtime updates which criteria are active and their weights. The routing layer reads the active profile from Redis at inference time and recommends the best-scoring model for that profile and use case.

**Shared schema layer.** All three microservices share `back/shared/src/shared/` for Pydantic schemas and config — single source of truth for data contracts.

**Judge traces filtered.** Evaluation calls to LiteLLM are excluded from the traces view so only user interactions appear.

**Dev/prod parity via compose overrides.** `make dev` mounts source volumes with `--reload`. `make prod` builds images and serves the front via nginx. Same base compose file, no drift.

---

## Roadmap

**Governance**
- [ ] Governance-driven routing — enforce model selection based on governance profile scores, block non-compliant models automatically
- [ ] Drift detection — automatic score trend alerts, quarantine on threshold breach
- [ ] Audit log export — consolidated compliance report (`/audit/export`) for CISO review
- [ ] Judge specialisation — assign different judge models per regulatory criterion
- [ ] Policy-as-code — define enforcement rules in YAML (block model if score < threshold)
- [ ] Global alert thresholds with visual dashboard indicators

**Infrastructure**
- [ ] asyncio.gather — parallelize Langfuse observation fetches
- [ ] Redis TTL cache — 30s on /metrics and /benchmark/results
- [ ] EvalAP integration — push traces to Etalab's evaluation platform
- [ ] prometheus-fastapi-instrumentator — expose microservice-level metrics, not just LiteLLM

---

## Relevant standards and resources

**Regulatory texts**
- [EU AI Act](https://artificialintelligenceact.eu/ai-act-explorer/) — Art. 5 (prohibited practices), Art. 9 (risk management), Art. 13 (transparency), Art. 14 (human oversight)
- [GDPR Art. 22](https://gdpr-info.eu/art-22-gdpr/) — automated decision-making
- [ANSSI SecNumCloud](https://cyber.gouv.fr/offre-de-service/solutions-certifiees-et-qualifiees/services-de-securite-evalue/solutions-en-cours-de-qualification/prestataires-secnumcloud/) — French sovereign cloud security reference
- [NIS2 Directive](https://digital-strategy.ec.europa.eu/en/policies/nis2-directive) — operational continuity for critical infrastructure

**Evaluation and benchmarking**
- [COMPL-AI](https://compl-ai.org) — AI Act compliance benchmarking framework (ETH Zurich)
- [LM Evaluation Harness](https://github.com/EleutherAI/lm-evaluation-harness) — standardized LLM evaluation by EleutherAI
- [OWASP LLM Top 10](https://owasp.org/www-project-top-10-for-large-language-model-applications/) — security risks for LLM applications
- [EU AI Act Compliance Checker](https://artificialintelligenceact.eu/assessment/eu-ai-act-compliance-checker/) — Future of Life Institute interactive tool

**LLM observability and evaluation landscape**

Several platforms address LLM observability from different angles — govllm is positioned differently on two axes: sovereign/on-premise deployment and governance-first scoring (regulatory criteria, not just performance metrics).

- [Langfuse](https://langfuse.com) — open-source tracing and evaluation, self-hostable. govllm uses Langfuse as its tracing layer.
- [Giskard](https://giskard.ai) — open-source LLM testing and red-teaming, EU-based. Strong on vulnerability detection pre-deployment.
- [Arize AI](https://arize.com) — production LLM observability and evaluation. Cloud-first, strong on agent tracing.
- [Fiddler AI](https://fiddler.ai) — enterprise ML + LLM monitoring with explainability and compliance focus. Targets regulated industries.
- [Arthur AI](https://arthur.ai) — ML and LLM monitoring with bias detection and governance. Enterprise, cloud.
- [LatticeFlow AI](https://latticeflow.ai) — AI compliance validation, focused on EU AI Act and defense. Closed, enterprise.
- [Holistic AI](https://holisticai.com) — AI governance and risk management platform. Audit-oriented, closed.

govllm's differentiator: fully local inference (no data leaves your infrastructure), governance criteria mapped to EU/French regulatory frameworks, and profile-driven routing based on production scores — not pre-deployment benchmarks.

**On AI ethics charters**

The past few years have seen a proliferation of AI ethics charters and responsible AI commitments — from national frameworks to sector-specific pledges. These documents play an important role in setting shared principles. govllm is designed to complement them: where charters articulate what should be done, govllm provides a technical layer to verify that it is actually being done, continuously, in production. Principles need observability to become practice.

**French public sector context**
- [DINUM Albert](https://www.numerique.gouv.fr/offre-accompagnement/expertise-albert-ia-etat/) — French government's sovereign LLM
- [EIG Program](https://eig.numerique.gouv.fr) — Entrepreneurs d'Intérêt Général
- [CNIL AI guidance](https://www.cnil.fr/fr/intelligence-artificielle) — French data protection authority on AI
- [AI Charters Portal for Public Administration](https://alliance.numerique.gouv.fr/ressources/portail-des-chartes-ia-dans-ladministration/) — Public repository of AI charters, guidelines, and governance frameworks used across French public administrations, designed to share best practices, promote ethical AI, and support adoption by public sector staff
- [Projet PANAME](https://www.cnil.fr/fr/projet-paname-participez-aux-tests-dun-outil-daudit-rgpd-des-modeles-dia) — CNIL's GDPR audit tool for AI models, currently in beta testing
---

## License

EUPL-1.2
