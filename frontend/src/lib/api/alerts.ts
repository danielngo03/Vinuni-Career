import { api } from "./client";
import type { ApiListEnvelope } from "./types";

/* -------------------------------------------------------------------------- */
/* Types                                                                      */
/* -------------------------------------------------------------------------- */

export type AlertMetric =
  | "ai_spend_vs_budget_pct"
  | "ai_error_rate"
  | "queue_depth"
  | "outbox_failed";

export type AlertComparison = "gt" | "lt" | "gte" | "lte";

export type AlertSeverity = "info" | "warning" | "critical";

export type IncidentStatus = "open" | "acknowledged" | "resolved";

/** One alert rule row from `GET /admin/alerts/rules`. */
export interface AlertRule {
  id: string;
  name: string;
  metric: AlertMetric;
  comparison: AlertComparison;
  threshold: number;
  window_days: number;
  severity: AlertSeverity;
  enabled: boolean;
  channels: string[];
  updated_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface AlertRuleCreateBody {
  name: string;
  metric: AlertMetric;
  comparison: AlertComparison;
  threshold: number;
  window_days: number;
  severity: AlertSeverity;
  enabled: boolean;
  channels: string[];
}

export interface AlertRuleUpdateBody {
  name?: string;
  metric?: AlertMetric;
  comparison?: AlertComparison;
  threshold?: number;
  window_days?: number;
  severity?: AlertSeverity;
  enabled?: boolean;
  channels?: string[];
}

/** One incident row from `GET /admin/alerts/incidents`. */
export interface AlertIncident {
  id: string;
  rule_id: string;
  metric: AlertMetric;
  severity: AlertSeverity;
  status: IncidentStatus;
  message: string;
  value: number;
  threshold: number;
  triggered_at: string;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
  resolved_at: string | null;
  created_at: string;
}

export interface IncidentsParams {
  status?: IncidentStatus | "all";
  cursor?: string;
  limit?: number;
}

export interface IncidentsPage {
  items: AlertIncident[];
  next_cursor: string | null;
}

/* -------------------------------------------------------------------------- */
/* API object                                                                  */
/* -------------------------------------------------------------------------- */

export const alertsApi = {
  /**
   * List all alert rules.
   * `GET /admin/alerts/rules`
   * Backend returns `{ data: AlertRule[] }` — `api.get` unwraps to bare array.
   */
  listRules(): Promise<AlertRule[]> {
    return api.get<AlertRule[]>("/admin/alerts/rules");
  },

  /**
   * Create a new alert rule.
   * `POST /admin/alerts/rules`
   */
  createRule(body: AlertRuleCreateBody): Promise<AlertRule> {
    return api.post<AlertRule>("/admin/alerts/rules", body);
  },

  /**
   * Partially update an alert rule.
   * `PATCH /admin/alerts/rules/{id}`
   */
  updateRule(id: string, body: AlertRuleUpdateBody): Promise<AlertRule> {
    return api.patch<AlertRule>(`/admin/alerts/rules/${id}`, body);
  },

  /**
   * Delete an alert rule.
   * `DELETE /admin/alerts/rules/{id}`
   */
  deleteRule(id: string): Promise<void> {
    return api.delete(`/admin/alerts/rules/${id}`);
  },

  /**
   * Cursor-paginated incident list.
   * `GET /admin/alerts/incidents?status=&cursor=&limit=`
   * Uses `api.list` to unwrap the `paginated()` envelope:
   *   `{ data: AlertIncident[], page: { next_cursor, limit } }`.
   */
  async listIncidents(params: IncidentsParams = {}): Promise<IncidentsPage> {
    const { status, cursor, limit } = params;
    const queryStatus = status === "all" ? undefined : status;
    const envelope: ApiListEnvelope<AlertIncident> =
      await api.list<AlertIncident>("/admin/alerts/incidents", {
        query: { status: queryStatus, cursor, limit },
      });
    return {
      items: envelope.data,
      next_cursor: envelope.page.next_cursor,
    };
  },

  /**
   * Acknowledge an open incident.
   * `POST /admin/alerts/incidents/{id}/acknowledge`
   */
  acknowledgeIncident(id: string): Promise<AlertIncident> {
    return api.post<AlertIncident>(
      `/admin/alerts/incidents/${id}/acknowledge`,
      {},
    );
  },

  /**
   * Resolve an incident.
   * `POST /admin/alerts/incidents/{id}/resolve`
   */
  resolveIncident(id: string): Promise<AlertIncident> {
    return api.post<AlertIncident>(
      `/admin/alerts/incidents/${id}/resolve`,
      {},
    );
  },
};
