import { api } from "./client";
import type {
  BulkModerationResultItem,
  JobVisibility,
  ModerationReasonCode,
  ModerationStatus,
} from "./jobs";
import type { ApiListEnvelope } from "./types";

/* ------------------------------- Vocabularies ----------------------------- */

export type EventType =
  | "career_fair"
  | "workshop"
  | "info_session"
  | "networking"
  | "webinar";

/** Event delivery mode (backend column `format`). */
export type EventFormat = "onsite" | "online" | "hybrid";

/**
 * Event lifecycle status (ADR-0008). Diverges from jobs intentionally: events
 * `publish`, `complete`, or `cancel` — they never "close". Edit/submit are only
 * legal in `draft`/`rejected`.
 */
export type EventStatus =
  | "draft"
  | "pending_review"
  | "published"
  | "cancelled"
  | "completed"
  | "rejected";

/** Events reuse the jobs visibility matrix + moderation vocabulary. */
export type EventVisibility = JobVisibility;
export type EventModerationStatus = ModerationStatus;

export const EVENT_STATUSES: EventStatus[] = [
  "draft",
  "pending_review",
  "published",
  "cancelled",
  "completed",
  "rejected",
];
export const EVENT_VISIBILITIES: EventVisibility[] = [
  "public",
  "authenticated",
  "students_only",
  "vinuni_only",
  "invitation_only",
];

/** A registrant's own registration state (never another attendee's). */
export type RegistrationState =
  | "confirmed"
  | "waitlisted"
  | "cancelled"
  | "attended"
  | "no_show";

export const EVENT_TYPES: EventType[] = [
  "career_fair",
  "workshop",
  "info_session",
  "networking",
  "webinar",
];
export const EVENT_FORMATS: EventFormat[] = ["onsite", "online", "hybrid"];

/* ------------------------------- Wire types ------------------------------- */

/** Venue block — present only for onsite/hybrid events (null for online). */
export interface EventVenue {
  name: string | null;
  address: string | null;
}

/**
 * Tiny organizer block embedded on public event projections. `logo_url` is
 * nullable — render an initials placeholder when null. `null` company means the
 * owning org is not currently listable; show the event without an org chip.
 */
export interface EventCompanyRef {
  slug: string;
  display_name: string;
  logo_url: string | null;
  is_verified: boolean;
}

/**
 * Public event summary (list rows + the `event` block on a registration). Never
 * carries moderation/owner internals. `cover_image_url` may be null (fall back to
 * the bundled hero asset). `seats_remaining` is null for unlimited-capacity
 * events; otherwise it is the live remaining confirmed seats (clamped at 0).
 */
export interface EventSummary {
  id: string;
  org_id: string;
  title: string;
  slug: string;
  event_type: string;
  event_type_label: string;
  format: string;
  format_label: string;
  cover_image_url: string | null;
  venue: EventVenue | null;
  starts_at: string;
  ends_at: string;
  timezone: string;
  registration_opens_at: string | null;
  registration_closes_at: string | null;
  capacity: number | null;
  registration_count: number;
  seats_remaining: number | null;
  is_featured: boolean;
  is_sponsored: boolean;
  tags: string[];
  published_at: string | null;
  /** Embedded organizer chip on the public list projection. */
  company?: EventCompanyRef | null;
}

/** Public discovery detail — adds the full description; no owner internals. */
export interface PublicEventDetail extends EventSummary {
  description: string;
}

/**
 * Owner/moderator list row (`GET /events/mine`, `GET /admin/events`) — the
 * public summary plus lifecycle + moderation + version fields.
 */
export interface OwnerEventSummary extends EventSummary {
  status: EventStatus;
  status_label: string;
  moderation_status: EventModerationStatus;
  moderation_status_label: string;
  moderation_reason_code?: ModerationReasonCode | string | null;
  moderation_reason_label?: string | null;
  visibility: EventVisibility;
  version: number;
  created_at: string;
  /** Moderation queue assignment (claim/SLA — university moderation only). */
  claimed_by?: string | null;
  claimed_at?: string | null;
  due_by?: string | null;
  age_hours?: number | null;
  is_overdue?: boolean;
}

/**
 * Full owner/moderator detail (org members of the owning org + university
 * moderators + superadmin). Adds the description + lifecycle/moderation metadata.
 */
export interface OwnerEventDetail extends PublicEventDetail {
  created_by: string;
  visibility: EventVisibility;
  status: EventStatus;
  status_label: string;
  moderation_status: EventModerationStatus;
  moderation_status_label: string;
  moderation_note: string | null;
  submitted_at: string | null;
  approved_at: string | null;
  cancelled_at: string | null;
  settings: Record<string, unknown>;
  version: number;
  created_at: string;
  updated_at: string;
}

/**
 * One attendee-list row (organizer/university only, ADR-0008 §3). `email` is
 * present **only** on the owning organizer's projection and absent for everyone
 * else — render it when defined, never assume it is always there.
 */
export interface EventAttendee {
  registration_id: string;
  display_name: string;
  status: RegistrationState;
  status_label: string;
  registered_at: string;
  checked_in_at: string | null;
  /** Organizer-only PII (legitimate event comms). Undefined for non-organizers. */
  email?: string | null;
}

/** Result of marking a registration as attended (idempotent). */
export interface CheckInResult {
  status: "attended";
  registration_id: string;
}

/* ------------------------------- Write bodies ----------------------------- */

export interface EventCreateBody {
  title: string;
  description: string;
  event_type: string;
  format: string;
  cover_image_path?: string | null;
  venue_name?: string | null;
  venue_address?: string | null;
  starts_at: string;
  ends_at: string;
  timezone?: string;
  registration_opens_at?: string | null;
  registration_closes_at?: string | null;
  capacity?: number | null;
  visibility?: string;
  tags?: string[];
}

export type EventUpdateBody = Partial<EventCreateBody> & { version?: number };

/**
 * The caller's own registration row ("My Events" + the register/cancel result).
 * `waitlist_position` is the 1-based FIFO slot when `status === "waitlisted"`,
 * otherwise null. No other attendee's identity is ever present here.
 */
export interface MyEventRegistration {
  registration_id: string;
  status: RegistrationState;
  status_label: string;
  waitlist_position: number | null;
  registered_at: string;
  checked_in_at: string | null;
  event: EventSummary;
}

/** Result of cancelling the caller's registration. */
export interface CancelRegistrationResult {
  status: "cancelled";
  registration_id: string;
}

/* --------------------------------- Calls ---------------------------------- */

export const eventsApi = {
  /* Public discovery (guest or any). Cursor pagination + server-side filters. */
  listPublic(opts?: {
    cursor?: string | null;
    limit?: number;
    q?: string | null;
    event_type?: string | null;
    format?: string | null;
  }): Promise<ApiListEnvelope<EventSummary>> {
    return api.list<EventSummary>("/events", {
      skipAuth: true,
      query: {
        cursor: opts?.cursor ?? undefined,
        limit: opts?.limit,
        q: opts?.q ?? undefined,
        event_type: opts?.event_type ?? undefined,
        format: opts?.format ?? undefined,
      },
    });
  },

  /**
   * Public event detail. The discovery detail route is keyed by the event UUID
   * (`id`), so callers pass `event.id` from a list row, not the slug.
   */
  getPublic(eventId: string): Promise<PublicEventDetail> {
    return api.get<PublicEventDetail>(`/events/${eventId}`);
  },

  /**
   * Register the caller for an event. Resolves to a registration whose `status`
   * is `confirmed` (a seat was held) OR `waitlisted` (event was full — note the
   * `waitlist_position`). Idempotent server-side for an existing active
   * registration. Guests receive a 401 (ApiError.isAuthError) → open login.
   */
  register(eventId: string): Promise<MyEventRegistration> {
    return api.post<MyEventRegistration>(`/events/${eventId}/register`, {});
  },

  /** Cancel the caller's registration (frees the seat; promotes the waitlist). */
  cancelRegistration(eventId: string): Promise<CancelRegistrationResult> {
    return api.delete<CancelRegistrationResult>(`/events/${eventId}/register`);
  },

  /** The caller's own registrations ("My Events"), newest event first. */
  myRegistrations(): Promise<MyEventRegistration[]> {
    return api.get<MyEventRegistration[]>("/events/registrations/mine");
  },

  /* ----------------------- Organizer (partner) management ----------------- */

  /** Owner/superadmin detail (full owner fields; cross-org → 404). */
  getOwned(eventId: string): Promise<OwnerEventDetail> {
    return api.get<OwnerEventDetail>(`/events/${eventId}`);
  },

  /** The caller org's events (any status). Cursor-paginated. */
  listMine(opts?: {
    cursor?: string | null;
    limit?: number;
    status?: string | null;
  }): Promise<ApiListEnvelope<OwnerEventSummary>> {
    return api.list<OwnerEventSummary>("/events/mine", {
      query: {
        cursor: opts?.cursor ?? undefined,
        limit: opts?.limit,
        status: opts?.status ?? undefined,
      },
    });
  },

  create(body: EventCreateBody): Promise<OwnerEventDetail> {
    return api.post<OwnerEventDetail>("/events", body);
  },

  update(eventId: string, body: EventUpdateBody): Promise<OwnerEventDetail> {
    return api.patch<OwnerEventDetail>(`/events/${eventId}`, body);
  },

  /**
   * Submit a draft/rejected event for review. Partner events go to
   * `pending_review`; university-created events auto-publish.
   */
  submit(eventId: string, version?: number): Promise<OwnerEventDetail> {
    return api.post<OwnerEventDetail>(`/events/${eventId}/submit`, { version });
  },

  /** Cancel a published event (notifies registrants). */
  cancel(eventId: string, version?: number): Promise<OwnerEventDetail> {
    return api.post<OwnerEventDetail>(`/events/${eventId}/cancel`, { version });
  },

  /** Soft-delete / archive a draft/rejected/cancelled/completed event. */
  remove(eventId: string): Promise<{ status: string }> {
    return api.delete<{ status: string }>(`/events/${eventId}`);
  },

  /* --------------------- Attendee list + check-in (staff) ----------------- */

  /**
   * Attendee list for the owning organizer / university staff (cross-org → 404).
   * `email` is present only on the organizer projection (ADR-0008 §3).
   */
  listRegistrations(eventId: string): Promise<EventAttendee[]> {
    return api.get<EventAttendee[]>(`/events/${eventId}/registrations`);
  },

  /** Mark a registration as attended (confirmed → attended; idempotent). */
  checkIn(eventId: string, registrationId: string): Promise<CheckInResult> {
    return api.post<CheckInResult>(
      `/events/${eventId}/registrations/${registrationId}/check-in`,
      {},
    );
  },

  /* ------------------------- University moderation ------------------------ */

  /** Moderation queue (default `pending_review`). University/superadmin only. */
  listModeration(status?: string | null): Promise<OwnerEventSummary[]> {
    return api.get<OwnerEventSummary[]>("/admin/events", {
      query: { status: status ?? undefined },
    });
  },

  /**
   * Approve + publish. Sent with no body (note/version optional server-side);
   * idempotent. `pending_review → published`.
   */
  approve(eventId: string): Promise<OwnerEventSummary> {
    return api.post<OwnerEventSummary>(`/admin/events/${eventId}/approve`);
  },

  /** Reject with a required coded reason. `pending_review → rejected`. */
  reject(
    eventId: string,
    reason: string,
    version?: number,
    reasonCode?: ModerationReasonCode | string,
  ): Promise<OwnerEventSummary> {
    return api.post<OwnerEventSummary>(`/admin/events/${eventId}/reject`, {
      reason,
      reason_code: reasonCode,
      version,
    });
  },

  /** Claim a pending event for review (concurrency-safe; 409 if already claimed). */
  claim(eventId: string): Promise<OwnerEventSummary> {
    return api.post<OwnerEventSummary>(`/admin/events/${eventId}/claim`);
  },

  /** Escalate an event to the shared human review queue. */
  escalate(
    eventId: string,
    opts?: { reason_code?: ModerationReasonCode | string; note?: string },
  ): Promise<OwnerEventSummary> {
    return api.post<OwnerEventSummary>(`/admin/events/${eventId}/escalate`, opts ?? {});
  },

  /** Approve multiple events; each item succeeds/fails independently. */
  bulkApprove(eventIds: string[]): Promise<BulkModerationResultItem[]> {
    return api.post<BulkModerationResultItem[]>("/admin/events/bulk-approve", {
      event_ids: eventIds,
    });
  },

  /** Reject multiple events; each item succeeds/fails independently. */
  bulkReject(
    items: { id: string; reason: string; reason_code?: ModerationReasonCode | string }[],
  ): Promise<BulkModerationResultItem[]> {
    return api.post<BulkModerationResultItem[]>("/admin/events/bulk-reject", { items });
  },
};
