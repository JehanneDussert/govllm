#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
"""
Judge reliability analysis — 3-level cross between benchmark + ground truth.

Level 1 — Agreement rate (from validity.json)
Level 2 — Reason consistency (from benchmark criteria_scores)
Level 3 — Composite reliability classification

Bonus — High-disagreement reasons for top prompts (σ > 0.15)

Output: docs/benchmark/analysis/judge_reliability.json
"""

import json
import re
from collections import defaultdict
from pathlib import Path

RESULTS_DIR   = Path("docs/benchmark/results")
VALIDITY_FILE = Path("docs/ground_truth/validity.json")
SUMMARY_FILE  = Path("docs/benchmark/analysis/summary.json")
PROMPTS_FILE  = Path("docs/benchmark/prompts.json")
OUTPUT_FILE   = Path("docs/benchmark/analysis/judge_reliability.json")

JUDGES = ["phi4-mini", "qwen3-1.7b", "gemma3-4b", "mistral-7b"]

# ── Reason sentiment heuristics ───────────────────────────────────────────────

# Note: "no" excluded — "no false claims present" / "no unexplained acronyms"
# are positive reasons. Only unambiguous problem markers are kept.

# Compound negations where "does not [violation-word]" is semantically positive
# (the response does not violate = compliant). Strip before PROBLEM_PATTERNS fires.
COMPOUND_NEGATION = re.compile(
    r"\b(does not|doesn'?t)\s+"
    r"(violat|constitut|represent|expos|reveal|creat|introduc|"
    r"contain|leak|bias|manipulat|inject|produc|generat)\w*\b",
    re.IGNORECASE,
)

# "no [problem-adjective] [noun]" is semantically positive:
# "no unexplained acronyms", "no false claims", "no unnecessary data" = compliant.
# The dominant false-positive source in phi4-mini transparency reasons.
POSITIVE_NEGATION = re.compile(
    r"\bno\s+(unexplained|unnecessary|false|mislead\w*|manipulat\w*|"
    r"incorrect|inaccurat\w*|inappropriate\w*|undisclosed|excessive|"
    r"harmful|dangerous|biased?|inject\w*|leak\w*)\b",
    re.IGNORECASE,
)

PROBLEM_PATTERNS = re.compile(
    r"\b(not\b|lacks?|missing|unclear|fail|fails|doesn'?t|does not|"
    r"problematic|issue|concern|violat|risk|inadequate|insufficient|"
    r"absent|without\b|omit|vague|incomplete|mislead|manipulat|inject|"
    r"leak|bias|confus|incorrect|inaccurat|error|wrong|danger|harmful|"
    r"inappropriat|unexplained|undisclosed|excessive|ignores?)\b",
    re.IGNORECASE,
)

POSITIVE_PATTERNS = re.compile(
    r"\b(clear|accurat|correct|appropriat|good|well|excellent|effective|"
    r"properly|fully|directly|provides?|addresses?|meets?|satisf|"
    r"compli|transparent|present|includes?|mentions?|acknowledg|"
    r"balanced|neutral|justified|structured|explicit|inform)\b",
    re.IGNORECASE,
)


def _reason_sentiment(reason: str) -> str:
    """'positive' | 'negative' | 'ambiguous'"""
    if not reason or len(reason.strip()) < 5:
        return "ambiguous"
    scrubbed = COMPOUND_NEGATION.sub("", reason)
    scrubbed = POSITIVE_NEGATION.sub("", scrubbed)
    neg = bool(PROBLEM_PATTERNS.search(scrubbed))
    pos = bool(POSITIVE_PATTERNS.search(scrubbed))
    if neg and not pos:
        return "negative"
    if pos and not neg:
        return "positive"
    return "ambiguous"


def _short_name(model: str) -> str:
    return model.removeprefix("ollama/").replace(":", "-")


def _r(v, n=3) -> float | None:
    return round(v, n) if v is not None else None


# ── Load data ─────────────────────────────────────────────────────────────────

def load_validity() -> dict:
    with open(VALIDITY_FILE, encoding="utf-8") as f:
        return json.load(f)


def load_benchmark() -> list[dict]:
    """Flat list of criteria_score entries enriched with context."""
    rows = []
    for fpath in sorted(RESULTS_DIR.glob("*.json")):
        with open(fpath, encoding="utf-8") as f:
            data = json.load(f)
        gen   = _short_name(data["model"])
        judge = _short_name(data["judge_model"])
        for r in data["results"]:
            if r.get("status") != "OK" or not r.get("eval"):
                continue
            use_case = r["use_case"]
            profile  = r["governance_profile"]
            pid      = r["id"]
            # Infer difficulty from id
            if "hard" in pid:
                diff = "hard"
            elif "adv" in pid:
                diff = "adversarial"
            elif "_06" in pid:
                diff = "medium"
            elif any(f"_{x:02d}" in pid for x in [1, 2, 3, 4, 5]):
                diff = "easy" if any(f"_0{n}" in pid for n in [1, 3, 4, 5]) else "medium"
            else:
                diff = "unknown"
            for cs in r["eval"].get("criteria_scores", []):
                rows.append({
                    "gen":        gen,
                    "judge":      judge,
                    "prompt_id":  pid,
                    "use_case":   use_case,
                    "profile":    profile,
                    "difficulty": diff,
                    "criterion":  cs["criterion_id"],
                    "score":      cs["score"],
                    "flag":       cs.get("flag", False),
                    "reason":     cs.get("reason", ""),
                    "composite":  r["score"],
                })
    return rows


def load_prompt_difficulty() -> dict[str, str]:
    with open(PROMPTS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    out = {}
    for uc, prompts in data["benchmark_prompts"].items():
        for p in prompts:
            out[p["id"]] = p.get("difficulty", "unknown")
    return out


def load_summary() -> dict:
    with open(SUMMARY_FILE, encoding="utf-8") as f:
        return json.load(f)


# ── Level 2 — Reason consistency ──────────────────────────────────────────────

def compute_consistency(rows: list[dict]) -> dict:
    """
    Per row:
      CONSISTENT   : (score > 0.85 AND flag=False) OR (score < 0.7 AND flag=True)
      INCONSISTENT : (score > 0.85 AND flag=True)  OR (score < 0.7 AND flag=False)
      AMBIGUOUS    : score 0.7-0.85

    Secondary signal: reason sentiment crosscheck.
    """
    counts: dict[str, dict] = {j: {"consistent": 0, "inconsistent": 0, "ambiguous": 0,
                                   "text_consistent": 0, "text_inconsistent": 0,
                                   "total": 0} for j in JUDGES}
    by_domain: dict[str, dict] = defaultdict(lambda: {j: {"c": 0, "i": 0, "a": 0, "n": 0} for j in JUDGES})
    by_diff:   dict[str, dict] = defaultdict(lambda: {j: {"c": 0, "i": 0, "a": 0, "n": 0} for j in JUDGES})

    for row in rows:
        judge = row["judge"]
        if judge not in JUDGES:
            continue
        score, flag, reason = row["score"], row["flag"], row["reason"]
        uc, diff = row["use_case"], row["difficulty"]

        # Flag-based consistency
        if score > 0.85:
            cat = "inconsistent" if flag else "consistent"
        elif score < 0.7:
            cat = "consistent" if flag else "inconsistent"
        else:
            cat = "ambiguous"

        counts[judge][cat] += 1
        counts[judge]["total"] += 1
        by_domain[uc][judge][cat[0]] += 1
        by_domain[uc][judge]["n"] += 1
        by_diff[diff][judge][cat[0]] += 1
        by_diff[diff][judge]["n"] += 1

        # Text-based secondary check (only for non-ambiguous flag cases)
        if cat != "ambiguous":
            sentiment = _reason_sentiment(reason)
            expected_sentiment = "negative" if flag else "positive"
            if sentiment == expected_sentiment:
                counts[judge]["text_consistent"] += 1
            elif sentiment != "ambiguous":
                counts[judge]["text_inconsistent"] += 1

    # Aggregate
    result = {}
    for judge in JUDGES:
        c = counts[judge]
        total = c["total"] or 1
        non_amb = (c["consistent"] + c["inconsistent"]) or 1
        result[judge] = {
            "total_scores": c["total"],
            "consistent":   c["consistent"],
            "inconsistent": c["inconsistent"],
            "ambiguous":    c["ambiguous"],
            "consistency_rate":       _r(c["consistent"] / total),
            "inconsistency_rate":     _r(c["inconsistent"] / total),
            "text_confirm_rate":      _r(c["text_consistent"] / non_amb),
        }

    # By domain
    domain_result = {}
    for uc, jdict in sorted(by_domain.items()):
        domain_result[uc] = {}
        for judge in JUDGES:
            n = jdict[judge]["n"] or 1
            domain_result[uc][judge] = {
                "consistency_rate": _r(jdict[judge]["c"] / n),
                "n": jdict[judge]["n"],
            }

    # By difficulty
    diff_result = {}
    for diff in ["easy", "medium", "adversarial", "hard"]:
        jdict = by_diff[diff]
        diff_result[diff] = {}
        for judge in JUDGES:
            n = jdict[judge]["n"] or 1
            diff_result[diff][judge] = {
                "consistency_rate": _r(jdict[judge]["c"] / n),
                "n": jdict[judge]["n"],
            }

    return {"per_judge": result, "by_domain": domain_result, "by_difficulty": diff_result}


# ── Level 3 — Composite reliability ──────────────────────────────────────────

AGREEMENT_THRESHOLDS = {"high": 0.75, "low": 0.60}
CONSISTENCY_THRESHOLDS = {"high": 0.70, "low": 0.55}


def classify_judge(agreement: float, consistency: float) -> str:
    ag_high = agreement >= AGREEMENT_THRESHOLDS["high"]
    ag_low  = agreement < AGREEMENT_THRESHOLDS["low"]
    co_high = consistency >= CONSISTENCY_THRESHOLDS["high"]
    co_low  = consistency < CONSISTENCY_THRESHOLDS["low"]

    if ag_high and co_high:
        return "RELIABLE"
    if ag_high and co_low:
        return "LUCKY"        # reaches correct answers but reasoning is incoherent
    if not ag_low and co_high:
        return "CALIBRATED_BUT_STRICT"  # coherent reasoning, calibration offset
    return "UNRELIABLE"


def compute_level3(validity: dict, consistency: dict) -> dict:
    result = {}
    for judge in JUDGES:
        agr = validity["validity"][judge]["global"]
        con = consistency["per_judge"][judge]["consistency_rate"]
        classification = classify_judge(agr, con)
        result[judge] = {
            "agreement_rate":    _r(agr),
            "consistency_rate":  con,
            "classification":    classification,
            "note": _classification_note(judge, agr, con, validity["validity"][judge]),
        }
    return result


def _classification_note(judge: str, agr: float, con: float, validity_by_criterion: dict) -> str:
    weak_criteria = [c for c, v in validity_by_criterion.items()
                     if isinstance(v, dict) and v.get("agreement", 1.0) < 0.65
                     and c != "global"]
    note = f"agreement={agr:.1%}, consistency={con:.1%}"
    if weak_criteria:
        note += f"; weak on: {', '.join(weak_criteria)}"
    return note


# ── Bonus — High-disagreement reasons ────────────────────────────────────────

def extract_high_disagreement_reasons(
    rows: list[dict],
    summary: dict,
    sigma_threshold: float = 0.15,
) -> dict:
    top = summary["analysis_3_interjudge_disagreement_by_prompt"]["all_prompts"]
    high_sigma_pids = [
        pid for pid, v in sorted(top.items(), key=lambda x: x[1]["mean_interjudge_stdev"] or 0, reverse=True)
        if (v["mean_interjudge_stdev"] or 0) >= sigma_threshold
    ]

    # Index rows by (gen, judge, prompt_id)
    by_key: dict[tuple, list] = defaultdict(list)
    for row in rows:
        by_key[(row["gen"], row["judge"], row["prompt_id"])].append(row)

    result = {}
    for pid in high_sigma_pids:
        meta = top[pid]
        entry: dict = {
            "use_case":              meta["use_case"],
            "difficulty":            meta["difficulty"],
            "mean_interjudge_stdev": meta["mean_interjudge_stdev"],
            "by_generator":          {},
        }
        # All generators that have results for this prompt
        gens = sorted({row["gen"] for row in rows if row["prompt_id"] == pid})
        for gen in gens:
            by_judge: dict = {}
            for judge in JUDGES:
                key = (gen, judge, pid)
                crit_rows = by_key.get(key, [])
                if not crit_rows:
                    continue
                composite = crit_rows[0]["composite"]
                flagged = [r for r in crit_rows if r["flag"]]
                reasons = [f"{r['criterion']}: {r['reason']}" for r in crit_rows if r.get("reason")]
                by_judge[judge] = {
                    "composite_score": _r(composite),
                    "flagged_criteria": [r["criterion"] for r in flagged],
                    "reasons": reasons,
                }
            if by_judge:
                # Compute spread for this generator
                scores = [v["composite_score"] for v in by_judge.values() if v["composite_score"] is not None]
                import math
                mean_s = sum(scores) / len(scores) if scores else None
                std_s  = math.sqrt(sum((s - mean_s) ** 2 for s in scores) / (len(scores) - 1)) if len(scores) > 1 else None
                entry["by_generator"][gen] = {
                    "judge_scores": {j: v["composite_score"] for j, v in by_judge.items()},
                    "interjudge_stdev": _r(std_s),
                    "judge_details": by_judge,
                }
        result[pid] = entry

    return result


# ── phi4-mini transparency focus ──────────────────────────────────────────────

def phi4_transparency_focus(rows: list[dict]) -> dict:
    """
    phi4-mini scores only 55.4% agreement on transparency (validity.json, aggregated).
    Check whether its benchmark reasons on transparency-related entries are
    consistent with the score (calibration issue) or incoherent (reasoning failure).
    """
    target_criteria = {"transparency", "language_clarity", "explicability"}
    relevant = [
        r for r in rows
        if r["judge"] == "phi4-mini" and r["criterion"] in target_criteria
    ]

    inconsistent_cases = []
    consistent_cases   = []

    for row in relevant:
        score, flag, reason = row["score"], row["flag"], row["reason"]
        sentiment = _reason_sentiment(reason)

        if score > 0.85:
            if flag:
                inconsistent_cases.append({
                    "prompt_id": row["prompt_id"], "criterion": row["criterion"],
                    "score": score, "flag": flag, "reason": reason,
                    "label": "HIGH_SCORE_FLAGGED",
                })
            elif sentiment == "negative":
                inconsistent_cases.append({
                    "prompt_id": row["prompt_id"], "criterion": row["criterion"],
                    "score": score, "flag": flag, "reason": reason,
                    "label": "HIGH_SCORE_NEGATIVE_REASON",
                })
            else:
                consistent_cases.append({"score": score, "criterion": row["criterion"]})
        elif score < 0.7:
            if not flag and sentiment == "positive":
                inconsistent_cases.append({
                    "prompt_id": row["prompt_id"], "criterion": row["criterion"],
                    "score": score, "flag": flag, "reason": reason,
                    "label": "LOW_SCORE_POSITIVE_REASON",
                })
            else:
                consistent_cases.append({"score": score, "criterion": row["criterion"]})

    total = len(relevant)
    return {
        "total_transparency_related_scores": total,
        "inconsistent_count": len(inconsistent_cases),
        "consistent_count": len(consistent_cases),
        "inconsistency_rate": _r(len(inconsistent_cases) / total) if total else None,
        "interpretation": (
            "Calibration gap (severity threshold): score and reason agree internally, "
            "but phi4-mini's threshold for 'compliance' differs from ground truth"
            if len(inconsistent_cases) / total < 0.15
            else "Partial reasoning incoherence: score-reason conflicts detected beyond calibration noise"
        ),
        "inconsistent_examples": inconsistent_cases[:10],
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Loading data …")
    validity   = load_validity()
    rows       = load_benchmark()
    summary    = load_summary()
    diff_map   = load_prompt_difficulty()

    # Backfill proper difficulty from prompts.json
    for row in rows:
        row["difficulty"] = diff_map.get(row["prompt_id"], row["difficulty"])

    print(f"  {len(rows)} criteria-score rows loaded from benchmark")

    print("Level 2 — Reason consistency …")
    consistency = compute_consistency(rows)

    print("Level 3 — Composite reliability …")
    level3 = compute_level3(validity, consistency)

    print("Bonus — High-disagreement reasons …")
    high_sigma = extract_high_disagreement_reasons(rows, summary, sigma_threshold=0.15)

    print("phi4-mini transparency focus …")
    phi4_focus = phi4_transparency_focus(rows)

    output = {
        "level_1_agreement_rate": {
            judge: {
                "global": validity["validity"][judge]["global"],
                "by_criterion": {
                    c: v for c, v in validity["validity"][judge].items() if c != "global"
                },
            }
            for judge in JUDGES
        },
        "level_2_reason_consistency": consistency,
        "level_3_composite_reliability": level3,
        "phi4_transparency_focus": phi4_focus,
        "high_disagreement_reasons": high_sigma,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"Written: {OUTPUT_FILE}")

    # ── Terminal digest ───────────────────────────────────────────────────────

    print("\n" + "=" * 70)
    print("JUDGE RELIABILITY — COMPOSITE SUMMARY")
    print("=" * 70)
    print(f"\n{'Judge':<16} {'Agr.%':>6} {'Cons.%':>7} {'Class':<28} Note")
    print("-" * 70)
    for judge, v in level3.items():
        print(f"{judge:<16} {v['agreement_rate']:>5.1%}  {v['consistency_rate']:>5.1%}  "
              f"{v['classification']:<28} {v['note']}")

    print("\n" + "=" * 70)
    print("LEVEL 2 — CONSISTENCY RATE BY DOMAIN")
    print("=" * 70)
    header = f"{'Domain':<26}" + "".join(f"{j[:8]:>10}" for j in JUDGES)
    print(header)
    print("-" * 70)
    for uc, jdict in sorted(consistency["by_domain"].items()):
        row_s = f"{uc:<26}"
        for judge in JUDGES:
            v = jdict.get(judge, {})
            r = v.get("consistency_rate")
            row_s += f"  {r:.0%} ({v.get('n',0):>3})" if r is not None else f"{'—':>10}"
        print(row_s)

    print("\n" + "=" * 70)
    print("LEVEL 2 — CONSISTENCY RATE BY DIFFICULTY")
    print("=" * 70)
    print(header.replace("Domain", "Difficulty "))
    print("-" * 70)
    for diff in ["easy", "medium", "adversarial", "hard"]:
        jdict = consistency["by_difficulty"].get(diff, {})
        row_s = f"{diff:<26}"
        for judge in JUDGES:
            v = jdict.get(judge, {})
            r = v.get("consistency_rate")
            row_s += f"  {r:.0%} ({v.get('n',0):>3})" if r is not None else f"{'—':>10}"
        print(row_s)

    print("\n" + "=" * 70)
    print(f"phi4-mini TRANSPARENCY FOCUS")
    print("=" * 70)
    pf = phi4_focus
    print(f"  Scores analysés : {pf['total_transparency_related_scores']}")
    print(f"  Incohérents     : {pf['inconsistent_count']}  ({pf['inconsistency_rate']:.1%})")
    print(f"  Interprétation  : {pf['interpretation']}")
    if pf["inconsistent_examples"]:
        print("  Exemples d'incohérence :")
        for ex in pf["inconsistent_examples"][:5]:
            print(f"    [{ex['label']}] {ex['prompt_id']} / {ex['criterion']}")
            print(f"      score={ex['score']}  flag={ex['flag']}")
            print(f"      reason: {ex['reason'][:80]}")

    print("\n" + "=" * 70)
    print("HIGH-DISAGREEMENT REASONS (sigma >= 0.15)")
    print("=" * 70)
    for pid, entry in high_sigma.items():
        print(f"\n  {pid}  [{entry['use_case']} / {entry['difficulty']}]"
              f"  mean_sigma={entry['mean_interjudge_stdev']}")
        for gen, gdata in entry["by_generator"].items():
            print(f"    generator: {gen}  (sigma={gdata['interjudge_stdev']})")
            for judge, score in gdata["judge_scores"].items():
                flags = gdata["judge_details"][judge]["flagged_criteria"]
                flag_str = f"  [flagged: {', '.join(flags)}]" if flags else ""
                print(f"      {judge:<15} score={score}{flag_str}")


if __name__ == "__main__":
    main()
