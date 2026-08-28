PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS wukong_batch_builds (
    batch_id TEXT PRIMARY KEY,
    owner_subject TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    release_version TEXT NOT NULL,
    editions_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'succeeded', 'partial', 'failed', 'cancelled')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT NOT NULL DEFAULT ''
);

CREATE UNIQUE INDEX IF NOT EXISTS wukong_batch_owner_request_idx
    ON wukong_batch_builds(owner_subject, idempotency_key);

CREATE TABLE IF NOT EXISTS wukong_batch_build_items (
    item_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    device TEXT NOT NULL,
    mod_version TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending_source'
        CHECK (status IN ('pending_source', 'resolving', 'job_created', 'source_failed', 'failed')),
    source_url TEXT NOT NULL DEFAULT '',
    source_version TEXT NOT NULL DEFAULT '',
    job_id TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (batch_id, device, mod_version),
    FOREIGN KEY (batch_id) REFERENCES wukong_batch_builds(batch_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS wukong_batch_items_pending_idx
    ON wukong_batch_build_items(status, created_at);

CREATE TABLE IF NOT EXISTS wukong_batch_build_events (
    event_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    item_id TEXT NOT NULL DEFAULT '',
    event_type TEXT NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (batch_id) REFERENCES wukong_batch_builds(batch_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS wukong_batch_events_idx
    ON wukong_batch_build_events(batch_id, created_at, event_id);
