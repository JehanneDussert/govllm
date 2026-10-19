# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2

"""Unit tests for the checklist answer parser (services/groundtruth.py, pure functions).

Run inside the evaluation container:  python -m pytest tests/ -q
The response shapes below are the ones observed in ground truth runs; the parsing
rule is the same for every judge model.
"""

from services.groundtruth import (
    STATUS_EMPTY,
    STATUS_OK,
    STATUS_PARSE_ERROR,
    _extract_checklist_json,
    normalize_bool,
    parse_checklist_answers,
)

QIDS = ["q1", "q2", "q3", "q4"]


def test_normalize_bool_plain_values():
    assert normalize_bool(True) is True
    assert normalize_bool(False) is False
    assert normalize_bool("true") is True
    assert normalize_bool(" False ") is False
    assert normalize_bool("compliant") is True
    assert normalize_bool("violation") is False


def test_normalize_bool_echoed_template_label():
    # Judge copied the prompt template line "true (compliant) | false (violation)"
    assert normalize_bool("true (compliant)") is True
    assert normalize_bool("false (violation)") is False


def test_normalize_bool_rejects_non_answers():
    for v in ("<true|false>", "maybe", "", None, 1, "true | false", "yes"):
        assert normalize_bool(v) is None, v


def test_standard_answers_dict():
    answers, status, fallback = parse_checklist_answers(
        {"answers": {"q1": True, "q2": "false", "q3": "true", "q4": False}}, QIDS
    )
    assert status == STATUS_OK and fallback is None
    assert answers == {"q1": True, "q2": False, "q3": True, "q4": False}


def test_echoed_labels_are_usable():
    parsed = {"answers": {q: "true (compliant)" for q in QIDS}}
    answers, status, _ = parse_checklist_answers(parsed, QIDS)
    assert status == STATUS_OK and all(answers.values())


def test_positional_list():
    answers, status, fallback = parse_checklist_answers(
        {"answers": [True, False, True, True]}, QIDS
    )
    assert status == STATUS_OK and fallback == "positional_list"
    assert answers["q2"] is False


def test_top_level_keys_without_answers_wrapper():
    # Observed with LFM2.5-1.2B-Thinking: {"q4": true, "q3": true, ...}
    raw = '\n\n{\n  "q4": true,\n  "q3": true,\n  "q2": true,\n  "q1": false\n}\n\nSummary.'
    answers, status, fallback = parse_checklist_answers(_extract_checklist_json(raw), QIDS)
    assert status == STATUS_OK and fallback == "top_level_keys"
    assert answers == {"q1": False, "q2": True, "q3": True, "q4": True}


def test_no_answers_is_empty():
    assert parse_checklist_answers({"reason": "ok"}, QIDS)[1] == STATUS_EMPTY
    assert parse_checklist_answers({"answers": {}}, QIDS)[1] == STATUS_EMPTY


def test_incomplete_or_invalid_answers_are_parse_errors():
    # Missing q4
    _, status, _ = parse_checklist_answers({"answers": {"q1": True, "q2": True, "q3": True}}, QIDS)
    assert status == STATUS_PARSE_ERROR
    # Template placeholder copied verbatim
    _, status, _ = parse_checklist_answers({"answers": {q: "<true|false>" for q in QIDS}}, QIDS)
    assert status == STATUS_PARSE_ERROR
    # Analysis text instead of true/false (gemma3:4b failure mode)
    parsed = {"answers": {q: "The response does not mention any source." for q in QIDS}}
    assert parse_checklist_answers(parsed, QIDS)[1] == STATUS_PARSE_ERROR
