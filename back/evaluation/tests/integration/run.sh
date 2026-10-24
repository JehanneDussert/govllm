#!/bin/sh
# Run the evaluation tests, integration tests included, in a throwaway container built from
# the evaluation image: real PostgreSQL and Redis, but a separate schema (govllm_test) and
# Redis database (15), and a simulated judge (no LLM call). The running `evaluation`
# service and its data are not touched.
#
# Usage, from the repository root (or a worktree), with the dev stack up:
#     sh back/evaluation/tests/integration/run.sh [pytest args]
set -e
ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
ENV_FILE="$(mktemp)"
trap 'rm -f "$ENV_FILE"' EXIT
# Same settings as the running service (DB URL, model list, keys), test schema and Redis db
docker inspect evaluation --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | grep -E '^(LANGFUSE_HOST|ALLOWED_ORIGINS|LITELLM_API_KEY|EVAL_INTERVAL_SECONDS|ARENA_DB_URL|BENCHMARK_MODELS|LITELLM_BASE_URL|LANGFUSE_PUBLIC_KEY|LANGFUSE_SECRET_KEY)=' > "$ENV_FILE"
printf 'REDIS_URL=redis://redis:6379/15\nGOVLLM_DB_SCHEMA=govllm_test\nPYTHONPATH=/app\n' >> "$ENV_FILE"
host() { cygpath -w "$1" 2>/dev/null || echo "$1"; }
MSYS_NO_PATHCONV=1 docker run --rm --network infra_default --env-file "$(host "$ENV_FILE")" \
  -v "$(host "$ROOT/back/evaluation"):/app" \
  -v "$(host "$ROOT/back/shared/src/shared"):/app/shared" \
  -v infra_evaluation_venv:/app/.venv:ro \
  -w /app infra-evaluation /app/.venv/bin/python -m pytest tests -q -p no:cacheprovider "$@"
