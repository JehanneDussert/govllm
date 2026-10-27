#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
#
# Start an ISOLATED copy of the judging stack for re-runs (README.md in this directory):
# nothing it does can write to the deployment.
#
#   iso-ollama    Ollama, image pinned in infra/docker-compose.yml, the deployment's model files
#                 mounted READ-ONLY (no download)
#   iso-litellm   LiteLLM, pinned image, infra/litellm_config.yaml pointed at iso-ollama
#                 (same num_ctx / num_thread), no callbacks
#   iso-pg        throwaway PostgreSQL (tmpfs), seeded with a copy of govllm.groundtruth_cases
#   iso-redis     throwaway Redis, seeded with a copy of the deployment's config:judge
#   iso-langfuse  stub answering 200 to every request (the evaluation service traces calls)
#   iso-eval      evaluation service from this checkout, pointed at the containers above
#
# All on a network created with --internal: no route to the deployment's containers or
# outside. Each container has a memory cap. The deployment is only READ, twice, at start
# (pg_dump of one table, redis GET of one key).
#
#     bash scripts/isolated_stack/up.sh
set -euo pipefail
export MSYS_NO_PATHCONV=1
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$ROOT/scripts/isolated_stack"
NET=govllm-iso
STATE="$HERE/.state"   # generated config, git-ignored
host() { cygpath -w "$1" 2>/dev/null || echo "$1"; }
mkdir -p "$STATE"

if docker network inspect "$NET" >/dev/null 2>&1; then
  echo "$NET already exists: run down.sh first" >&2; exit 1
fi

OLLAMA_IMAGE="$(grep -oE 'ollama/ollama@sha256:[0-9a-f]{64}' "$ROOT/infra/docker-compose.yml")"
LITELLM_IMAGE="$(grep -oE 'ghcr.io/berriai/litellm@sha256:[0-9a-f]{64}' "$ROOT/infra/docker-compose.yml")"
[ -n "$OLLAMA_IMAGE" ] && [ -n "$LITELLM_IMAGE" ] || { echo "pinned images not found in docker-compose.yml" >&2; exit 1; }

# LiteLLM config: the deployment's model list and parameters, pointed at iso-ollama, no callbacks
python - "$(host "$ROOT/infra/litellm_config.yaml")" "$(host "$STATE/litellm.yaml")" <<'EOF'
import re, sys
src, dst = sys.argv[1], sys.argv[2]
t = open(src, encoding="utf-8").read()
t = t.replace("http://ollama:11434", "http://iso-ollama:11434")
t = re.sub(r"\nlitellm_settings:.*?(?=\n\S|\Z)", "", t, flags=re.S)
t = re.sub(r"\ngeneral_settings:.*", "\ngeneral_settings:\n  master_key: sk-iso\n", t, flags=re.S)
assert "iso-ollama" in t and "ollama:11434" not in t.replace("iso-ollama:11434", "")
open(dst, "w", encoding="utf-8").write(t)
EOF

docker network create --internal "$NET" >/dev/null

docker run -d --name iso-ollama --network "$NET" --memory 12g \
  -v infra_ollama_data:/ollama-data:ro -e OLLAMA_MODELS=/ollama-data/models "$OLLAMA_IMAGE" >/dev/null
docker run -d --name iso-litellm --network "$NET" --memory 1g -e LITELLM_LOCAL_MODEL_COST_MAP=True \
  -v "$(host "$STATE/litellm.yaml"):/app/config.yaml:ro" "$LITELLM_IMAGE" --config /app/config.yaml --port 4000 >/dev/null
docker run -d --name iso-pg --network "$NET" --memory 512m -e POSTGRES_HOST_AUTH_METHOD=trust \
  -e POSTGRES_DB=govllm_iso --tmpfs /var/lib/postgresql/data postgres:16-alpine >/dev/null
docker run -d --name iso-redis --network "$NET" --memory 512m redis:7-alpine redis-server --save "" --appendonly no >/dev/null
docker run -d --name iso-langfuse --network "$NET" --memory 128m -v "$(host "$HERE"):/stub:ro" \
  infra-evaluation python /stub/langfuse_stub.py >/dev/null

until docker exec iso-pg pg_isready -q -h 127.0.0.1 -U postgres 2>/dev/null; do sleep 1; done
# Seed: the ground-truth cases (same ids as the deployment) and the judge configuration
docker exec iso-pg psql -U postgres -d govllm_iso -q -c "CREATE SCHEMA govllm"
# Same default as the deployment (ALTER ROLE langfuse ... SET search_path TO govllm, public):
# without #42, the service's pool loses its search_path after RESET ALL
docker exec iso-pg psql -U postgres -d govllm_iso -q -c "ALTER DATABASE govllm_iso SET search_path TO govllm, public"
docker exec langfuse-db pg_dump -U langfuse -d langfuse --no-owner --no-privileges -t govllm.groundtruth_cases \
  | docker exec -i iso-pg psql -U postgres -d govllm_iso -q -v ON_ERROR_STOP=1 >/dev/null
docker exec redis redis-cli --raw GET config:judge > "$STATE/config_judge.json"
docker exec -i iso-redis redis-cli -x SET config:judge < "$STATE/config_judge.json" >/dev/null

docker run -d --name iso-eval --network "$NET" --memory 1g -w /app \
  -e ARENA_DB_URL=postgresql://postgres@iso-pg:5432/govllm_iso -e REDIS_URL=redis://iso-redis:6379/0 \
  -e LITELLM_BASE_URL=http://iso-litellm:4000 -e LITELLM_API_KEY=sk-iso -e OLLAMA_BASE_URL=http://iso-ollama:11434 \
  -e LANGFUSE_HOST=http://iso-langfuse:3000 -e LANGFUSE_PUBLIC_KEY=iso -e LANGFUSE_SECRET_KEY=iso \
  -e "BENCHMARK_MODELS=$(docker inspect evaluation --format '{{range .Config.Env}}{{println .}}{{end}}' | sed -n 's/^BENCHMARK_MODELS=//p')" \
  -e EVAL_INTERVAL_SECONDS=3600 -e 'ALLOWED_ORIGINS=["http://localhost"]' -e PYTHONPATH=/app \
  -v "$(host "$ROOT/back/evaluation"):/app:ro" -v "$(host "$ROOT/back/shared/src/shared"):/app/shared:ro" \
  -v infra_evaluation_venv:/app/.venv:ro \
  infra-evaluation /app/.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8003 >/dev/null

# Wait for the evaluation service and check what the stack really applies
for i in $(seq 1 120); do
  if docker exec iso-eval python -c "import urllib.request as u; u.urlopen('http://localhost:8003/config/inference-stack', timeout=5)" 2>/dev/null; then break; fi
  sleep 2
done
docker exec iso-eval python -c "
import json, urllib.request as u
s = json.load(u.urlopen('http://localhost:8003/config/inference-stack', timeout=30))
print('ollama', s['ollama_version'])
for m, p in sorted(s['model_params'].items()):
    print(' ', m, s['model_digests'].get(m, '?')[:12], p)
"
# None of the isolated containers may be attached to another network
for c in iso-ollama iso-litellm iso-pg iso-redis iso-langfuse iso-eval; do
  nets="$(docker inspect "$c" --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}')"
  [ "$nets" = "$NET " ] || { echo "ABORT: $c is attached to: $nets" >&2; exit 1; }
done
echo "isolated stack up on $NET"
