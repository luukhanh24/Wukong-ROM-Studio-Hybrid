ALTER TABLE wukong_jobs
    ADD COLUMN dispatch_attempts INTEGER NOT NULL DEFAULT 0;

ALTER TABLE wukong_jobs
    ADD COLUMN dispatch_last_attempt_at TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS wukong_jobs_prebootstrap_recovery_idx
    ON wukong_jobs(status, stage, dispatch_last_attempt_at)
    WHERE finished_at = '';
