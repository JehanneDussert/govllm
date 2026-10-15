# Good first issues

A handful of self-contained tasks from the project backlog, picked because they don't require the paper's context, ground truth runs, or a deep understanding of the judge architecture. If `gh` access is set up for this repo, these should be filed as GitHub Issues instead — this file is the fallback until then.

---

## 1. Warning UI if the generator model is in the active judge panel

**Where:** `front/src/views/SettingsView.vue`, judge panel section (per-profile "JUDGE PANEL" accordion).

**What:** In Arena, the model being evaluated is automatically excluded from the judge panel for that run (a model shouldn't judge its own output — self-preference bias). The same constraint exists conceptually for production panels (`JudgePanel` in `back/shared/src/shared/schemas/judge.py`), but it's not enforced or even warned about in the Settings UI: nothing stops an operator from assigning a model as both the chat generator (`preferred_model` on a use case) and a judge in that profile's panel.

**Task:** add a visible warning (banner or inline note) in the Settings → Governance profiles → Judge Panel section when the panel includes a model that matches the active use case's `preferred_model`. No backend change needed — this is a pure frontend check against data already available in the Settings store.

---

## 2. `groundtruth.py seed` should read from `corpus.json`, not a hardcoded list

**Where:** `back/evaluation/scripts/groundtruth.py`.

**What:** The 49 ground truth cases are currently defined twice: once as a hardcoded Python list (`CASES`) in `groundtruth.py`, and once in `docs/ground_truth/corpus.json` — supposed to be identical, but two independent sources mean adding or editing a case requires updating both by hand, and they can silently drift.

**Task:** replace the `CASES = [...]` list with:
```python
cases = json.loads(Path("docs/ground_truth/corpus.json").read_text())["cases"]
```
adjusting the relative path to work whether the script is run inside the Docker container (`/app/...`) or from the repo root. `corpus.json` becomes the single source of truth; the DB stays the operational derivative. Verify field names match exactly what `cmd_seed` expects (`corpus.json` uses `expected_answers`, check the field the current `CASES` list uses for the same data before finishing).

---

## 3. `scripts/extract_langfuse.py` — latency/token analysis from Langfuse traces

**Where:** new file, `scripts/extract_langfuse.py`.

**What:** The benchmark results (`docs/benchmark/results/*.json`) have scores but not real latency or token counts — that data lives in Langfuse traces, keyed by `trace_id`. No script currently joins the two.

**Task:**
1. Read all `docs/benchmark/results/*.json`, collect the `trace_id` of every entry (the join key — not `session_id`).
2. Resolve those traces via the Langfuse SDK directly (not `GET /observability/traces` — that endpoint caps at 200 results and filters out judge traces, which would break the join).
3. For each trace, extract `trace_id`, `model`, real latency (ms), and `usage.completion_tokens` if present.
4. Before writing the full script: check on a handful of existing traces whether `usage.completion_tokens` is actually populated (Ollama doesn't always report it) — if it's consistently null, skip the token columns and keep latency/score as the analysis, don't build dead code around a field that's never populated.
5. Join on `trace_id`, write `docs/benchmark/analysis/latency_score.json` (per-prompt detail) and `docs/benchmark/analysis/latency_summary.json` (p50/p95 latency, mean score, ratio score/latency per model).

Should be re-runnable: re-reads `results.json` + Langfuse traces each time, overwrites the analysis files.

---

## 4. README GIF — governance profile switch demo

**Where:** `README.md`, `docs/screenshots/`.

**What:** The README backlog has a standing item for an animated GIF showing a governance profile switch in the UI with scores updating live (similar in spirit to the existing `govllm-demo.gif`). Not there yet.

**Task:** using the running dev stack (`make dev`), record a short screen capture (10-20s) of: opening Settings → switching the active governance profile → navigating to Matrix or Chat and showing the criteria/weights (or scores) reflect the new profile without a service restart. Convert to an optimized GIF (keep it small — under ~3MB, similar to the existing demo GIF), save to `docs/screenshots/`, and reference it in the README near the existing screenshots section.

---

## Before you start

- Read `CONTRIBUTING.md` for the setup and development conventions (especially: diff before modification, one change at a time).
- **If your fix touches anything under `back/evaluation/` or `back/shared/`**, know that `make dev` runs with hot-reload — editing those files while a long-running background job (a ground truth run, a benchmark) is active against the same service will stall it until the in-flight request completes. Check `make gt-status` before editing if you're unsure whether something's running.
- Open a draft PR early if you want feedback on direction before finishing.
