-- SEATWISEE relational schema (SQLite)
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS programs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    code           TEXT NOT NULL UNIQUE,
    name           TEXT NOT NULL,
    capacity       INTEGER NOT NULL CHECK (capacity >= 0),
    min_score      INTEGER NOT NULL DEFAULT 0,
    required_track TEXT,                       -- NULL = any track eligible
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS applicants (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    email      TEXT NOT NULL UNIQUE,
    score      INTEGER NOT NULL CHECK (score BETWEEN 0 AND 100),
    track      TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'withdrawn')),
    form_data       TEXT,                 -- JSON: responses to the admin-defined dynamic form
    marksheet_path  TEXT,                 -- uploads/<id>_12thMarksheet.<ext>
    scorecard_path  TEXT,                 -- uploads/<id>_EntranceScorecard.<ext>
    applied_at      TEXT NOT NULL DEFAULT (datetime('now')),  -- tie-break key
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Admin-configurable application form (rendered dynamically in the student portal).
CREATE TABLE IF NOT EXISTS form_schema (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    field_key  TEXT NOT NULL UNIQUE,      -- machine key stored in applicants.form_data JSON
    label      TEXT NOT NULL,
    field_type TEXT NOT NULL CHECK (field_type IN ('text', 'number', 'select')),
    required   INTEGER NOT NULL DEFAULT 1,
    options    TEXT,                      -- JSON list for select fields
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS preferences (
    applicant_id INTEGER NOT NULL REFERENCES applicants(id) ON DELETE CASCADE,
    program_id   INTEGER NOT NULL REFERENCES programs(id)   ON DELETE CASCADE,
    rank         INTEGER NOT NULL CHECK (rank >= 1),
    PRIMARY KEY (applicant_id, rank),
    UNIQUE (applicant_id, program_id)
);

-- Every solver invocation that is persisted becomes a run (version).
CREATE TABLE IF NOT EXISTS allocation_runs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    mode           TEXT NOT NULL,            -- initial | reassign | counterfactual
    solver_status  TEXT NOT NULL,            -- OPTIMAL | FEASIBLE | INFEASIBLE | UNKNOWN | MODEL_INVALID
    objective      REAL,
    best_bound     REAL,
    wall_time_s    REAL,
    preference_score INTEGER,
    assigned_count INTEGER,
    reassigned_count INTEGER,
    parent_run_id  INTEGER REFERENCES allocation_runs(id),
    is_current     INTEGER NOT NULL DEFAULT 0,
    notes          TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS assignments (
    run_id              INTEGER NOT NULL REFERENCES allocation_runs(id) ON DELETE CASCADE,
    applicant_id        INTEGER NOT NULL REFERENCES applicants(id),
    program_id          INTEGER REFERENCES programs(id),   -- NULL = unassigned
    rank_obtained       INTEGER,
    previous_program_id INTEGER REFERENCES programs(id),
    PRIMARY KEY (run_id, applicant_id)
);

CREATE TABLE IF NOT EXISTS capacity_changes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    program_id   INTEGER NOT NULL REFERENCES programs(id),
    old_capacity INTEGER NOT NULL,
    new_capacity INTEGER NOT NULL,
    reason       TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS appeals (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    applicant_id         INTEGER NOT NULL REFERENCES applicants(id),
    requested_program_id INTEGER NOT NULL REFERENCES programs(id),
    baseline_run_id      INTEGER REFERENCES allocation_runs(id),
    solver_status        TEXT,
    feasible             INTEGER,
    displaced_count      INTEGER,
    preference_delta     INTEGER,
    decision             TEXT NOT NULL DEFAULT 'evaluated',  -- evaluated | accepted | rejected
    result_json          TEXT,
    created_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT NOT NULL DEFAULT (datetime('now')),
    actor      TEXT NOT NULL,
    action     TEXT NOT NULL,
    details    TEXT
);

CREATE INDEX IF NOT EXISTS idx_assignments_run ON assignments(run_id);
CREATE INDEX IF NOT EXISTS idx_prefs_applicant ON preferences(applicant_id);

-- Admin-editable site text (CMS). Rendered dynamically on the landing page and student portal.
CREATE TABLE IF NOT EXISTS site_content (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    section_key  TEXT NOT NULL UNIQUE,
    content_text TEXT NOT NULL,
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
