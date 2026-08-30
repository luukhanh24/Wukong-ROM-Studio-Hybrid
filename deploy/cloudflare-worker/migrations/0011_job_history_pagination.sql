CREATE INDEX IF NOT EXISTS wukong_jobs_owner_created_idx
    ON wukong_jobs(owner_channel, owner_subject, created_at DESC, job_id DESC);

CREATE INDEX IF NOT EXISTS wukong_jobs_owner_status_created_idx
    ON wukong_jobs(owner_channel, owner_subject, status, created_at DESC, job_id DESC);

CREATE INDEX IF NOT EXISTS wukong_jobs_status_created_idx
    ON wukong_jobs(status, created_at DESC, job_id DESC);
