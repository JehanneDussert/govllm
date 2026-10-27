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
   A second dump was taken right before the restoration, to allow a rollback: `pg_dumpall_20261026_0908.sql`, 15,260,316 bytes, SHA-256 `4EB8DDDA3ACFA9B848383800DDA6B4E9704148404D8A5C5D917BF4973B123D6F`. Its contents were checked by counting the rows of each table in the file (54 tables with data): `groundtruth_results` 4,704, `groundtruth_cases` 49, `eval_results` 30, `model_lifecycle` 0, `traces` 3,912, `scores` 4,552, all equal to the live database.
2. **Provenance**: two nullable columns, `eval_results.restored_from` (`'benchmark_files'`) and `restored_at` (time of the restoration, the same for the whole batch), added by migration (`migrations.sql`). They are NULL for every row written by `eval_runner`. No code reads `eval_results` with `SELECT *`.
3. `scripts/restore_eval_results.py`: deletes the 30 test rows and inserts the 3,064 benchmark evaluations, with their provenance, in one transaction. Dry run by default; idempotent. It refuses to run without the provenance columns.
4. `scripts/mark_self_judged.py`: flags self-judged rows (generator = judge). Then `backfill_matrix_cache.py` rebuilds the Redis cache.

Rehearsal on the throwaway restore (2026-10-26):
- 30 → 3,064 rows;
- second run: nothing to insert;
- `mark_self_judged`: 379 flagged, judge unknown 0. 384 before the incident: the 5 missing rows are diagonal evaluations that finished after the benchmark poll timed out, so they are not in the files.

A second rehearsal (2026-10-26, on a restore of the 09:08 dump, with the provenance migration) gave:
- 3,064 rows `restored_from = 'benchmark_files'`, evaluated between 2026-05-15 and 2026-08-27, with a single `restored_at`;
- 0 test rows;
- `mark_self_judged` dry run: 379 rows.

**Production run (2026-10-26, after approval):**
- **Migration:** two `ALTER TABLE` statements via `psql`.
- **`restore_eval_results.py --apply`:**
  - 30 → 3,064 rows, 0 test rows, 3,064 distinct trace_ids;
  - all rows `restored_from = 'benchmark_files'`, with a single `restored_at` of 2026-10-26 12:13:06 UTC;
  - `evaluated_at` from 2026-05-15 to 2026-08-27.
- **`mark_self_judged.py`:** dry run with 379 rows shown to the author, then `--apply` (UPDATE 379; 2,685 rows not self-judged).
- **Redis cache:** rebuilt with `backfill_matrix_cache.py`, which excludes self-judged rows (56 keys).
- **`GET /matrix`:** the 8 models have data in all 6 use cases.
- **`GET /matrix/routing`** (`analysis`, `ai_act_compliance`): returns a recommendation, and the judge `ministral-3:8b` is excluded.

**Remaining gap — old use-case IDs.** The May rows carry the use-case IDs of the time, `summary` and `legal`. The configuration has since renamed them `summarization` and `administrative_writing`. Their 24 rows per model and use case therefore sit under orphan cache keys. For the four original models, the Matrix shows only the 32 August rows on those two use cases, instead of 56. The restoration kept the IDs as they were written; the renaming needs a separate decision (`UPDATE` of the `use_case_id` of the 255 May rows concerned, 128 `summary` and 127 `legal`, as on 2026-08-22 for the Redis keys).

**Renaming done on 2026-10-26** (author's approval, conditions checked first):
- **Mapping:** `summary` → `summarization` (128 rows) and `legal` → `administrative_writing` (127 rows); 255 rows, all from May. The original values remain in the dump of 2026-10-26 09:08 (SHA-256 `4EB8DDDA…3B123D6F`).
- **Evidence of a pure rename:**
  - in commit `488b662` (2026-05-19), only the `id` changes: label, description and judge prompt are identical (the `default_profile_id` of `summary` changes only through the renaming of the profile `accessibility` to `accessibility_inclusion`);
  - in the benchmark files, the same 8 prompts (same IDs, same text) were evaluated under both IDs with the same profile (`quality_baseline`, `data_protection`);
  - the Redis keys had already been renamed the same way on 2026-08-22.
- **Transaction:** a single one.
  - Before: `summary` 128, `summarization` 383, `legal` 127, `administrative_writing` 381.
  - After: `summarization` 511, `administrative_writing` 508, no old ID left. Total unchanged (3,064).
- **Cache rebuilt:** 2,685 rows, 48 keys, no `summary` or `legal` key.
- **Matrix:** 8 models × 6 use cases. Each cell holds 56 evaluations (8 prompts × 7 judges other than the generator), except three cells at 55, which are benchmark evaluations with nothing to restore:
  - phi4-mini on `summarization` (`sum_01`) and on `analysis` (`ana_hard_01`): judged by lfm2.5, TIMEOUT;
  - gemma3:4b on `administrative_writing` (`adm_hard_02`): scored by hand in May (`score_missing_entry.py`), without the `eval` field.
- **Redis:** persistent (RDB snapshots on the `infra_redis_data` volume, `BGSAVE` after the rebuild). The cache survives a Docker restart.

**The Redis cache keeps a 7-day TTL on `main`.** Without evaluation activity, it will expire again; PR #42 makes `eval_results` the source the Matrix and routing read.

## Prevention

- **Connection-level schema:** `server_settings={"search_path": …}` in `db/database.py` (PR #42).
- **Integration tests:** they will run only on dedicated PostgreSQL and Redis instances (separate containers, other ports, throwaway volumes), with no credentials of the real database in their environment. A guard checks host, port, database name and `current_schema()` on every connection, and refuses anything that looks like production.
- **Backups:** a daily backup PR (`pg_dump` of the govllm and Langfuse schemas, 7 daily + 4 weekly copies, a copy off the PC, a documented restore test) comes before the lifecycle PR.
