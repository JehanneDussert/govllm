# govllm — backend

Three independent FastAPI microservices sharing `back/shared/src/shared/` (Pydantic schemas + config).

## Services

| Service | Port | Role |
|---|---|---|
| `llm-gateway` | 8001 | Chat endpoint, governance system prompt injection, Redis publisher |
| `observability` | 8002 | Metrics, traces, Grafana proxy — read-only on Langfuse |
| `evaluation` | 8003 | Judge, benchmark, matrix, arena, lifecycle, ground truth |

Swagger docs at `http://localhost:{port}/docs` when running.

## API reference

### llm-gateway — :8001

```
POST /chat          # chat completion — streaming SSE or non-streaming JSON
GET  /health
```

### observability — :8002

```
GET /metrics?window=24h    # latency p50/p95/p99, error rate, request count per model
GET /traces?limit=200      # production traces with eval scores and judge model (judge traces filtered)
                           # query params: model=ollama/phi4-mini
```

### evaluation — :8003

**Benchmark & matrix**
```
GET  /benchmark/results           # multi-model benchmark
GET  /matrix                      # use case × model score matrix (Redis rolling avg)
GET  /matrix/routing              # recommended model for active profile + use case
```

**Judge configuration**
```
GET  /config/models/available     # list available Ollama models
GET  /config/judge                # full config (criteria, profiles, use cases, panels, routing)
PUT  /config/judge                # update judge configuration
POST /config/judge/profile/{id}   # activate a governance profile
POST /config/judge/use-case/{id}  # activate a use case (auto-applies its default profile)
```

**Evaluation**
```
POST /eval/score                  # trigger async evaluation (returns 202)
GET  /eval/result/{trace_id}      # poll for evaluation result
```

**Arena**
```
POST /arena/run                   # synchronous: N judges on one prompt → scores per judge
POST /arena/run/stream            # SSE variant — judge cards appear progressively
GET  /arena/sessions              # history of arena sessions
GET  /arena/variance              # inter-judge σ over time
GET  /arena/bias-matrix           # judge family × evaluated model heatmap (SPR)
GET  /arena/incoherence           # intra-judge structural contradiction rate
GET  /arena/variance/export       # CSV export
GET  /arena/bias-matrix/export    # CSV export
POST /arena/vote                  # user vote on an Arena session
```

**Lifecycle**
```
GET  /lifecycle/status             # current zone for every configured model
POST /lifecycle/validate/{model}   # human validation → production
POST /lifecycle/quarantine/{model} # manual quarantine
POST /lifecycle/sas                # SAS qualification — score vs threshold → zone decision
POST /lifecycle/sas/lmsys          # LMSYS-style SAS on governance corpus
GET  /lifecycle/history            # full transition timeline
```

**Ground truth**
```
POST /groundtruth/corpus                   # add a case to the validity corpus
GET  /groundtruth/corpus                   # list corpus cases (?criterion=X)
POST /groundtruth/run/{case_id}            # run N judges → per-sub-question agreement
GET  /groundtruth/results/{case_id}        # stored results (?question_order=original)
GET  /groundtruth/validity                 # agreement rates by judge × criterion × sub-question
GET  /groundtruth/validity/best-judges     # best judge per criterion (≥3 cases)
GET  /groundtruth/order-sensitivity        # flip rate + Δ agreement per judge × criterion
GET  /groundtruth/incoherence              # cases available for manual validation
PATCH /groundtruth/results/{id}/validate  # manually validate an incoherence flag
```

## Shared layer

`back/shared/src/shared/` — single source of truth for data contracts:

| File | Content |
|---|---|
| `config.py` | Settings per service (pydantic-settings, env vars) |
| `langfuse.py` | `LangfuseClient` — traces + scores. `push_score` only in evaluation (observability is read-only) |
| `schemas/judge.py` | `JudgeConfig`, `JudgeCriterion`, `GovernanceProfile`, `JudgePanel` |
| `schemas/traces.py` | `TraceItem`, `TracesResponse` |
| `schemas/evaluation.py` | `EvalResult`, `CriterionScore` |
| `schemas/chat.py` | `ChatRequest`, `ChatResponse` |

## Key files

```
back/
├── shared/src/shared/
│   ├── config.py
│   ├── langfuse.py
│   └── schemas/
├── llm-gateway/
│   ├── routers/chat.py            # governance system prompt injection per request
│   └── services/litellm_client.py
├── observability/
│   ├── routers/traces.py          # judge trace filtering, model detection
│   └── services/langfuse_client.py
└── evaluation/
    ├── jobs/eval_runner.py        # async evaluation orchestrator (panel dispatch, dual-write Redis + PostgreSQL)
    ├── services/
    │   ├── judge.py               # _build_judge_prompt, _call_judge, _extract_json
    │   ├── judge_config.py        # built-in profiles + DEFAULT_CONFIG
    │   ├── arena.py               # run_arena, _compute_sigma, _detect_family
    │   ├── lifecycle.py           # get_status, set_zone, run_sas
    │   └── groundtruth.py         # checklist evaluation, agreement computation
    └── scripts/
        ├── groundtruth.py         # unified entry point: seed / run / extend / compare
        └── fetch_lmsys.py         # download LMSYS regulatory subset (requires HF_TOKEN)
```
