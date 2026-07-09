import { api, apiFetch } from "./client";

/* ------------------------------- Vocabularies ----------------------------- */

/**
 * Known notification kinds surfaced by the backend. Kept as a string-open union
 * so a new server-side type never breaks rendering (falls back to a default
 * icon + the server-localized title/body).
 */
export type NotifType =
  | "recruitment.reveal_requested"
  | "recruitment.reveal_responded"
  | "recruitment.application_received"
  | "recruitment.application_under_review"
  | "recruitment.application_stage_advanced"
  | "recruitment.application_under_rereview"
  | "recruitment.application_rejected"
  | "recruitment.interview_scheduled"
  | "recruitment.interview_rescheduled"
  | "recruitment.interview_cancelled"
  | "recruitment.interview_reminder"
  | "recruitment.interview_assigned"
  | "recruitment.interview_reminder_assignee"
  | "recruitment.offer_received"
  | "recruitment.offer_expiring"
  | "recruitment.offer_expired"
  | "recruitment.offer_accepted"
  | "recruitment.offer_declined"
  | "recruitment.offer_rescinded"
  | "opportunities.job_approved"
  | "opportunities.job_rejected"
  | "opportunities.job_auto_closed"
  | "opportunities.event_registration_confirmed"
  | "opportunities.event_waitlisted"
  | "opportunities.event_waitlist_promoted"
  | "opportunities.event_cancelled"
  | "opportunities.event_reminder"
  | "organization.partner_approved"
  | "message.received"
  | "message.request_accepted"
  | "message.flagged"
  | "messaging.thread_assigned"
  | "advertising.placement_approved"
  | "advertising.placement_rejected"
  | (string & {});

/* ------------------------------- Wire types ------------------------------- */

/**
 * A single bell-center notification. `title`/`body` arrive already localized
 * and user-safe from the server — render verbatim, never re-interpret. Never
 * contains AI/provider internals. `action_url` is a non-locale app path.
 */
export interface Notification {
  id: string;
  notif_type: NotifType;
  title: string;
  body: string;
  action_url: string | null;
  is_read: boolean;
  created_at: string;
}

/** Cursor page descriptor for the notifications feed. */
export interface NotificationPage {
  next_cursor: string | null;
  limit: number;
}

/**
 * `GET /notifications` response. Carries the live `unread_count` in `meta` so
 * the badge can be reconciled from the same fetch that hydrates the list.
 */
export interface NotificationListResponse {
  data: Notification[];
  page: NotificationPage;
  meta: { unread_count: number };
}

/** `POST /notifications/{id}/read` result. */
export interface MarkReadResult {
  status: "ok" | string;
  id: string;
  is_read: true;
  unread_count: number;
}

/** `POST /notifications/read-all` result. */
export interface MarkAllReadResult {
  updated: number;
  unread_count: number;
}

/* --------------------------------- Calls ---------------------------------- */

export const notificationsApi = {
  /** Bell-center feed, newest first, cursor paginated. */
  list(opts?: {
    cursor?: string | null;
    limit?: number;
    unreadOnly?: boolean;
  }): Promise<NotificationListResponse> {
    return apiFetch<NotificationListResponse>("/notifications", {
      method: "GET",
      query: {
        cursor: opts?.cursor ?? undefined,
        limit: opts?.limit,
        // Only send the filter when explicitly on, so the default feed shows all.
        unread_only: opts?.unreadOnly ? true : undefined,
      },
    });
  },

  /** Lightweight badge poll. Returns the current unread total. */
  async unreadCount(): Promise<number> {
    const data = await api.get<{ unread_count: number }>(
      "/notifications/unread-count",
    );
    return data.unread_count;
  },

  /** Mark one notification read (idempotent). Returns the fresh unread total. */
  markRead(id: string): Promise<MarkReadResult> {
    return api.post<MarkReadResult>(`/notifications/${id}/read`, {});
  },

  /** Mark every notification read. Returns how many changed + unread_count: 0. */
  markAllRead(): Promise<MarkAllReadResult> {
    return api.post<MarkAllReadResult>("/notifications/read-all", {});
  },
};

/* ---------------------- Notification template governance ------------------ */

export type NotificationTemplateChannel = "email" | "in_app" | "push";
export type NotificationTemplateLocale = "vi" | "en";
export type NotificationTemplateStatus = "draft" | "active" | "archived";

export const NOTIFICATION_TEMPLATE_CHANNELS: NotificationTemplateChannel[] = [
  "email",
  "in_app",
  "push",
];
export const NOTIFICATION_TEMPLATE_LOCALES: NotificationTemplateLocale[] = [
  "vi",
  "en",
];
export const NOTIFICATION_TEMPLATE_STATUSES: NotificationTemplateStatus[] = [
  "draft",
  "active",
  "archived",
];

/** Declared placeholder vocabulary for one template version. */
export interface NotificationTemplateVariablesSchema {
  allowed: string[];
  required: string[];
}

/**
 * A single template version row (`_presenter` in `template_admin_service.py`).
 * Every (key, channel, locale) identity can have many versions; exactly one may
 * be `active` at a time. Editing an active/archived row is not allowed — a
 * caller must `create` a new version instead.
 */
export interface NotificationTemplate {
  id: string;
  owner_scope: string;
  owner_org_id: string | null;
  key: string;
  channel: NotificationTemplateChannel | string;
  locale: NotificationTemplateLocale | string;
  version: number;
  status: NotificationTemplateStatus | string;
  subject: string | null;
  title: string | null;
  body: string;
  variables_schema: NotificationTemplateVariablesSchema;
  created_by: string | null;
  updated_by: string | null;
  activated_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface NotificationTemplateCreateBody {
  key: string;
  channel: NotificationTemplateChannel | string;
  locale: NotificationTemplateLocale | string;
  subject?: string | null;
  title?: string | null;
  body: string;
  variables_schema?: NotificationTemplateVariablesSchema;
}

export type NotificationTemplateUpdateBody = Partial<
  Pick<NotificationTemplateCreateBody, "subject" | "title" | "body" | "variables_schema">
>;

/** Rendered preview (no send). `required_variables` never omits a real requirement. */
export interface NotificationTemplatePreviewResult {
  template_id: string;
  locale: string;
  channel: string;
  subject: string | null;
  title: string | null;
  body: string;
  required_variables: string[];
}

export const templateAdminApi = {
  /** List templates (all versions) visible to the caller's org. */
  list(opts?: {
    key?: string | null;
    channel?: string | null;
    locale?: string | null;
    status?: string | null;
  }): Promise<NotificationTemplate[]> {
    return api.get<NotificationTemplate[]>("/notification-templates", {
      query: {
        key: opts?.key ?? undefined,
        channel: opts?.channel ?? undefined,
        locale: opts?.locale ?? undefined,
        status: opts?.status ?? undefined,
      },
    });
  },

  /** Create a new draft (or a new version if the identity already exists). */
  create(body: NotificationTemplateCreateBody): Promise<NotificationTemplate> {
    return api.post<NotificationTemplate>("/notification-templates", body);
  },

  /** Update a draft in place. 409 if the template is no longer a draft. */
  update(
    templateId: string,
    body: NotificationTemplateUpdateBody,
  ): Promise<NotificationTemplate> {
    return api.patch<NotificationTemplate>(
      `/notification-templates/${templateId}`,
      body,
    );
  },

  /** Render subject/body with sample or caller-supplied variables. Never sends. */
  preview(
    templateId: string,
    sampleVariables?: Record<string, string>,
  ): Promise<NotificationTemplatePreviewResult> {
    return api.post<NotificationTemplatePreviewResult>(
      `/notification-templates/${templateId}/preview`,
      { sample_variables: sampleVariables ?? {} },
    );
  },

  /** Publish this version, archiving whichever version was previously active. */
  activate(templateId: string): Promise<NotificationTemplate> {
    return api.post<NotificationTemplate>(
      `/notification-templates/${templateId}/activate`,
      {},
    );
  },

  /** Retire a draft/active version without activating a replacement. */
  archive(templateId: string): Promise<NotificationTemplate> {
    return api.post<NotificationTemplate>(
      `/notification-templates/${templateId}/archive`,
      {},
    );
  },
};
