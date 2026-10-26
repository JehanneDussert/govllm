# Incident of 2026-10-24: `eval_results` and `model_lifecycle` emptied by integration tests

## What happened

On 2026-10-24, between 09:16 and 09:45 UTC, the integration tests of PR #42 were run against the development database. They were supposed to run in a separate schema (`govllm_test`). asyncpg runs `RESET ALL` when a connection returns to the pool. The `search_path` had only been set in the pool's `init` callback, so it was reset after the first query, and the following statements ran in the default schema, `govllm`. The tests' `TRUNCATE` therefore emptied the production tables:
- `govllm.eval_results`;
- `govllm.model_lifecycle`.

The tests then wrote 30 rows (`model = 'ollama/test-generator'`) and 21 lifecycle transitions, which their own teardown removed again.

Deletion by `TRUNCATE`, so nothing can be recovered from PostgreSQL:
- `pg_stat_user_tables` shows, for `eval_results`, 1,312 inserts, **0 deletes** and 30 live rows (TRUNCATE is not counted as deletes);
- `archive_mode = off`, and only 2 WAL segments remain;
- no backup existed.

Not affected:
- the ground truth (`groundtruth_cases`, `groundtruth_results`: 49 cases, 4,704 results including the test-retest run);
- Arena;
- Langfuse (`public.*`, 3,912 traces);
- the Redis configuration;
- the benchmark files.

## What was lost

| Data | Before | Restorable | Lost |
|---|---|---|---|
| `eval_results`, benchmark evaluations | 3,064 | **all, exactly**: each OK entry of `docs/benchmark/results/*.json` stores the row as written (`eval` field: trace_id, generator, use case, profile, composite score, per-criterion scores, `evaluated_at`) | — |
| `eval_results`, other rows (chat, discarded runs, evaluations completed after the benchmark poll timed out) | about 333 (3,397 − 3,064) | no exact source (Langfuse keeps the composite score but per-criterion scores only for flagged criteria) | **about 333 rows** |
| `model_lifecycle` | most likely empty (every model was shown in TEST; the 21 transitions recorded since the statistics reset are the tests' own) | — | possibly nothing; if there was history, it is lost |

The 3,397 rows before the incident are known from the `mark_self_judged.py` dry run of 2026-10-23. That run flagged 384 self-judged rows from the benchmark files, which is exactly the 8 diagonal files × 48. This shows that the whole benchmark, May and August, was in the table.

**Correction:** the figures of "2,817 benchmark rows and about 580 others", given on 2026-10-24, were wrong. No rule reproduces them from the data.

No figure of the paper (v1 or v2) depends on `eval_results` or `model_lifecycle`. The analyses read the benchmark files and `groundtruth_results`. What the loss affects is the Matrix, AUTO routing, the SAS and the drift watcher, which read `eval_results` (PR #42) and lose the chat history.

## Restoration (option b, decision of 2026-10-25)

1. **Backup first**: `pg_dumpall` of 2026-10-25 15:39, 15,260,316 bytes, SHA-256 `64336E34…88BE16`, kept on the PC and as an encrypted copy off the PC. Restore test on 2026-10-26 in a throwaway instance (`postgres:16-alpine`, `--network none`, `--memory 512m`): no error, 56 tables, identical row counts and identical checksum of `groundtruth_results` against the live database.
2. `scripts/restore_eval_results.py`: deletes the 30 test rows and inserts the 3,064 benchmark evaluations, in one transaction. Dry run by default; idempotent.
3. `scripts/mark_self_judged.py`: flags self-judged rows (generator = judge). Then `backfill_matrix_cache.py` rebuilds the Redis cache.

Rehearsal on the throwaway restore (2026-10-26):
- 30 → 3,064 rows;
- second run: nothing to insert;
- `mark_self_judged`: 379 flagged, judge unknown 0. 384 before the incident: the 5 missing rows are diagonal evaluations that finished after the benchmark poll timed out, so they are not in the files.

The production run waits for the author's approval.

## Prevention

- **Connection-level schema:** `server_settings={"search_path": …}` in `db/database.py` (PR #42).
- **Integration tests:** they will run only on dedicated PostgreSQL and Redis instances (separate containers, other ports, throwaway volumes), with no credentials of the real database in their environment. A guard checks host, port, database name and `current_schema()` on every connection, and refuses anything that looks like production.
- **Backups:** a daily backup PR (`pg_dump` of the govllm and Langfuse schemas, 7 daily + 4 weekly copies, a copy off the PC, a documented restore test) comes before the lifecycle PR.
