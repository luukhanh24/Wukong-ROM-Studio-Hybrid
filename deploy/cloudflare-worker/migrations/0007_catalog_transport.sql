-- Preserve in-flight claims while extending the operation constraint.
CREATE TABLE wukong_source_transport_claims_next (
    token_hash TEXT PRIMARY KEY,
    operation TEXT NOT NULL CHECK (operation IN ('probe', 'range', 'catalog')),
    source_url TEXT NOT NULL,
    range_header TEXT NOT NULL DEFAULT '',
    maximum_bytes INTEGER NOT NULL CHECK (maximum_bytes > 0),
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    claimed_at INTEGER NOT NULL DEFAULT 0
);
INSERT INTO wukong_source_transport_claims_next SELECT * FROM wukong_source_transport_claims;
DROP TABLE wukong_source_transport_claims;
ALTER TABLE wukong_source_transport_claims_next RENAME TO wukong_source_transport_claims;
CREATE INDEX wukong_source_transport_claims_expiry_idx ON wukong_source_transport_claims(expires_at);
