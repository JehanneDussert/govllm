#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
#
# Daily backup of the govllm database (docs/backups.md).
#
#   - pg_dump (custom format, compressed) of the govllm schema and of the Langfuse schema
#     (public), plus the roles (pg_dumpall --globals-only), taken inside the langfuse-db
#     container and copied out with docker cp (no binary data through the shell);
#   - MANIFEST: SHA-256 of every file and the row count of every govllm table and of the
#     main Langfuse tables, taken just before the dump;
#   - rotation: 7 daily copies in daily/, 4 weekly copies in weekly/ (the Sunday copy);
#   - every weekly copy is restore-tested in a throwaway instance (backup_restore_test.sh);
#   - off-PC copy, only if configured: an encrypted 7-Zip archive written to OFFSITE_DIR
#     with the password read from PASSWORD_FILE (both set by the operator, never by this
#     script). Without them the off-PC copy is skipped and the log says so.
#
# Read-only on the database. Usage:
#     bash scripts/backup_db.sh                       # BACKUP_DIR defaults below
#     BACKUP_DIR=/d/backups OFFSITE_DIR=/e/govllm PASSWORD_FILE=~/.govllm_backup_pw bash scripts/backup_db.sh
set -euo pipefail
export MSYS_NO_PATHCONV=1  # Git Bash: keep container paths (/tmp/...) as they are

BACKUP_DIR="${BACKUP_DIR:-$HOME/Documents/govllm-backups/daily-rotation}"
OFFSITE_DIR="${OFFSITE_DIR:-}"
PASSWORD_FILE="${PASSWORD_FILE:-}"
SEVENZIP="${SEVENZIP:-/c/Program Files/7-Zip/7z.exe}"
CONTAINER="${CONTAINER:-langfuse-db}"
DB_USER="${DB_USER:-langfuse}"
DB_NAME="${DB_NAME:-langfuse}"
KEEP_DAILY=7
KEEP_WEEKLY=4
HERE="$(cd "$(dirname "$0")" && pwd)"

STAMP="$(date +%Y%m%d_%H%M)"
DEST="$BACKUP_DIR/daily/$STAMP"
LOG="$BACKUP_DIR/backup.log"
mkdir -p "$DEST" "$BACKUP_DIR/weekly"
log() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }
host() { cygpath -w "$1" 2>/dev/null || echo "$1"; }
psql_ro() { docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -At -F ' ' -c "$1"; }

log "backup $STAMP -> $DEST"

# 1. Row counts just before the dump
{
  echo "# row counts taken before the dump ($STAMP)"
  psql_ro "SELECT 'govllm.' || s.relname, (xpath('/row/c/text()', query_to_xml(format('SELECT count(*) AS c FROM govllm.%I', s.relname), false, true, '')))[1]::text FROM pg_stat_user_tables s WHERE s.schemaname = 'govllm' ORDER BY 1;"
  psql_ro "SELECT 'public.' || t, (xpath('/row/c/text()', query_to_xml(format('SELECT count(*) AS c FROM public.%I', t), false, true, '')))[1]::text FROM unnest(ARRAY['traces','scores','observations','projects','users']) t WHERE to_regclass('public.' || t) IS NOT NULL ORDER BY 1;"
} > "$DEST/counts.txt"

# 2. Dumps inside the container, then docker cp
TMP="/tmp/govllm-backup-$STAMP"
docker exec "$CONTAINER" mkdir -p "$TMP"
docker exec "$CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc -Z 6 -n govllm -f "$TMP/govllm.dump"
docker exec "$CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc -Z 6 -n public -f "$TMP/langfuse_public.dump"
docker exec "$CONTAINER" sh -c "pg_dumpall -U '$DB_USER' --globals-only > '$TMP/globals.sql'"
for f in govllm.dump langfuse_public.dump globals.sql; do
  MSYS_NO_PATHCONV=1 docker cp "$CONTAINER:$TMP/$f" "$(host "$DEST/$f")"
done
docker exec "$CONTAINER" rm -rf "$TMP"

# 3. Manifest (hashes + counts)
( cd "$DEST" && sha256sum govllm.dump langfuse_public.dump globals.sql counts.txt > MANIFEST.sha256 )
log "dumps written: $(du -sh "$DEST" | cut -f1) ($(wc -l < "$DEST/counts.txt") count lines)"

# 4. Weekly copy (Sunday), restore-tested
if [ "$(date +%u)" = "7" ] || [ "${FORCE_WEEKLY:-0}" = "1" ]; then  # FORCE_WEEKLY=1: test the weekly path
  cp -r "$DEST" "$BACKUP_DIR/weekly/$STAMP"
  log "weekly copy: weekly/$STAMP"
  if bash "$HERE/backup_restore_test.sh" "$BACKUP_DIR/weekly/$STAMP" >> "$LOG" 2>&1; then
    log "restore test OK: weekly/$STAMP"
  else
    log "RESTORE TEST FAILED: weekly/$STAMP (see above)"
  fi
fi

# 5. Rotation
prune() {  # keep the newest $2 entries of directory $1
  { find "$1" -mindepth 1 -maxdepth 1 -type d | sort | head -n -"$2"; } | while read -r old; do
    rm -rf "$old"; log "pruned $old"
  done
}
prune "$BACKUP_DIR/daily" "$KEEP_DAILY"
prune "$BACKUP_DIR/weekly" "$KEEP_WEEKLY"

# 6. Off-PC copy, encrypted (only when the operator configured it)
if [ -n "$OFFSITE_DIR" ] && [ -n "$PASSWORD_FILE" ] && [ -r "$PASSWORD_FILE" ] && [ -x "$SEVENZIP" ]; then
  ARCHIVE="$(host "$OFFSITE_DIR/govllm_$STAMP.7z")"
  PW="$(head -n1 "$PASSWORD_FILE")"
  "$SEVENZIP" a -t7z -mx=5 -mhe=on -p"$PW" "$ARCHIVE" "$(host "$DEST")" > /dev/null
  "$SEVENZIP" t -p"$PW" "$ARCHIVE" > /dev/null && log "off-PC copy OK: $OFFSITE_DIR/govllm_$STAMP.7z"
  unset PW
  # same rotation off-PC: keep the newest KEEP_DAILY + KEEP_WEEKLY archives
  { find "$OFFSITE_DIR" -maxdepth 1 -name 'govllm_*.7z' | sort | head -n -"$((KEEP_DAILY + KEEP_WEEKLY))"; } |
    while read -r old; do rm -f "$old"; log "pruned off-PC $old"; done
else
  log "off-PC copy SKIPPED (OFFSITE_DIR / PASSWORD_FILE not configured)"
fi
log "backup $STAMP done"
