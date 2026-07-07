import { api, apiDownload } from "./client";
import type { ApiListEnvelope } from "./types";

/* -------------------------------------------------------------------------- */
/* Types                                                                      */
/* -------------------------------------------------------------------------- */

/**
 * One row from `GET /admin/audit-log`.
 * Field names are snake_case matching the backend schema exactly.
 */
export interface AuditRow {
  id: number;
  actor_id: string | null;
  actor_org_id: string | null;
  actor_email: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  occurred_at: string;
}

/** Query parameters for `GET /admin/audit-log` and the CSV export. */
export interface AuditLogParams {
  cursor?: string;
  limit?: number;
  actor_id?: string;
  action?: string;
  resource_type?: string;
  since?: string;
  until?: string;
}

/** The unwrapped page result returned by `auditLogApi.list`. */
export interface AuditLogPage {
  items: AuditRow[];
  next_cursor: string | null;
}

/* -------------------------------------------------------------------------- */
/* API object                                                                  */
/* -------------------------------------------------------------------------- */

export const auditLogApi = {
  /**
   * Cursor-paginated audit log entries.
   * `GET /admin/audit-log?cursor=&limit=&actor_id=&action=&resource_type=&since=&until=`
   * Uses `api.list` to unwrap the `paginated()` envelope:
   *   `{ data: AuditRow[], page: { next_cursor, limit } }`.
   */
  async list(params: AuditLogParams = {}): Promise<AuditLogPage> {
    const { cursor, limit, actor_id, action, resource_type, since, until } =
      params;
    const envelope: ApiListEnvelope<AuditRow> = await api.list<AuditRow>(
      "/admin/audit-log",
      {
        query: { cursor, limit, actor_id, action, resource_type, since, until },
      },
    );
    return {
      items: envelope.data,
      next_cursor: envelope.page.next_cursor,
    };
  },

  /**
   * Download filtered audit log as CSV.
   * `GET /admin/audit-log/export?actor_id=&action=&resource_type=&since=&until=`
   * Returns a Blob for browser download trigger.
   */
  exportCsv(
    params: Omit<AuditLogParams, "cursor" | "limit"> = {},
  ): Promise<Blob> {
    const { actor_id, action, resource_type, since, until } = params;
    return apiDownload("/admin/audit-log/export", {
      query: { actor_id, action, resource_type, since, until },
    });
  },
};
