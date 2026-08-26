ALTER TABLE wukong_source_probe_sessions
    ADD COLUMN transport_mode TEXT NOT NULL DEFAULT 'direct'
        CHECK (transport_mode IN ('direct', 'vercel'));

CREATE TABLE IF NOT EXISTS wukong_source_transport_claims (
    token_hash TEXT PRIMARY KEY,
    operation TEXT NOT NULL CHECK (operation IN ('probe', 'range')),
    source_url TEXT NOT NULL,
    range_header TEXT NOT NULL DEFAULT '',
    maximum_bytes INTEGER NOT NULL CHECK (maximum_bytes > 0),
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    claimed_at INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS wukong_source_transport_claims_expiry_idx
    ON wukong_source_transport_claims(expires_at);
