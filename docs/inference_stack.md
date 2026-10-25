# Inference stack: pinned versions, model digests, backup and restore

Judge verdicts depend on the exact model files **and** on the inference server version. In October 2026, we re-ran the May 2026 ground-truth evaluations of phi4-mini and gemma3:4b with:
- byte-identical prompts;
- the same model files (downloaded once, on 2026-05-14);
- the same parsing rule;
- temperature 0.

The only change was a newer Ollama release, and 7 and 17 of the 49 cases changed verdict. Repeated calls on a fixed stack are deterministic for 7 of the 8 judges (`scripts/test_retest.py`, `docs/ground_truth/analysis/test_retest.json`). Hence the following rules:
- the two images below are pinned by digest;
- every judge call records the Ollama version and the model digest;
- the model files are backed up outside Docker.

## Pinned images (`infra/docker-compose.yml`)

| Service | Version | Image digest |
|---|---|---|
| Ollama | 0.32.15 (image built 2026-08-20, running since 2026-08-22) | `ollama/ollama@sha256:57d60e686821ea81a7748a3ec8141308c8b8f95b27105713954abf7a6529e700` |
| LiteLLM | 1.82.1 (image built 2026-03-10) | `ghcr.io/berriai/litellm@sha256:d2bc536b3459e58f62bfc8f286a9c2882038b14ce7309c3991845bebc2e3c4fa` |

These are the images of the test-retest run (2026-10-23/25) and of every run since 2026-08-22. A run on any other version is a different experiment: change the pin only together with a full re-run.

## Judge models

Ollama model ID = sha256 of the manifest (first 12 characters in `ollama list`). These files are the ones every reported run used: none has been downloaded again since its first pull.

| Model (LiteLLM id) | Manifest sha256 | First pulled |
|---|---|---|
| `ollama/phi4-mini` | `78fad5d182a7c33065e153a5f8ba210754207ba9d91973f57dffa7f487363753` | 2026-05-14 |
| `ollama/qwen3:1.7b` | `8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7` | 2026-05-14 |
| `ollama/gemma3:4b` | `a2af6cc3eb7fa8be8504abaf9b04e88f17a119ec3f04a3addf55f92841195f5a` | 2026-05-14 |
| `ollama/mistral:7b` | `6577803aa9a036369e481d648a2baebb381ebc6e897f2bb9a766a2aa7bfbc1cf` | 2026-05-14 |
| `ollama/gemma4:e4b` | `c6eb396dbd5992bbe3f5cdb947e8bbc0ee413d7c17e2beaae69f5d569cf982eb` | 2026-08-22 |
| `ollama/ministral-3:8b` | `1922accd5827ebe6829e536369195db25eaf664528dc66206d646ea3bb386b71` | 2026-08-22 |
| `ollama/granite4` | `4235724a127c0f86dcc0247d67c20148705d6dd2319164014d92f71d607f4773` | 2026-08-22 |
| `ollama/hf.co/LiquidAI/LFM2.5-1.2B-Thinking-GGUF:latest` | `c1f3e0033aa77e2c30b350dd9f7d11aed34aaad509b8b0f2cf6b12d97545f6df` | 2026-08-22 |

**Do not `ollama pull` these models again.** The `gemma3:4b` tag has changed on the Ollama library since May (now manifest `68ceab7e…`, with the vision projector split into a separate layer), so a new pull would replace the evaluated model. `phi4-mini`, `qwen3:1.7b` and `mistral:7b` still match the library on 2026-10-25, but nothing guarantees they will stay that way.

## What each run records

- **Ground truth** (`groundtruth_results`): `model_digest` and `ollama_version` per call.
- **Benchmark** (`scripts/run_full_benchmark.py`, `docs/benchmark/results/*.json`):
  - an `inference_stack` field per entry (Ollama version, judge and generator digests);
  - `inference_stacks` at file level.
- **Few-shot** (`scripts/run_fewshot_groundtruth.py`, `*_fewshot.json`): same fields.
- Both scripts read `GET /config/inference-stack?models=…` on the evaluation service. They stop rather than write two stacks into one file, both when a partial file already holds another stack and when the stack changes during a run.
- Result files written before 2026-10-25 carry none of these fields. Their stack follows from the date:
  - before 2026-08-22: an earlier Ollama release, not recorded;
  - from 2026-08-22: Ollama 0.32.15;
  - model files: as in the table above throughout.

## Backup of the model files

The manifests and blobs of the 8 judges are copied out of the `ollama` container with `docker cp` (no download, no new container). Every blob's sha256 is checked against its file name.

```bash
bash scripts/backup_ollama_models.sh /path/outside/the/repo/ollama-models
# -> manifests/, blobs/, models.json, SHA256SUMS, backup.log
# stops if the Docker VM has less than 300 MB available; re-running skips verified blobs
```

`models.json` lists, for each model, its manifest path, manifest sha256 and blob digests. `SHA256SUMS` covers every file. The backup is about 30 GB and stays outside the repository; keep an offline copy.

## Restore

1. Check the backup: `cd /path/to/ollama-models && sha256sum -c SHA256SUMS`.
2. Copy the files back into the Ollama volume, without overwriting anything already present:
   ```bash
   cd /path/to/ollama-models
   for f in blobs/*; do docker cp "$f" ollama:/root/.ollama/models/blobs/; done
   docker exec ollama mkdir -p /root/.ollama/models/manifests
   docker cp manifests/. ollama:/root/.ollama/models/manifests/
   ```
3. Check that `docker exec ollama ollama list` shows the IDs of the table above, and that `GET /config/inference-stack` returns the same digests and `ollama_version: 0.32.15`.
4. Never use `ollama pull` to "repair" a model: it fetches the current tag, not the evaluated file.
