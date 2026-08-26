PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS wukong_telegram_access (
    subject TEXT PRIMARY KEY,
    role TEXT NOT NULL CHECK (role IN ('admin', 'user'))
);

CREATE TABLE IF NOT EXISTS wukong_telegram_users (
    subject TEXT PRIMARY KEY,
    username TEXT NOT NULL DEFAULT '',
    display_name TEXT NOT NULL DEFAULT '',
    photo_url TEXT NOT NULL DEFAULT '',
    access_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (access_status IN ('pending', 'approved', 'revoked')),
    role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    mini_app_open_count INTEGER NOT NULL DEFAULT 0,
    job_count INTEGER NOT NULL DEFAULT 0,
    build_credits INTEGER NOT NULL DEFAULT 0 CHECK (build_credits >= 0),
    unlimited INTEGER NOT NULL DEFAULT 0,
    lifetime_granted INTEGER NOT NULL DEFAULT 0,
    lifetime_used INTEGER NOT NULL DEFAULT 0,
    last_job_id TEXT NOT NULL DEFAULT '',
    last_job_status TEXT NOT NULL DEFAULT '',
    approved_at TEXT NOT NULL DEFAULT '',
    revoked_at TEXT NOT NULL DEFAULT '',
    access_actor TEXT NOT NULL DEFAULT '',
    access_reason TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT '',
    platform TEXT NOT NULL DEFAULT '',
    app_version TEXT NOT NULL DEFAULT '',
    configured_admin INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS wukong_telegram_users_seen_idx
    ON wukong_telegram_users(last_seen_at DESC);

CREATE TABLE IF NOT EXISTS wukong_telegram_user_events (
    event_id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor_subject TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (subject) REFERENCES wukong_telegram_users(subject) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS wukong_telegram_user_events_subject_idx
    ON wukong_telegram_user_events(subject, created_at DESC);

CREATE TABLE IF NOT EXISTS wukong_telegram_sessions (
    subject TEXT NOT NULL,
    session_id TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    PRIMARY KEY (subject, session_id),
    FOREIGN KEY (subject) REFERENCES wukong_telegram_users(subject) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS wukong_telegram_quota_ledger (
    ledger_id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    entry_type TEXT NOT NULL,
    delta INTEGER NOT NULL,
    balance_after INTEGER NOT NULL,
    job_id TEXT NOT NULL DEFAULT '',
    idempotency_key TEXT UNIQUE,
    consumed INTEGER NOT NULL DEFAULT 0,
    actor_subject TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (subject) REFERENCES wukong_telegram_users(subject) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS wukong_quota_subject_idx
    ON wukong_telegram_quota_ledger(subject, created_at DESC);

CREATE TABLE IF NOT EXISTS wukong_telegram_ui_state (
    subject TEXT PRIMARY KEY,
    language TEXT NOT NULL DEFAULT '',
    session_json TEXT NOT NULL DEFAULT '{}',
    job_refs_json TEXT NOT NULL DEFAULT '[]',
    conversation_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (subject) REFERENCES wukong_telegram_users(subject) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS wukong_telegram_pairings (
    pair_id TEXT PRIMARY KEY,
    secret_hash TEXT NOT NULL,
    user_id TEXT,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS wukong_pairings_expiry_idx
    ON wukong_telegram_pairings(expires_at);

CREATE TABLE IF NOT EXISTS wukong_telegram_source_drafts (
    subject TEXT PRIMARY KEY,
    uri TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS wukong_source_drafts_expiry_idx
    ON wukong_telegram_source_drafts(updated_at);

CREATE TABLE IF NOT EXISTS wukong_jobs (
    job_id TEXT PRIMARY KEY,
    manifest_json TEXT NOT NULL,
    recipe_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT NOT NULL DEFAULT '',
    next_event_sequence INTEGER NOT NULL DEFAULT 1,
    owner_channel TEXT NOT NULL,
    owner_subject TEXT NOT NULL,
    device TEXT NOT NULL,
    status TEXT NOT NULL,
    stage TEXT NOT NULL DEFAULT 'queued',
    progress REAL NOT NULL DEFAULT 0,
    github_run_id INTEGER,
    terminal_notified INTEGER NOT NULL DEFAULT 0,
    recipe_drive_ref TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS wukong_jobs_created_idx
    ON wukong_jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS wukong_jobs_active_owner_idx
    ON wukong_jobs(owner_channel, status, owner_subject);
CREATE INDEX IF NOT EXISTS wukong_jobs_active_device_idx
    ON wukong_jobs(owner_channel, status, device);
CREATE UNIQUE INDEX IF NOT EXISTS wukong_jobs_github_run_idx
    ON wukong_jobs(github_run_id) WHERE github_run_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS wukong_job_events (
    job_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (job_id, sequence),
    FOREIGN KEY (job_id) REFERENCES wukong_jobs(job_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS wukong_build_locks (
    lock_key TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    subject TEXT NOT NULL,
    device TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES wukong_jobs(job_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS wukong_build_locks_job_idx
    ON wukong_build_locks(job_id);

CREATE TABLE IF NOT EXISTS wukong_control_plane_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wukong_telegram_update_inbox (
    update_id INTEGER PRIMARY KEY,
    payload_json TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending', 'processing', 'processed', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    received_at TEXT NOT NULL,
    processed_at TEXT NOT NULL DEFAULT '',
    last_error TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS wukong_telegram_notification_outbox (
    notification_id TEXT PRIMARY KEY,
    dedupe_key TEXT NOT NULL UNIQUE,
    chat_id TEXT NOT NULL,
    method TEXT NOT NULL DEFAULT 'sendMessage',
    payload_json TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending', 'sending', 'sent', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    sent_at TEXT NOT NULL DEFAULT '',
    last_error TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS wukong_notification_outbox_ready_idx
    ON wukong_telegram_notification_outbox(state, available_at);

CREATE TABLE IF NOT EXISTS wukong_actions_callback_receipts (
    receipt_key TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    run_id INTEGER NOT NULL,
    callback_kind TEXT NOT NULL,
    sequence INTEGER NOT NULL DEFAULT 0,
    payload_hash TEXT NOT NULL,
    received_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES wukong_jobs(job_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS wukong_callback_receipts_job_idx
    ON wukong_actions_callback_receipts(job_id, received_at DESC);

CREATE TABLE IF NOT EXISTS wukong_source_probe_sessions (
    session_id TEXT PRIMARY KEY,
    owner_subject TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL,
    resolved_url TEXT NOT NULL,
    resolved_host TEXT NOT NULL,
    filename TEXT NOT NULL DEFAULT '',
    content_type TEXT NOT NULL DEFAULT '',
    size_bytes INTEGER,
    checksum_header TEXT NOT NULL DEFAULT '',
    signed_url_expires_at TEXT NOT NULL DEFAULT '',
    request_count INTEGER NOT NULL DEFAULT 0,
    bytes_served INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS wukong_probe_sessions_expiry_idx
    ON wukong_source_probe_sessions(expires_at);
