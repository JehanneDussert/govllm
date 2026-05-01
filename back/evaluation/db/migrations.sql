-- SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
-- SPDX-License-Identifier: EUPL-1.2

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
    model_name      TEXT NOT NULL,      -- e.g. "ollama/qwen2.5:1.5b"
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

-- Indexes for frequent queries
CREATE INDEX IF NOT EXISTS idx_arena_sessions_profile    ON arena_sessions(profile_id);
CREATE INDEX IF NOT EXISTS idx_arena_sessions_created    ON arena_sessions(created_at);
CREATE INDEX IF NOT EXISTS idx_arena_judges_session      ON arena_judges(session_id);
CREATE INDEX IF NOT EXISTS idx_arena_judges_family       ON arena_judges(model_family);
CREATE INDEX IF NOT EXISTS idx_arena_criterion_session   ON arena_criterion_scores(session_id);
CREATE INDEX IF NOT EXISTS idx_arena_criterion_judge     ON arena_criterion_scores(judge_id);
CREATE INDEX IF NOT EXISTS idx_arena_criterion_id        ON arena_criterion_scores(criterion_id);