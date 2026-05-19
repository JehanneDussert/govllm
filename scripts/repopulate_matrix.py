"""
Clears Redis eval:scores:* keys and repopulates from all 16 benchmark result files.
Each cell (model × use_case) will have exactly 32 entries (4 judges × 8 prompts).
Run inside the evaluation container: python scripts/repopulate_matrix.py
"""
import json
import os
import redis

# Use_case IDs are now aligned between prompts.json and config; no mapping needed.
UC_MAP: dict[str, str] = {}

RESULTS_DIR = "/app/docs/benchmark/results"
TTL = 3600 * 24 * 7  # 7 days

r = redis.from_url("redis://redis:6379", decode_responses=True)

# Step 1: clear existing eval:scores keys
existing = r.keys("eval:scores:*")
if existing:
    r.delete(*existing)
    print(f"Cleared {len(existing)} existing eval:scores keys")

# Step 2: accumulate all scores from result files
# scores[model][uc_config_id] = list of {"score": float, "ts": str}
scores: dict[str, dict[str, list]] = {}

result_files = [f for f in os.listdir(RESULTS_DIR) if f.endswith(".json")]
print(f"Found {len(result_files)} result files")

for fname in sorted(result_files):
    fpath = os.path.join(RESULTS_DIR, fname)
    with open(fpath) as fp:
        data = json.load(fp)

    model = data.get("model")  # e.g. "ollama/phi4-mini"
    results = data.get("results", [])

    if not model:
        print(f"  SKIP {fname}: no model field")
        continue

    if model not in scores:
        scores[model] = {}

    for entry in results:
        uc_raw = entry.get("use_case", "")
        uc_id = UC_MAP.get(uc_raw, uc_raw)
        score = entry.get("score")
        ts = entry.get("evaluated_at") or "2026-05-19T00:00:00+00:00"

        if score is None:
            continue

        if uc_id not in scores[model]:
            scores[model][uc_id] = []
        scores[model][uc_id].append({"score": float(score), "ts": ts})

# Step 3: write to Redis
total_keys = 0
for model, uc_dict in sorted(scores.items()):
    for uc_id, entries in sorted(uc_dict.items()):
        key = f"eval:scores:{model}:{uc_id}"
        r.setex(key, TTL, json.dumps(entries[-100:]))  # keep at most 100
        print(f"  {key}: {len(entries)} entries")
        total_keys += 1

print(f"\nDone. Wrote {total_keys} keys.")

# Verify
print("\nVerification:")
keys = sorted(r.keys("eval:scores:*"))
for k in keys:
    raw = r.get(k)
    n = len(json.loads(raw)) if raw else 0
    print(f"  {k}: {n}")
