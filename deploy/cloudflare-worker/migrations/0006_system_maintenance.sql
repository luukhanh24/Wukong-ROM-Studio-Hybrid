CREATE TABLE IF NOT EXISTS wukong_system_maintenance (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
    message TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT '',
    updated_by TEXT NOT NULL DEFAULT ''
);

INSERT OR IGNORE INTO wukong_system_maintenance (
    singleton,
    enabled,
    message,
    updated_at,
    updated_by
) VALUES (
    1,
    0,
    'Hệ thống đang được bảo trì. Vui lòng quay lại sau.',
    '',
    ''
);
