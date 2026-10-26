# Integration tests

Real PostgreSQL and Redis, simulated judge, no LLM call. They run **only** against dedicated throwaway instances, never against the deployment's database.

On 2026-10-24, an earlier version of these tests ran in a separate schema of the real database. A reset `search_path` sent their `TRUNCATE` to the production tables. See [docs/incident_2026-10-24_eval_results.md](../../../../docs/incident_2026-10-24_eval_results.md).

## Running

```bash
sh back/evaluation/tests/integration/run.sh            # all evaluation tests, integration included
sh back/evaluation/tests/integration/run.sh -k drift   # extra pytest arguments are passed through
```

`run.sh` starts the following, then removes everything at the end, even on failure:

| Container | Role | Identity |
|---|---|---|
| `govllm-itest-pg` | PostgreSQL 16, data on tmpfs | port 5433, database `govllm_itest`, `cluster_name=govllm-itest`, password generated per run |
| `govllm-itest-redis` | Redis 7, no persistence | port 6380 |
| runner | `infra-evaluation` image (no rebuild), code mounted from this checkout | — |

Isolation:
- **Private network:** all three containers sit on a network created with `--internal` for this run. It has no route to the deployment's containers (`langfuse-db`, `redis`) or to the outside.
- **No real settings:** the runner receives only test settings; no DSN or key of the deployment.
- **Memory cap:** every container is limited to 512 MB.

## Guards (`conftest.py`)

1. **Configuration.** The integration tests are skipped unless the DSN names `govllm-itest-pg:5433/govllm_itest`, the schema is `govllm_itest` and the Redis URL names `govllm-itest-redis:6380`.
2. **Every connection.**
   - `asyncpg.create_pool` and `asyncpg.connect` are wrapped. Each PostgreSQL connection, on every acquire from the pool, must report `current_database() = govllm_itest`, `cluster_name = govllm-itest`, `inet_server_port() = 5433` and the test schema. Otherwise the run aborts (`pytest.exit`, code 3) before any statement.
   - Before any flush, the Redis server must report port 6380.

Negative check (2026-10-26): with a PostgreSQL of the same name, port and database but another `cluster_name`, the run aborts on the first connection (exit code 3, no table created).

## Proving that the real database received no write

```bash
sh back/evaluation/tests/integration/prod_snapshot.sh > before.txt
sh back/evaluation/tests/integration/run.sh
sh back/evaluation/tests/integration/prod_snapshot.sh > after.txt
diff before.txt after.txt   # no output = no write
```

`prod_snapshot.sh` is read-only. It records, for every table of the `govllm` schema:
- the row count;
- PostgreSQL's cumulative insert, update and delete counters.

It also records the Redis key count and a checksum of the `eval:scores` cache.
