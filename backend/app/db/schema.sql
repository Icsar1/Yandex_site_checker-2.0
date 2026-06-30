PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    niche TEXT NOT NULL,
    region_ids TEXT NOT NULL DEFAULT '[]',
    region_label TEXT NOT NULL DEFAULT '',
    contact TEXT,
    status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','collecting_keys','forecasting','awaiting_manual','generating_text','rendering_pdf','done','failed','canceled')),
    attempts INTEGER NOT NULL DEFAULT 0,
    error_class TEXT,
    error_message TEXT,
    suggested_niche TEXT,
    search_masks TEXT,
    progress_pct INTEGER NOT NULL DEFAULT 0,
    stage TEXT,
    download_token TEXT UNIQUE,
    token_expires_at TEXT,
    source TEXT NOT NULL DEFAULT 'auto' CHECK(source IN ('auto','manual_xls')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    started_at TEXT,
    finished_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_token ON tasks(download_token);

CREATE TABLE IF NOT EXISTS task_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    level TEXT NOT NULL DEFAULT 'info',
    event TEXT NOT NULL,
    stage TEXT,
    message TEXT,
    meta TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_events_task_ts ON task_events(task_id, ts);

CREATE TABLE IF NOT EXISTS artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    kind TEXT NOT NULL CHECK(kind IN ('keywords','forecast','report_json','pdf','xls_upload')),
    path TEXT,
    payload TEXT,
    sha256 TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE(task_id, kind)
);
