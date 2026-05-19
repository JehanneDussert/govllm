import json
import redis

TTL = 3600 * 24 * 7
r = redis.from_url("redis://redis:6379", decode_responses=True)

existing = r.keys("eval:scores:*")
if existing:
    r.delete(*existing)
    print(f"Cleared {len(existing)} existing keys")

with open("/app/matrix_data.json") as f:
    scores = json.load(f)

written = 0
for model, uc_dict in sorted(scores.items()):
    for uc_id, entries in sorted(uc_dict.items()):
        key = f"eval:scores:{model}:{uc_id}"
        r.setex(key, TTL, json.dumps(entries))
        print(f"  {key}: {len(entries)}")
        written += 1

print(f"\nDone. Wrote {written} keys.")
