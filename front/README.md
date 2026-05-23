# govllm — frontend

Vue 3 + TypeScript + ECharts. Talks to three backend services via [src/api/client.ts](src/api/client.ts).

## Dev

```sh
pnpm install
pnpm dev        # http://localhost:5173
pnpm build
pnpm lint
```

## Views

### Chat
Real-time chat with any Ollama model. Streaming SSE. Smart routing bar (AUTO / MANUAL): in AUTO mode, the recommended model is fetched before each message based on the active governance profile + use case. Switching to a specific model puts the bar in MANUAL mode. Each response shows a governance score badge once the async judge evaluation completes.

### Model × Use Case Matrix
Heatmap: rows = use cases (general / summarization / translation / code / administrative_writing / analysis), columns = models. Each cell shows the rolling average score for that (model, use case) pair based on production traces. Hover for score detail, trend, and recent score pills. Lifecycle badges (test / validation / production / quarantine) per model. Side drawer: validate, quarantine, run SAS, run LMSYS SAS, full lifecycle timeline.

### Metrics
Latency percentiles (p50 / p95 / p99), error rate, and request count per model over a sliding window (1h / 6h / 24h / 7d). Line charts via ECharts. Useful to detect regressions after a model change.

### Traces
Table of production LLM interactions (judge evaluation traces filtered out). Columns: time, model, judge, latency, governance score. Filter by generator model or judge model. Pagination 20/page. Click a row to expand full input/output. `judge_model` is populated for traces generated after the evaluation service was updated to store it in Langfuse metadata.

### Benchmark
Multi-model comparison on the fixed prompt set (`docs/benchmark/prompts.json`). Bar chart: average score per model across all use cases and judge combinations. Source: `GET /benchmark/results`.

### Judge Arena
Four tabs:

| Tab | Purpose |
|---|---|
| **Run** | Submit a prompt (manual, auto-generate, or ground truth corpus) to N judges simultaneously. Each judge card shows per-criterion scores with tooltip (score + reason + flag). Incoherence badge if the judge contradicts itself (flag=true + low score + thin reason). |
| **Variance** | Inter-judge variance over time. Line chart: x=time, y=σ per criterion, tooltip=prompt preview. High variance = judges disagree = prompt is discriminating. |
| **Bias matrix** | Heatmap: judge family (row) × evaluated model (col). Cell = mean score. Highlights self-preference: does a judge score its own model family higher? |
| **Corpus** | Ground truth validity. Table: judge × criterion agreement (%). Click a cell for per-sub-question breakdown. Order sensitivity section (flip rate + Δ agreement across three orderings: original, reversed, permuted). Source: ground truth corpus of 49 annotated (prompt, response) pairs across 5 criteria. |

### Settings
Four tabs:

| Tab | Purpose |
|---|---|
| **Governance profiles** | Toggle criteria, adjust weights per profile. "Auto-assign from ground truth" fills the judge panel with the best judge per criterion (from ground truth validity data). |
| **Use cases** | Default profile, preferred model, language, score threshold, judge system prompt per use case. |
| **Judge** | Active judge model, arena judge panel (multi-select), system prompt, policy rules. |
| **Routing** | Strategy (best_score / progression / stability / strict) and global score threshold. |
