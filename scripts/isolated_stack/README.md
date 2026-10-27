# Isolated stack for re-runs

Re-runs the benchmark and the few-shot experiment on the **pinned inference stack** (docs/inference_stack.md) **without touching the deployment**: no write to its database, its Redis or its judge configuration. The results go to files only.

```bash
bash scripts/isolated_stack/up.sh
OUT=/c/Users/jehan/Documents/govllm-reruns/<date> bash scripts/isolated_stack/run.sh benchmark \
    --only-evaluate --models ollama/phi4-mini ollama/mistral:7b ollama/gemma3:4b ollama/qwen3:1.7b \
    --judges ollama/phi4-mini ollama/mistral:7b ollama/gemma3:4b ollama/qwen3:1.7b --timeout 900
OUT=... bash scripts/isolated_stack/run.sh fewshot --judges ollama/phi4-mini ollama/gemma3:4b ollama/qwen3:1.7b ollama/mistral:7b
bash scripts/isolated_stack/down.sh
```

## What `up.sh` starts

All the containers sit on a Docker network created with `--internal`: no route to the deployment's containers or outside. Each one has a memory cap.

| Container | Content |
|---|---|
| `iso-ollama` | Ollama, image **pinned** in `infra/docker-compose.yml`. The deployment's model files are mounted **read-only**: no download, same digests. |
| `iso-litellm` | LiteLLM, pinned image. `infra/litellm_config.yaml` points to `iso-ollama`, with the same `num_ctx` and **`num_thread: 10`**, and without the Langfuse/Prometheus callbacks. |
| `iso-pg` | Throwaway PostgreSQL (tmpfs), seeded with a copy of `govllm.groundtruth_cases`, so the case ids are those of the deployment. |
| `iso-redis` | Throwaway Redis, seeded with a copy of `config:judge`. The benchmark switches judge, use case and profile **here**, not in production. |
| `iso-langfuse` | A stub answering 200 to everything (`langfuse_stub.py`): the evaluation service traces each call. |
| `iso-eval` | The evaluation service, run from this checkout (read-only). |

The deployment is only **read**, once, at start: `pg_dump` of one table and `redis GET` of one key.

## What every run records

- **Per entry or call** (`inference_stack`): the Ollama version, the model digest, and the `num_thread` / `num_ctx` that LiteLLM applies (`GET /config/inference-stack`, read from LiteLLM's `/model/info`).
- **Refusals:** a run stops if a judge's `num_thread` is not 10 (`--require-num-thread 10`), and if the stack changes during the run.
- **`run_manifest.txt`** next to the results: images, code commit, digests and parameters, and the thread counts the Ollama runners actually reported during the run (`n_threads = 10`).

## Checks (2026-10-27)

- **Few-shot:** granite4 on 4 prompt-injection cases. Answers and reasons are identical to its August few-shot file (same Ollama version, 10 threads).
- **Benchmark:** granite4 judging phi4-mini.
  - On a cold call, scores and reasons are identical to the August file (`gen_02`, `gen_05`).
  - **The same prompt sent again right after can give another answer**, most likely because of Ollama's prompt cache.
  - So restart `iso-ollama` (`docker restart iso-ollama`) before each run, and never repeat a prompt within a run. The scripts process the entries in the same order as the original runs.
