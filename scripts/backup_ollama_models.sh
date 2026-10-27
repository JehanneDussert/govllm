#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
# Copy the Ollama manifests + blobs of the 8 judge models out of the `ollama` container
# (no download, no new container), verify every blob's sha256, write SHA256SUMS + models.json.
# Stops if the Docker VM drops under 300 MB of available memory.
set -u
DEST="${1:?usage: backup_ollama_models.sh <destination dir outside the repo>}"
SRC=/root/.ollama/models
MODELS=(
  "registry.ollama.ai/library/phi4-mini/latest"
  "registry.ollama.ai/library/qwen3/1.7b"
  "registry.ollama.ai/library/gemma3/4b"
  "registry.ollama.ai/library/mistral/7b"
  "registry.ollama.ai/library/gemma4/e4b"
  "registry.ollama.ai/library/ministral-3/8b"
  "registry.ollama.ai/library/granite4/latest"
  "hf.co/LiquidAI/LFM2.5-1.2B-Thinking-GGUF/latest"
)
mkdir -p "$DEST/manifests" "$DEST/blobs"
log() { echo "$(date '+%F %T') $*" | tee -a "$DEST/backup.log"; }
mem_ok() {
  kb=$(docker exec redis sh -c "grep MemAvailable /proc/meminfo" | awk '{print $2}')
  [ -n "$kb" ] && [ "$kb" -ge 307200 ] || { log "STOP: VM MemAvailable=${kb:-unknown} kB < 300 MB"; exit 2; }
}
echo "[" > "$DEST/models.json.tmp"; first=1
for m in "${MODELS[@]}"; do
  mem_ok
  mkdir -p "$DEST/manifests/$(dirname "$m")"
  docker cp "ollama:$SRC/manifests/$m" "$DEST/manifests/$m" >/dev/null || { log "FAIL manifest $m"; exit 1; }
  mdig=$(sha256sum "$DEST/manifests/$m" | cut -d' ' -f1)
  digests=$(grep -o 'sha256:[0-9a-f]\{64\}' "$DEST/manifests/$m" | sort -u)
  for d in $digests; do
    f="sha256-${d#sha256:}"
    if [ -f "$DEST/blobs/$f" ] && [ "$(sha256sum "$DEST/blobs/$f" | cut -d' ' -f1)" = "${d#sha256:}" ]; then
      log "skip $f (already verified)"; continue
    fi
    mem_ok
    docker cp "ollama:$SRC/blobs/$f" "$DEST/blobs/$f" >/dev/null || { log "FAIL blob $f"; exit 1; }
    got=$(sha256sum "$DEST/blobs/$f" | cut -d' ' -f1)
    [ "$got" = "${d#sha256:}" ] || { log "SHA MISMATCH $f got $got"; exit 1; }
    log "ok $m $f $(stat -c %s "$DEST/blobs/$f") bytes"
  done
  [ $first -eq 1 ] || echo "," >> "$DEST/models.json.tmp"; first=0
  printf '  {"manifest": "%s", "manifest_sha256": "%s", "ollama_id": "%s", "blobs": [%s]}' \
    "$m" "$mdig" "${mdig:0:12}" "$(echo $digests | sed 's/\([^ ]*\)/"\1"/g; s/ /, /g')" >> "$DEST/models.json.tmp"
done
echo "" >> "$DEST/models.json.tmp"; echo "]" >> "$DEST/models.json.tmp"; mv "$DEST/models.json.tmp" "$DEST/models.json"
(cd "$DEST" && find manifests blobs -type f | sort | xargs sha256sum > SHA256SUMS)
log "ALL_DONE $(du -sh "$DEST" | cut -f1)"
