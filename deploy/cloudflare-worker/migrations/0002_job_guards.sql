CREATE TRIGGER IF NOT EXISTS wukong_job_access_guard
BEFORE INSERT ON wukong_jobs
WHEN NEW.owner_channel = 'telegram'
 AND COALESCE((
     SELECT value FROM wukong_control_plane_metadata WHERE key = 'd1_migration_mode'
 ), '') <> 'migration'
BEGIN
    SELECT (CASE
        WHEN NOT EXISTS (
            SELECT 1 FROM wukong_telegram_users
            WHERE subject = NEW.owner_subject AND access_status = 'approved'
        )
        THEN RAISE(ABORT, 'access_denied')
    END);
    SELECT (CASE
        WHEN EXISTS (
            SELECT 1 FROM wukong_telegram_users
            WHERE subject = NEW.owner_subject
              AND access_status = 'approved'
              AND unlimited = 0
              AND build_credits <= 0
        )
        THEN RAISE(ABORT, 'build_quota_exhausted')
    END);
END;
