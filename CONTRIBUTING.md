# Contributing to govllm

Thanks for considering a contribution. This is a solo research project that grew into something usable beyond its original scope — contributions are welcome, but a few conventions keep the codebase (and the accompanying paper's reproducibility) intact.

---

## Setup

**Prerequisites:** Docker, Docker Compose, [uv](https://docs.astral.sh/uv/), [Ollama](https://ollama.com) models pulled locally.

```bash
git clone https://github.com/JehanneDussert/govllm
cd govllm

cp infra/.env.example infra/.env
# fill in Langfuse keys

make dev            # hot reload — back/evaluation, back/shared, back/llm-gateway,
                     # back/observability are bind-mounted, code changes apply immediately
make pull-models     # pulls the 4 default generators (phi4-mini, mistral:7b, gemma3:4b, qwen3:1.7b) + the default judge (ministral-3:8b)
```

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| Gateway | http://localhost:8001/docs |
| Observability | http://localhost:8002/docs |
| Evaluation | http://localhost:8003/docs |

`make down` stops the stack, `make logs` / `make ps` for status, `make reset` for a clean rebuild.

**Note on hot reload:** with `make dev`, editing any `.py` file under `back/evaluation/` or `back/shared/` triggers uvicorn's `--reload`, which gracefully restarts the service — including waiting for any in-flight request to complete first. If a long-running job (e.g. a ground truth run hitting Ollama) is active against that service when you save a file, the whole service will stall until that request finishes. Avoid editing backend Python files while a ground truth run or benchmark is in progress; frontend and documentation changes are unaffected.

**Note for Windows hosts — `SSLKEYLOGFILE`:** the services run in Linux containers, so a local `back/.venv` is only needed for editors and host-side scripts. If the `SSLKEYLOGFILE` environment variable is set (some network-monitoring / TLS-inspection tools set it, often to a device or named pipe; for example, the HTTPS inspection of **Norton 360**, and of the **Avast / AVG** suites that share its engine, injects a hook DLL into some processes and sets it to `\\.\nllMonFltProxy\…` or `\\.\aswMonFltProxy\…`, so it may only appear in shells started from certain apps, such as an IDE extension, and not in your own terminal), Python builds that lack OpenSSL's `applink` shim crash on the first TLS context with `OPENSSL_Uplink … no OPENSSL_Applink`. That includes the "standalone" CPython that `uv` downloads by default. In practice it shows up as `import deepeval` or any `httpx`/`urllib` HTTPS-capable client failing in the host venv. Fix: build the venv on a python.org or Microsoft Store Python 3.12, which ships `applink`, then sync from the lock:
```bash
uv venv --python <path-to-python.org-or-Store-python3.12> back/.venv
cd back && uv sync --frozen --all-packages
```
Alternatively, unset `SSLKEYLOGFILE` for your shell. The containers are not affected.

---

## Monorepo structure

Three independent FastAPI microservices sharing one Pydantic/config layer, managed as a [uv workspace](https://docs.astral.sh/uv/concepts/workspaces/) (`back/pyproject.toml` lists the members):

```
back/
├── shared/          # Pydantic schemas + config — single source of truth for data contracts
├── llm-gateway/      # :8001 — chat, streaming, governance system-prompt injection
├── observability/    # :8002 — metrics, traces (read-only)
└── evaluation/        # :8003 — judge, benchmark, matrix, arena, lifecycle, ground truth
```

`back/shared/src/shared/` is imported by all three services as a workspace package (`shared = { workspace = true }` in each service's `pyproject.toml`). Any logic shared across microservices belongs there — never duplicated.

Frontend is a single Vue 3 + TypeScript app under `front/`, calling all three services directly (`front/src/api/client.ts`).

---

## Development conventions

These are enforced in code review, not by CI (there is currently no CI pipeline in this repo):

- **One concern per change, diff before writing.** Don't bundle unrelated fixes into one PR.
- **`shared/` is the source of truth** for anything used by more than one microservice — never duplicate a schema or config helper across services.
- **No `print()` in backend code** — use the standard `logging` module. (Standalone scripts under `back/evaluation/scripts/` and top-level `scripts/` are the exception — they're operational tools, not library code, and use `print()` freely.)
- **Strict Pydantic schemas** — avoid free-form `dict` payloads where a typed schema is possible.
- **`make lint` / `make format`** before submitting — runs `ruff` on `back/` and `eslint`/prettier-equivalent on `front/`.
- **Keep `back/README.md`, `front/README.md`, and the root `README.md` in sync** with any new endpoint, view, or feature added in the same change.

---

## Running the evaluation service tests

Unit tests run inside the evaluation container: `docker exec -w /app evaluation python -m pytest tests -q`. The integration tests in `back/evaluation/tests/integration/` use the real PostgreSQL and Redis with a simulated judge (no LLM call); they only run against a separate schema and Redis database, and are skipped otherwise. To run everything without touching the service's data:

```bash
sh back/evaluation/tests/integration/run.sh
```

It starts a throwaway container from the evaluation image with `GOVLLM_DB_SCHEMA=govllm_test` and `REDIS_URL=redis://redis:6379/15`.

## Running the ground truth tests

The ground truth corpus (49 annotated cases across 5 regulatory criteria) is the closest thing this project has to a validity test suite — it measures whether judge models actually detect the violations they're supposed to, not just whether they're internally consistent.

```bash
make gt-seed          # (re)creates the corpus tables and seeds all 49 cases from docs/ground_truth/corpus.json
                      # destructive: drops existing results and regenerates case ids — fresh setups only
make gt-run           # runs the corpus against the configured judges, original question order
make gt-log           # tails the run log
make gt-status         # lists active runs
make gt-summary        # prints the aggregate summary block from the last run
```

See [docs/ground_truth/README.md](docs/ground_truth/README.md) for the full corpus format, the checklist sub-question methodology, and reproducibility details for the three question orderings (original / reversed / permuted) used in the paper.

**Ollama is single-threaded** — a full run against all 49 cases takes on the order of tens of minutes per judge model. Don't run `gt-run` and expect an instant result; check `make gt-status` before starting a second one.

---

## Adding a new judge model

Two separate steps — skipping the first is a documented silent-failure trap:

1. **Register the model with LiteLLM.** `ollama pull` alone is not enough — LiteLLM only knows about models explicitly listed in `infra/litellm_config.yaml` (`model_name` + `litellm_params.model: ollama/<tag>`, `api_base: http://ollama:11434`). Without this entry, calls through the judge pipeline fail even though `ollama run <model>` works fine directly. Restart the `litellm` container after editing.
2. **Check whether the model needs a call-quirk override.** Some models — particularly "thinking" models with a hidden or unmanaged chain-of-thought — exhaust the default token budget (2048 for production judging, 400-500 for ground truth/few-shot) before ever reaching their JSON answer, producing an empty or truncated response that looks like a parsing bug but isn't. Symptom: `raw` in the logs is either empty or an unclosed `<think>...` block on every attempt, all retries, every case — not a transient failure.

   All model-specific call quirks (extended token budgets, thinking-mode toggles, extended context windows) live in **one file**: `back/evaluation/model_quirks.json`. It's read at import time by `services/judge.py`, `services/groundtruth.py`, and `scripts/run_fewshot_groundtruth.py` — three independent call sites (production judging, ground truth checklist, few-shot calibration) that each make their own LiteLLM request, so a model added to `extended_token_models` there gets the same treatment everywhere automatically. Don't hardcode a model-specific `max_tokens`/`num_ctx` value inline in any of those three files — add it to `model_quirks.json` instead.

   To diagnose: test the model directly against LiteLLM (bypassing the app) with a realistic-length prompt and a generous `max_tokens` (4000+). If `finish_reason: "stop"` and valid JSON come back where the default budget failed, add the model to `extended_token_models` in `model_quirks.json` — don't guess at a fix without reproducing the failure first.

## Proposing a new governance profile or criterion

1. Pick the regulatory anchor(s) the criterion maps to (AI Act article, GDPR article, ANSSI guideline, NIS2 article, etc.) — every criterion in this project traces back to a specific text, not a vague principle.
2. Write it as a `JudgeCriterion` in `back/evaluation/services/judge_config.py` (`ALL_CRITERIA` list) — `id`, `label`, `description`, `weight`, `tags`. Follow the existing entries for tone and format.
3. If it belongs to a new governance profile, add a `GovernanceProfile` to `BUILT_IN_PROFILES` in the same file, with a `criteria_config` mapping each included criterion to its weight.
4. If the criterion should be validated against ground truth (recommended for anything non-trivial), write 3-4 binary sub-questions in the same style as the existing criteria — see [docs/ground_truth/criteria.md](docs/ground_truth/criteria.md) for the exact format (each sub-question states whether a "yes" means compliant or violation), and add annotated cases to `docs/ground_truth/corpus.json`.
5. New criteria should default to `enabled=False` in `ALL_CRITERIA` — they only activate through a profile that explicitly turns them on.

---

## Research context

This project is accompanied by a preprint: **"Who Judges the Judges? Governance from Metrics: A Runtime Framework for Continuous LLM Compliance Monitoring"** — [arXiv:2605.24737](https://arxiv.org/abs/2605.24737). The ground truth corpus and the empirical findings (position bias, panel specialization, family bias) referenced throughout the codebase's comments come from that paper. If you're proposing a change to the evaluation methodology itself (scoring logic, checklist format, panel dispatch), it's worth reading the paper first — some design choices that look arbitrary in the code are direct consequences of findings documented there.

---

## License

EUPL-1.2 — see [LICENSE](LICENSE).
