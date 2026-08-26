CREATE TRIGGER IF NOT EXISTS wukong_job_global_concurrency_guard
BEFORE INSERT ON wukong_jobs
WHEN NEW.owner_channel = 'telegram'
 AND COALESCE((
     SELECT value FROM wukong_control_plane_metadata WHERE key = 'd1_migration_mode'
 ), '') <> 'migration'
 AND (
     SELECT COUNT(*) FROM wukong_jobs
     WHERE status NOT IN ('succeeded', 'failed', 'cancelled')
 ) >= 20
BEGIN
    SELECT RAISE(ABORT, 'build_concurrency_limit');
END;
