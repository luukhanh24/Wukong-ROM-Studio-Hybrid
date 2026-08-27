const DEFAULT_MAINTENANCE_MESSAGE =
  "Hệ thống đang được bảo trì. Vui lòng quay lại sau.";
const MAX_MAINTENANCE_MESSAGE_LENGTH = 500;

interface MaintenanceRow {
  enabled: number;
  message: string;
  updated_at: string;
  updated_by: string;
}

export interface MaintenanceState {
  enabled: boolean;
  message: string;
  updatedAt: string;
  updatedBy: string;
}

function publicState(row: MaintenanceRow | null): MaintenanceState {
  return {
    enabled: row?.enabled === 1,
    message: row?.message || DEFAULT_MAINTENANCE_MESSAGE,
    updatedAt: row?.updated_at || "",
    updatedBy: row?.updated_by || ""
  };
}

export async function maintenanceState(env: Env): Promise<MaintenanceState> {
  const row = await env.DB.prepare(
    `SELECT enabled, message, updated_at, updated_by
       FROM wukong_system_maintenance
      WHERE singleton = 1`
  ).first<MaintenanceRow>();
  return publicState(row);
}

export async function setMaintenanceState(
  env: Env,
  subject: string,
  payload: Record<string, unknown>
): Promise<MaintenanceState> {
  if (typeof payload.enabled !== "boolean") {
    throw new Error("Maintenance enabled must be a boolean");
  }
  const previous = await maintenanceState(env);
  const message = String(payload.message ?? previous.message).trim();
  if (!message) throw new Error("Maintenance message is required");
  if (message.length > MAX_MAINTENANCE_MESSAGE_LENGTH) {
    throw new Error(`Maintenance message must not exceed ${MAX_MAINTENANCE_MESSAGE_LENGTH} characters`);
  }
  const updatedAt = new Date().toISOString();
  await env.DB.prepare(
    `INSERT INTO wukong_system_maintenance (
       singleton, enabled, message, updated_at, updated_by
     ) VALUES (1, ?, ?, ?, ?)
     ON CONFLICT(singleton) DO UPDATE SET
       enabled = excluded.enabled,
       message = excluded.message,
       updated_at = excluded.updated_at,
       updated_by = excluded.updated_by`
  ).bind(payload.enabled ? 1 : 0, message, updatedAt, subject).run();
  return {
    enabled: payload.enabled,
    message,
    updatedAt,
    updatedBy: subject
  };
}
