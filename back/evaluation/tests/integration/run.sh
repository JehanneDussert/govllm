#!/bin/sh
# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
#
# Run the evaluation tests, integration tests included, against DEDICATED throwaway
# instances: a PostgreSQL and a Redis started for this run only, on a private Docker
# network created with --internal (no route to the deployment's containers or outside).
# The test runner is attached to that network only and receives no setting of the real
# deployment (no DSN, no key): the real database is unreachable from it, by construction.
# Every container is capped at 512 MB and removed at the end, even on failure.
#
#   PostgreSQL  govllm-itest-pg     port 5433, database govllm_itest, cluster_name govllm-itest,
#                                   data on tmpfs
#   Redis       govllm-itest-redis  port 6380, no persistence
#   runner      infra-evaluation image (no rebuild), code mounted from this checkout
#
# conftest.py checks the identity of every connection (see its docstring) on top of this.
#
# Usage, from the repository root (or a worktree):
#     sh back/evaluation/tests/integration/run.sh [pytest args]
set -eu
ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
RUN_ID="$(date +%s)$$"
NET="govllm-itest-$RUN_ID"
PG="govllm-itest-pg"
REDIS="govllm-itest-redis"
PASSWORD="$(od -An -N12 -tx1 /dev/urandom | tr -d ' \n')"
ENV_FILE="$(mktemp)"

cleanup() {
  docker rm -f "$PG" "$REDIS" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
  rm -f "$ENV_FILE"
}

# Refuse to start if a previous run left containers behind
if docker ps -a --format '{{.Names}}' | grep -qE "^($PG|$REDIS)\$"; then
  echo "Leftover $PG / $REDIS containers: remove them first (docker rm -f $PG $REDIS)" >&2
  rm -f "$ENV_FILE"; exit 1
fi
trap cleanup EXIT INT TERM

docker network create --internal "$NET" >/dev/null
MSYS_NO_PATHCONV=1 docker run -d --name "$PG" --network "$NET" --memory 512m \
  -e POSTGRES_USER=itest -e POSTGRES_PASSWORD="$PASSWORD" -e POSTGRES_DB=govllm_itest \
  --tmpfs /var/lib/postgresql/data \
  postgres:16-alpine -c port=5433 -c cluster_name=govllm-itest >/dev/null
MSYS_NO_PATHCONV=1 docker run -d --name "$REDIS" --network "$NET" --memory 512m \
  redis:7-alpine redis-server --port 6380 --save "" --appendonly no >/dev/null

i=0
until docker exec "$PG" pg_isready -q -h 127.0.0.1 -p 5433 -U itest -d govllm_itest 2>/dev/null; do
  i=$((i + 1)); [ "$i" -gt 60 ] && { echo "PostgreSQL did not start" >&2; exit 1; }; sleep 1
done

# Test settings only. The service needs every field to be set; nothing points to the deployment.
cat > "$ENV_FILE" <<EOF
ARENA_DB_URL=postgresql://itest:$PASSWORD@$PG:5433/govllm_itest
GOVLLM_DB_SCHEMA=govllm_itest
REDIS_URL=redis://$REDIS:6380/0
LITELLM_BASE_URL=http://unreachable.invalid
LITELLM_API_KEY=test
LANGFUSE_HOST=http://unreachable.invalid
LANGFUSE_PUBLIC_KEY=test
LANGFUSE_SECRET_KEY=test
BENCHMARK_MODELS=["ollama/test-generator","ollama/test-other"]
EVAL_INTERVAL_SECONDS=60
ALLOWED_ORIGINS=["http://localhost"]
PYTHONPATH=/app
EOF

host() { cygpath -w "$1" 2>/dev/null || echo "$1"; }
MSYS_NO_PATHCONV=1 docker run --rm --network "$NET" --memory 512m --env-file "$(host "$ENV_FILE")" \
  -v "$(host "$ROOT/back/evaluation"):/app" \
  -v "$(host "$ROOT/back/shared/src/shared"):/app/shared" \
  -v infra_evaluation_venv:/app/.venv:ro \
  -w /app infra-evaluation /app/.venv/bin/python -m pytest tests -q -p no:cacheprovider "$@"
