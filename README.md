# govllm

> How do you justify a model choice six months after go-live?

Self-hosted LLM governance monitoring for regulated environments. Continuous scoring against EU AI Act, GDPR, and ANSSI (French National Agency for the Security of Information Systems) — not a one-shot benchmark.

Built out of a question I couldn't find a good answer to, working on LLM deployment in the french public sector. Directly applicable to AI Act Article 9 requirements (ongoing risk management) and NIS2 operational continuity constraints.

[![License: MIT](https://img.shields.io/badge/License-MIT-00d4b8.svg)](LICENSE)
[![Stack](https://img.shields.io/badge/stack-FastAPI%20%7C%20Vue%203%20%7C%20Ollama-3a3a3a)](https://github.com/JehanneDussert/govllm)

![govllm demo](docs/screenshots/govllm-demo.gif)

---

## What it does

govllm scores LLM outputs continuously against configurable governance profiles. Each response is evaluated by a local LLM-as-a-judge across criteria mapped to regulatory frameworks. The best-performing model per use case is selected automatically — based on your governance criteria, not raw performance metrics.

```
Request → Governance profile → LLM-as-a-judge scoring → Dynamic routing → Model A / B / C
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
│         │                                │
│         └──── Redis pub/sub ◄────────────┘
│
├──► observability :8002 ──► Prometheus / Grafana / Langfuse
│
└──► evaluation :8003 ──► Local judge (Ollama) ──► A/B · Matrix · Score
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

cp .env.example .env
# Fill in Langfuse keys

docker compose -f infra/docker-compose.yml up -d

make pull-models  # downloads qwen2.5:1.5b, gemma3:1b, llama3.2:3b, deepseek-r1:1.5b
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

Profiles are applied at runtime — switching a profile updates which criteria are active and their weights, without restarting any service.

---

## Judge criteria

The evaluation layer runs a local LLM-as-a-judge after each response. All criteria are configurable from the UI; custom criteria can be added.

| Criterion | Regulatory anchor | Default |
|---|---|---|
| Relevance | Quality baseline | ✅ |
| Conciseness | Quality baseline | ✅ |
| Factual reliability | AI Act | ✅ |
| Prompt injection | OWASP LLM01, ANSSI | ✅ |
| Data leakage | OWASP LLM02, ANSSI | ✅ |
| Non-manipulation | AI Act Art. 5 | — |
| Human oversight | AI Act Art. 14 | — |
| Explicability | AI Act Art. 13 | — |
| Transparency | AI Act | — |
| Data privacy | GDPR | — |
| Output traceability | GDPR Art. 22, AI Act | — |
| Accessibility | RGAA | — |
| Robustness | ANSSI | — |
| Contextual safety | AI Act high-risk | — |

The judge model runs locally (`ollama/gemma3:1b` by default). Evaluation calls are filtered from the traces view so only user interactions appear.

---

## Model × use case matrix

Scores accumulate per use case in Redis. The matrix view shows which model performs best per task under the active governance profile:

```
                    qwen2.5:1.5b   llama3.2:3b
Summary                 0.84           0.71
Translation             0.79           0.88
Code                    0.72           0.85
Administrative writing  0.88           0.74
```

→ Route translation and code to llama3.2, summary and admin writing to qwen2.5.

---

## A/B testing

Send traffic to two models, then compare:

```bash
curl http://localhost:8003/benchmark/results
```

```json
{
  "model_a": { "model": "ollama/qwen2.5:1.5b", "sample_size": 12, "avg_latency_ms": 4.2, "avg_eval_score": 0.81 },
  "model_b": { "model": "ollama/llama3.2:3b",  "sample_size": 9,  "avg_latency_ms": 8.7, "avg_eval_score": 0.76 },
  "winner": "ollama/qwen2.5:1.5b"
}
```

Winner is determined by eval score when available, latency otherwise.

---

## Stack

| Layer | Technology |
|---|---|
| Inference | Ollama — qwen2.5:1.5b, gemma3:1b, llama3.2:3b, deepseek-r1:1.5b |
| Proxy | LiteLLM |
| Backend | FastAPI + Python 3.11 |
| Tracing | Langfuse v2 |
| Metrics | Prometheus + Grafana |
| Event bus | Redis |
| Reverse proxy | Caddy |
| Frontend | Vue 3 + TypeScript + ECharts |
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
GET /grafana/dashboards    # Grafana dashboard links
```

### evaluation — :8003
```
GET  /benchmark/results?limit=50   # Benchmark between models
GET  /matrix                       # use case × model score matrix
GET  /config/judge                 # judge configuration
PUT  /config/judge                 # update judge configuration
POST /eval/score                   # trigger async evaluation (202 immediately)
GET  /eval/result/{trace_id}       # poll for evaluation result
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
│   └── evaluation/          # judge, benchmark, matrix, eval runner
├── front/
│   └── src/
│       ├── views/           # Chat, Metrics, Traces, Benchmark, Matrix, Settings
│       ├── components/      # MessageScore (async judge display)
│       ├── stores/          # chat.ts, judge.ts
│       └── api/client.ts
└── infra/
    ├── docker-compose.yml
    ├── litellm_config.yaml
    ├── prometheus.yml
    └── caddy/Caddyfile
```

---

## Key design decisions

**Governance from metrics.** The observability layer translates raw Prometheus metrics into structured governance signals. Model selection is driven by governance criteria, not performance alone.

**Local evaluation judge.** Quality scoring runs on Ollama — sovereign and usable in air-gapped or regulated environments. No response data sent to external APIs.

**Profile-driven routing.** Switching a governance profile at runtime updates which criteria are active and their weights. The routing layer reads the active profile from Redis at inference time.

**Shared schema layer.** All three microservices share `back/shared/src/shared/` for Pydantic schemas and config, ensuring type consistency across service boundaries.

**Judge traces filtered.** Evaluation calls to LiteLLM are excluded from the traces view so only user interactions appear.

---

## Roadmap

**Governance**
- [ ] Smart routing — auto-select model based on use case × criterion weight trajectory, not snapshot score
- [ ] Drift detection — automatic quarantine on score drop, synthetic retests to diagnose cause
- [ ] Audit log — consolidated compliance view (`/audit`)
- [ ] Judge specialisation — assign different judge models per regulatory criterion

**Infrastructure**
- [ ] asyncio.gather — parallelize observation fetches
- [ ] Redis cache — 30s TTL on /metrics and /benchmark/results
- [ ] EvalAP integration — push traces to Etalab's evaluation platform
- [ ] Regulatory benchmark alignment — coverage mapping against [COMPL-AI](https://compl-ai.org) for AI Act compliance assessment

---

## Relevant regulations

- EU AI Act (Art. 5, 9, 13, 14) — transparency, risk management, human oversight
- GDPR (Art. 22) — automated decision-making, data minimisation
- ANSSI guidelines — security hardening, incident traceability
- OWASP LLM Top 10 — prompt injection, data leakage
- RGAA / FALC — accessibility and inclusive language

---

## License

MIT
