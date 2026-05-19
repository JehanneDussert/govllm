-- SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
-- SPDX-License-Identifier: EUPL-1.2

SET search_path TO govllm;

-- Arena sessions — one row per Arena run
CREATE TABLE IF NOT EXISTS arena_sessions (
    session_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prompt          TEXT NOT NULL,
    profile_id      TEXT NOT NULL,
    use_case_id     TEXT,
    sigma           FLOAT,              -- inter-judge variance across all criteria
    user_vote       TEXT,               -- model_name chosen by user, null until voted
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Arena judges — one row per judge per session
CREATE TABLE IF NOT EXISTS arena_judges (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL REFERENCES arena_sessions(session_id) ON DELETE CASCADE,
    model_name      TEXT NOT NULL,      -- e.g. "ollama/phi4-mini"
    model_family    TEXT NOT NULL,      -- e.g. "qwen" — for bias matrix grouping
    assigned_criteria TEXT[] NOT NULL,  -- criterion ids this judge was assigned
    global_score    FLOAT,              -- weighted composite over assigned criteria
    latency_ms      INT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Arena criterion scores — one row per criterion per judge per session
CREATE TABLE IF NOT EXISTS arena_criterion_scores (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL REFERENCES arena_sessions(session_id) ON DELETE CASCADE,
    judge_id        UUID NOT NULL REFERENCES arena_judges(id) ON DELETE CASCADE,
    criterion_id    TEXT NOT NULL,      -- e.g. "non_manipulation"
    score           FLOAT NOT NULL,     -- 0.0 to 1.0
    flag            BOOLEAN NOT NULL DEFAULT false,
    reason          TEXT,               -- judge explanation (max ~50 words)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Model lifecycle — one row per zone transition
CREATE TABLE IF NOT EXISTS model_lifecycle (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model        TEXT NOT NULL,
    zone         TEXT NOT NULL CHECK (zone IN ('test', 'validation', 'production', 'quarantine')),
    score        FLOAT,           -- score that triggered the transition (SAS or drift)
    criterion_id TEXT,            -- criterion that triggered quarantine (if applicable)
    profile_id   TEXT,
    operator     TEXT NOT NULL DEFAULT 'auto',  -- 'human' | 'auto' | 'sas'
    note         TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_lifecycle_model   ON model_lifecycle(model);
CREATE INDEX IF NOT EXISTS idx_lifecycle_created ON model_lifecycle(created_at);

-- Indexes for frequent queries
CREATE INDEX IF NOT EXISTS idx_arena_sessions_profile    ON arena_sessions(profile_id);
CREATE INDEX IF NOT EXISTS idx_arena_sessions_created    ON arena_sessions(created_at);
CREATE INDEX IF NOT EXISTS idx_arena_judges_session      ON arena_judges(session_id);
CREATE INDEX IF NOT EXISTS idx_arena_judges_family       ON arena_judges(model_family);
CREATE INDEX IF NOT EXISTS idx_arena_criterion_session   ON arena_criterion_scores(session_id);
CREATE INDEX IF NOT EXISTS idx_arena_criterion_judge     ON arena_criterion_scores(judge_id);
CREATE INDEX IF NOT EXISTS idx_arena_criterion_id        ON arena_criterion_scores(criterion_id);

-- Ground truth corpus — regulatory test cases with expert-validated expected answers
CREATE TABLE IF NOT EXISTS groundtruth_cases (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    criterion   TEXT NOT NULL,   -- criterion_id, e.g. "transparency"
    prompt      TEXT NOT NULL,   -- original user question
    response    TEXT NOT NULL,   -- AI response being evaluated
    source      TEXT,            -- origin (e.g. "CNIL deliberation 2024-xxx")
    expected    TEXT NOT NULL,   -- JSON: {"q1": true, "q2": false, ...} — True=compliant
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Ground truth results — one row per judge per corpus run
CREATE TABLE IF NOT EXISTS groundtruth_results (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id      UUID NOT NULL REFERENCES groundtruth_cases(id) ON DELETE CASCADE,
    judge_model  TEXT NOT NULL,
    judge_family TEXT NOT NULL,
    answers      TEXT NOT NULL,  -- JSON: {"q1": true, ...} — True=compliant
    score        FLOAT NOT NULL, -- mean(answers.values())
    agreement    FLOAT NOT NULL, -- fraction of answers matching expected
    reason       TEXT,
    latency_ms   INT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_gt_cases_criterion  ON groundtruth_cases(criterion);
CREATE INDEX IF NOT EXISTS idx_gt_results_case     ON groundtruth_results(case_id);
CREATE INDEX IF NOT EXISTS idx_gt_results_judge    ON groundtruth_results(judge_model);

-- Production eval scores — audit-grade persistence (AI Act Art. 9)
-- Redis is the hot cache (TTL 7 d); this table is the authoritative long-term record.
CREATE TABLE IF NOT EXISTS eval_results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id        TEXT NOT NULL,
    model           TEXT NOT NULL,
    use_case_id     TEXT,
    profile_id      TEXT,
    composite_score FLOAT NOT NULL,
    criteria_scores JSONB NOT NULL DEFAULT '[]',
    evaluated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_eval_results_trace   ON eval_results(trace_id);
CREATE INDEX IF NOT EXISTS idx_eval_results_model   ON eval_results(model, use_case_id);
CREATE INDEX IF NOT EXISTS idx_eval_results_created ON eval_results(evaluated_at);