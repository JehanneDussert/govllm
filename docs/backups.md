# Database backups

The govllm database stores three kinds of data that cannot be rebuilt. These are the ground-truth results and their repeated runs, the evaluation history behind the Matrix and AUTO routing (`eval_results`), and the Langfuse traces. In October 2026, `eval_results` was emptied with no backup to restore from ([docs/incident_2026-10-24_eval_results.md](incident_2026-10-24_eval_results.md)). This procedure exists so that it cannot happen again.

## What a backup contains

`scripts/backup_db.sh` writes one directory per run, `daily/<YYYYMMDD_HHMM>/`:

| File | Content |
|---|---|
| `govllm.dump` | `pg_dump -Fc` of the `govllm` schema (ground truth, evaluation results, lifecycle, Arena) |
| `langfuse_public.dump` | `pg_dump -Fc` of the `public` schema (Langfuse: traces, scores, projects, users) |
| `globals.sql` | roles (`pg_dumpall --globals-only`) |
| `counts.txt` | row count of every `govllm` table and of the main Langfuse tables, taken just before the dump |
| `MANIFEST.sha256` | SHA-256 of the four files above |

The dumps are taken inside the `langfuse-db` container and copied out with `docker cp`. The script only reads the database.

## Rotation

- **daily:** 7 copies in `daily/`; one run per day.
- **weekly:** 4 copies in `weekly/`. The Sunday copy is also stored there, and it is **restore-tested automatically** (see below). The result is in `backup.log`.
- **off-PC:** an encrypted 7-Zip archive (`-mhe=on`: contents and file names), tested after writing. 11 archives are kept (7 + 4). This step runs only when the operator sets both:
  - `OFFSITE_DIR`: a folder synced off the PC (cloud storage) or an external drive;
  - `PASSWORD_FILE`: a file whose first line is the archive password, readable only by the operator. Keep the password somewhere other than the PC as well: without it, the archives cannot be opened.

  Without them, the log says `off-PC copy SKIPPED`. The script never chooses a destination or a password. Note: the password is passed to 7-Zip on its command line, so it is briefly visible to other processes of the same user.

## Restore test

```bash
bash scripts/backup_restore_test.sh <backup directory>
```

1. It checks every hash of `MANIFEST.sha256`.
2. It starts a throwaway PostgreSQL 16: no network, 512 MB, data on tmpfs.
3. It restores the roles and both dumps, stopping at the first error.
4. It compares the row count of every table with `counts.txt`. A difference means a write happened between the count and the dump; it is reported, and the test fails.

The container is removed at the end, even on failure. Exit code 0 = OK.

Check of 2026-10-26: backup of 4.4 MB; restore OK; the 12 counted tables were identical (`eval_results` 3,064, `groundtruth_results` 4,704, `traces` 3,912, `scores` 4,552, …). Also checked:
- rotation (7 / 4 / 11 kept);
- encrypted off-PC copy, refused with a wrong password;
- weekly path (`FORCE_WEEKLY=1`).

## Restoring for real

Restore into a throwaway instance first, as above, and compare. Then, with the services stopped (`docker stop evaluation llm-gateway observability langfuse`):

```bash
D=~/Documents/govllm-backups/daily-rotation/daily/<stamp>
docker cp "$D/govllm.dump" langfuse-db:/tmp/govllm.dump
docker exec langfuse-db pg_restore -U langfuse -d langfuse --clean --if-exists --exit-on-error /tmp/govllm.dump
# Langfuse, only if it is lost too:
docker cp "$D/langfuse_public.dump" langfuse-db:/tmp/langfuse_public.dump
docker exec langfuse-db pg_restore -U langfuse -d langfuse --clean --if-exists --exit-on-error /tmp/langfuse_public.dump
```

Then restart the services and rebuild the Matrix cache:

```bash
docker exec -w /app evaluation python scripts/backfill_matrix_cache.py
```

## Scheduling (Windows)

The script needs Docker to be running. To register a daily task at 22:00 (run once by the operator, in PowerShell):

```powershell
schtasks /Create /TN govllm-daily-backup /SC DAILY /ST 22:00 /F /TR "\"C:\Program Files\Git\bin\bash.exe\" -lc 'cd /c/Users/jehan/Documents/govllm && bash scripts/backup_db.sh'"
```

Add `OFFSITE_DIR=... PASSWORD_FILE=...` in front of `bash scripts/backup_db.sh` once the off-PC destination is chosen. Check `backup.log` in `BACKUP_DIR` (default `~/Documents/govllm-backups/daily-rotation`).
