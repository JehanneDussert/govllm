#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
#
# Restore test of one backup made by backup_db.sh (docs/backups.md):
#   1. check every hash of MANIFEST.sha256;
#   2. start a throwaway PostgreSQL 16 (no network, 512 MB, data on tmpfs);
#   3. restore globals.sql, govllm.dump and langfuse_public.dump with ON_ERROR_STOP / exit-on-error;
#   4. count the rows of the restored tables and compare them with counts.txt.
# The container is removed at the end, even on failure. Exit code 0 = restore OK.
#
#     bash scripts/backup_restore_test.sh ~/Documents/govllm-backups/daily-rotation/daily/20261026_2200
set -euo pipefail
export MSYS_NO_PATHCONV=1  # Git Bash: keep container paths (/tmp/...) as they are
DIR="${1:?usage: backup_restore_test.sh <backup directory>}"
NAME="govllm-restore-test-$$"
host() { cygpath -w "$1" 2>/dev/null || echo "$1"; }
cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT INT TERM

echo "restore test of $DIR"
( cd "$DIR" && sha256sum -c --quiet MANIFEST.sha256 ) && echo "  hashes OK"

MSYS_NO_PATHCONV=1 docker run -d --rm --name "$NAME" --network none --memory 512m \
  -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=langfuse \
  --tmpfs /var/lib/postgresql/data postgres:16-alpine >/dev/null
i=0
until docker exec "$NAME" pg_isready -q -h 127.0.0.1 -U postgres 2>/dev/null; do
  i=$((i + 1)); [ "$i" -gt 60 ] && { echo "  PostgreSQL did not start"; exit 1; }; sleep 1
done

for f in globals.sql govllm.dump langfuse_public.dump; do
  MSYS_NO_PATHCONV=1 docker cp "$(host "$DIR/$f")" "$NAME:/tmp/$f"
done
# globals.sql recreates the roles; the postgres superuser already exists (that one error is expected)
docker exec "$NAME" psql -U postgres -q -f /tmp/globals.sql >/dev/null 2>&1 || true
docker exec "$NAME" pg_restore -U postgres -d langfuse --exit-on-error /tmp/govllm.dump
docker exec "$NAME" pg_restore -U postgres -d langfuse --exit-on-error --clean --if-exists /tmp/langfuse_public.dump
echo "  pg_restore OK"

status=0
while read -r table expected; do
  case "$table" in \#*|"") continue ;; esac
  got="$(docker exec "$NAME" psql -U postgres -d langfuse -At -c "SELECT count(*) FROM $table")"
  if [ "$got" = "$expected" ]; then
    echo "  $table $got"
  else
    # counts.txt is taken just before pg_dump: a write in between shows up here
    echo "  $table restored $got, counted before the dump $expected  <-- DIFFERENT"; status=1
  fi
done < "$DIR/counts.txt"
[ "$status" = 0 ] && echo "restore test OK" || echo "restore test: row counts differ (see above)"
exit "$status"
