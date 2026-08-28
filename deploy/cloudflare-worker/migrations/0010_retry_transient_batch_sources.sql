ALTER TABLE wukong_batch_build_items
ADD COLUMN error_code TEXT NOT NULL DEFAULT '';

ALTER TABLE wukong_batch_build_items
ADD COLUMN source_attempts INTEGER NOT NULL DEFAULT 0;

ALTER TABLE wukong_batch_build_items
ADD COLUMN source_retry_at TEXT NOT NULL DEFAULT '';

UPDATE wukong_batch_build_items
SET status = 'pending_source',
    error = 'Nguồn ROM tạm thời gián đoạn; đang chờ thử lại',
    error_code = 'source_temporarily_unavailable',
    source_attempts = 1,
    source_retry_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
WHERE status = 'failed'
  AND job_id = ''
  AND (
    error LIKE 'ROM source transport %'
    OR error LIKE 'ROM catalog %'
  );

CREATE INDEX wukong_batch_items_source_retry_idx
ON wukong_batch_build_items(status, source_retry_at, created_at);

UPDATE wukong_batch_builds
SET status = 'running',
    finished_at = '',
    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
WHERE EXISTS (
  SELECT 1
  FROM wukong_batch_build_items AS item
  WHERE item.batch_id = wukong_batch_builds.batch_id
    AND item.status = 'pending_source'
);
