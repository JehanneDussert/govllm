#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
#
# Run a re-run script against the isolated stack (up.sh first). Results go to OUT (a
# directory outside the repository); the checkout is mounted read-only.
#
#     OUT=/c/Users/jehan/Documents/govllm-reruns/2026-10-27 bash scripts/isolated_stack/run.sh benchmark \
#         --only-evaluate --models ollama/phi4-mini ... --judges ollama/phi4-mini ... --timeout 900
#     OUT=... bash scripts/isolated_stack/run.sh fewshot --judges ollama/phi4-mini ...
#
# Every run requires num_thread 10 (--require-num-thread 10) and writes, next to its results,
# run_manifest.txt: images, Ollama version, model parameters, and the thread counts the
# Ollama runners reported while the run was going.
set -euo pipefail
export MSYS_NO_PATHCONV=1
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
NET=govllm-iso
KIND="${1:?usage: run.sh benchmark|fewshot [script args]}"; shift
OUT="${OUT:?set OUT to a results directory outside the repository}"
host() { cygpath -w "$1" 2>/dev/null || echo "$1"; }
case "$KIND" in
  benchmark) SCRIPT=scripts/run_full_benchmark.py; DEST=/out/benchmark ;;
  fewshot)   SCRIPT=scripts/run_fewshot_groundtruth.py; DEST=/out/fewshot ;;
  *) echo "unknown kind $KIND" >&2; exit 1 ;;
esac
mkdir -p "$OUT"
# Fresh Ollama for every run: a warm prompt cache can change answers (README.md)
docker restart iso-ollama >/dev/null
until docker exec iso-ollama ollama list >/dev/null 2>&1; do sleep 1; done
START="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

docker run --rm --name "iso-runner-$KIND" --network "$NET" --memory 512m \
  -e GOVLLM_EVAL_URL=http://iso-eval:8003 -e GOVLLM_GATEWAY_URL=http://unreachable.invalid \
  -e GOVLLM_LITELLM_URL=http://iso-litellm:4000 -e GOVLLM_LITELLM_KEY=sk-iso -e PYTHONUNBUFFERED=1 \
  -v "$(host "$ROOT"):/repo:ro" -v "$(host "$OUT"):/out" -v infra_evaluation_venv:/venv:ro -w /repo \
  infra-evaluation /venv/bin/python "$SCRIPT" --results-dir "$DEST" --require-num-thread 10 "$@" \
  2>&1 | tee -a "$OUT/$KIND.log"

{
  echo "run: $KIND $*"
  echo "start: $START  end: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "code: $(git -C "$(host "$ROOT")" rev-parse HEAD)$(git -C "$(host "$ROOT")" diff --quiet || echo ' (+ uncommitted changes)')"
  for c in iso-ollama iso-litellm iso-eval; do echo "image $c: $(docker inspect "$c" --format '{{.Config.Image}}')"; done
  docker exec iso-eval python -c "
import json, urllib.request as u
s = json.load(u.urlopen('http://localhost:8003/config/inference-stack', timeout=30))
print('ollama_version:', s['ollama_version'])
for m in sorted(s['model_digests']): print('model', m, s['model_digests'][m], s['model_params'].get(m))
"
  echo "ollama runner thread counts during the run:"
  docker logs --since "$START" iso-ollama 2>&1 | grep -oE 'n_threads = [0-9]+|NumThreads:[0-9]+' | sort | uniq -c
} >> "$OUT/run_manifest.txt"
echo "manifest: $OUT/run_manifest.txt"
