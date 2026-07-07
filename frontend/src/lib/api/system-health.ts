import { api } from "./client";

/* -------------------------------------------------------------------------- */
/* Job health                                                                  */
/* -------------------------------------------------------------------------- */

/**
 * One row from `GET /admin/system-health/jobs`.
 * Field names match the backend schema exactly (snake_case).
 */
export interface JobHealth {
  name: string;
  interval_seconds: number;
  never_run: boolean;
  last_started_at: string | null;
  last_finished_at: string | null;
  last_duration_ms: number | null;
  last_status: "ok" | "error" | null;
  last_result: Record<string, unknown> | null;
}

/** Response for `GET /admin/system-health/jobs`. */
export interface SystemHealthJobs {
  jobs: JobHealth[];
}

/* -------------------------------------------------------------------------- */
/* Queue health                                                                */
/* -------------------------------------------------------------------------- */

/** Response for `GET /admin/system-health/queues`. */
export interface SystemHealthQueues {
  redis: "ok" | "down";
  celery_default_queue_depth: number | null;
  broker_configured: boolean;
}

/* -------------------------------------------------------------------------- */
/* Service health                                                              */
/* -------------------------------------------------------------------------- */

/** Outbox status sub-object inside `SystemHealthServices`. */
export interface OutboxHealth {
  pending: number;
  sent: number;
  failed: number;
  skipped: number;
  dead: number;
  oldest_pending_age_seconds: number | null;
  retry_scheduled: number;
}

/** Response for `GET /admin/system-health/services`. */
export interface SystemHealthServices {
  database: "ok" | "down";
  redis: "ok" | "down";
  outbox: OutboxHealth;
}

/* -------------------------------------------------------------------------- */
/* API object                                                                  */
/* -------------------------------------------------------------------------- */

export const systemHealthApi = {
  /**
   * Scheduled-job health registry.
   * `GET /admin/system-health/jobs`
   */
  jobs(): Promise<SystemHealthJobs> {
    return api.get<SystemHealthJobs>("/admin/system-health/jobs");
  },

  /**
   * Redis + Celery queue depth.
   * `GET /admin/system-health/queues`
   */
  queues(): Promise<SystemHealthQueues> {
    return api.get<SystemHealthQueues>("/admin/system-health/queues");
  },

  /**
   * DB + Redis readiness and outbox health.
   * `GET /admin/system-health/services`
   */
  services(): Promise<SystemHealthServices> {
    return api.get<SystemHealthServices>("/admin/system-health/services");
  },
};
