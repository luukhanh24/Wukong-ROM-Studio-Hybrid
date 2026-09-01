CREATE TABLE IF NOT EXISTS wukong_mirror_repair_outbox (
    job_id TEXT PRIMARY KEY,
    state TEXT NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending', 'sending', 'dispatched', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    dispatched_at TEXT NOT NULL DEFAULT '',
    last_error TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (job_id) REFERENCES wukong_jobs(job_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS wukong_mirror_repair_outbox_ready_idx
    ON wukong_mirror_repair_outbox(state, available_at);
