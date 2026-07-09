import { api, apiDownload } from "./client";
import type { ApiListEnvelope } from "./types";

/* ------------------------------- Vocabularies ----------------------------- */

/** Thread kind. `announcement` recipients are one-way (read-only). */
export type ThreadKind = "direct" | "announcement";

/**
 * Thread context. Drives masking + initiation rules server-side:
 * - `application` — partner↔candidate, bound to an application (anonymity-masked
 *   until reveal).
 * - `support` — student/alumni → university.
 * - `team` — same-org partner members.
 * Kept as a string-open union so an unknown server value never breaks rendering.
 */
export type ThreadContextType =
  | "application"
  | "support"
  | "team"
  | (string & {});

/** Thread lifecycle. `closed`/`archived` block sends (409 on POST). */
export type ThreadStatus = "active" | "archived" | "closed" | (string & {});

/**
 * Messaging V2 thread discriminator. Distinguishes the party axes an inbox row
 * can represent. Kept string-open so an unknown server value never breaks render.
 */
export type ThreadKindV2 =
  | "org_dm"
  | "org_to_org"
  | "internal"
  | "application"
  | "support"
  | "announcement"
  | (string & {});

/**
 * First-contact "message request" gate state. A brand-new conversation between
 * two parties starts `pending`; the recipient accepts/declines/blocks. Privileged
 * axes (university-initiated, internal, application-backed) start `accepted`.
 */
export type RequestState =
  | "accepted"
  | "pending"
  | "declined"
  | "blocked"
  | (string & {});

/** Org shared-inbox routing state for a thread (partner/university personas). */
export type AssignmentState =
  | "unassigned"
  | "assigned"
  | "resolved"
  | (string & {});

/* ------------------------------- Wire types ------------------------------- */

/**
 * A thread row in the inbox. Every identity field is a SERVER-rendered label
 * (`counterpart_label`, participant `label`, message `sender_label`) — the
 * anonymity decision lives in the backend `thread_view` projection. The UI must
 * NEVER reconstruct, store, or display a student's name/email; it renders the
 * server label verbatim (an anonymous handle for the partner side until reveal).
 */
export interface ThreadSummary {
  id: string;
  kind: ThreadKind;
  kind_label: string;
  context_type: ThreadContextType | null;
  context_label: string | null;
  subject: string | null;
  /** Masked-or-real label for the OTHER side (server-decided). */
  counterpart_label: string;
  status: ThreadStatus;
  status_label: string;
  is_anonymous: boolean;
  /**
   * V2 party-axis discriminator (org_dm/org_to_org/internal/application/…). The
   * legacy `kind` column stays direct/announcement; this is the richer axis.
   */
  thread_kind: ThreadKindV2;
  /** First-contact request-gate state (accepted for privileged/internal axes). */
  request_state: RequestState;
  /** Server-rendered, localized label for `request_state` (render verbatim). */
  request_label: string;
  /** Intro messages the initiator has sent while pending (for the counter). */
  request_message_count: number;
  /** Max intro messages allowed before the recipient must accept. */
  request_message_limit: number;
  unread: number;
  can_reply: boolean;
  muted: boolean;
  last_message_at: string | null;
}

/**
 * A thread row inside an ORG shared inbox (`GET /inbox`). Extends the summary with
 * team-routing fields: whether it is unassigned/assigned/resolved and, when routed,
 * the raw department/assignee ids (resolved to names in the UI via pickers — never
 * shown as raw ids to operators).
 */
export interface InboxThreadSummary extends ThreadSummary {
  assignment_state: AssignmentState;
  assigned_department_id: string | null;
  assigned_user_id: string | null;
}

/** One rendered participant (label is masked-or-real per the server). */
export interface ThreadParticipant {
  label: string;
  can_reply: boolean;
  role_in_thread: string;
}

/** Thread detail = summary + the rendered participant roster. */
export interface ThreadDetail extends ThreadSummary {
  participants: ThreadParticipant[];
  /**
   * True only when this thread is a `pending` request AND the viewer is the
   * recipient party (the one who accepts/declines/blocks). Authoritative — use
   * this to decide the Accept/Decline/Block bar instead of inferring client-side.
   */
  viewer_is_recipient: boolean;
  /**
   * True when the viewer is the recipient party (the side that did NOT initiate),
   * regardless of request state. The recipient controls the gate across the whole
   * conversation life — use this to offer Unblock on a `blocked` thread and Reopen
   * on a `declined` one. The initiator never sees these controls.
   */
  viewer_is_recipient_party: boolean;
}

/**
 * A single message. `body` is markdown-lite and MUST be rendered through the
 * sanitizing renderer (never `dangerouslySetInnerHTML`). `sender_label` is the
 * masked-or-real server label; for system/announcement rows it is the system
 * label. A soft-deleted row arrives with `is_deleted=true` and a neutral body.
 */
export interface Message {
  id: string;
  body: string;
  is_system: boolean;
  is_mine: boolean;
  is_deleted: boolean;
  sender_label: string;
  reply_to_id: string | null;
  /** Bound attachments (empty on a soft-deleted message). */
  attachments: MessageAttachment[];
  created_at: string;
}

/** Attachment kind: an inline image or a downloadable file. */
export type MessageAttachmentKind = "image" | "file";

/**
 * A message attachment. `url` (`/api/v1/messaging/attachments/{id}`) is a GATED
 * endpoint requiring the Bearer token — fetch it authenticated (never a plain
 * `<img src>`), the storage key/path is never exposed.
 */
export interface MessageAttachment {
  id: string;
  kind: MessageAttachmentKind;
  file_name: string;
  content_type: string;
  size_bytes: number;
  width?: number | null;
  height?: number | null;
  url: string;
}

/** `POST /messaging/threads/{id}/read` result. */
export interface MarkReadResult {
  status: string;
  thread_id: string;
  unread: number;
}

/** `POST /messaging/threads/{id}/mute` result. */
export interface MuteResult {
  status: string;
  thread_id: string;
  muted: boolean;
}

/** `DELETE /messaging/threads/{id}/messages/{mid}` result. */
export interface DeleteMessageResult {
  status: string;
  id: string;
}

/** `POST /messaging/threads/{id}/report` result. */
export interface ReportThreadResult {
  status: string;
  thread_id: string;
}

/** `POST /messaging/threads/{id}/request/{action}` result. */
export interface RequestActionResult {
  status: string;
  thread_id: string;
  request_state: RequestState;
}

/** `POST /messaging/threads/{id}/assign` result. */
export interface AssignThreadResult {
  status: string;
  thread_id: string;
  assignment_state: AssignmentState;
  assigned_department_id: string | null;
  assigned_user_id: string | null;
}

/** `POST /messaging/threads/{id}/resolve` result. */
export interface ResolveThreadResult {
  status: string;
  thread_id: string;
  assignment_state: AssignmentState;
}

/** `POST /messaging/inbox/{id}/read` result (team-level read cursor). */
export interface InboxReadResult {
  status: string;
  thread_id: string;
  unread: number;
}

/* ----------------------------- Recipient search --------------------------- */

/** An organization Page target (student/partner → partner/university). */
export interface RecipientOrg {
  kind: "org";
  org_id: string;
  slug: string;
  display_name: string;
  org_type: "partner" | "university" | (string & {});
  is_verified: boolean;
  /** Safe logo URL when the search projection provides one (else initials). */
  logo_url?: string | null;
}

/** An internal department channel target (staff, own org). */
export interface RecipientDepartment {
  kind: "department";
  department_id: string;
  display_name: string;
}

/** A colleague target (staff, own org). */
export interface RecipientUser {
  kind: "user";
  user_id: string;
  display_name: string;
}

/**
 * A typed recipient the composer may offer. The permission matrix is enforced at
 * the SEARCH layer server-side: students only ever receive `org` targets (they can
 * never discover another student).
 */
export type RecipientTarget =
  | RecipientOrg
  | RecipientDepartment
  | RecipientUser;

/** Org-inbox scope filter (team triage). */
export type InboxScope = "unassigned" | "mine" | "all" | "resolved";

/** Message-request action the recipient may take on a `pending` thread. */
export type RequestAction = "accept" | "decline" | "block" | "unblock";

/* --------------------------------- Inputs --------------------------------- */

/**
 * Create-thread body. The permission matrix is RE-ENFORCED server-side; the UI
 * only ever offers an allowed shape:
 * - partner→candidate REQUIRES `context_type='application'` + `context_id` +
 *   the applicant in `recipient_ids`.
 * - student/alumni CANNOT initiate to a student or cold to a partner (the UI
 *   never exposes such a path).
 */
export interface CreateThreadBody {
  kind?: ThreadKind;
  context_type?: ThreadContextType | null;
  context_id?: string | null;
  /** User recipients (internal colleagues, university→user). Defaults to `[]`. */
  recipient_ids?: string[];
  /** V2: initiate to an org Page (student→org, partner→university). */
  target_org_id?: string | null;
  /** V2: internal department channel (same org, staff only). */
  target_department_id?: string | null;
  subject?: string | null;
  first_message?: string | null;
}

/** Send-message body. `client_dedupe_key` makes a retry idempotent. */
export interface SendMessageBody {
  body: string;
  reply_to_id?: string | null;
  client_dedupe_key?: string | null;
  /**
   * V2 (optional): bind previously-uploaded attachments to this message. The
   * upload UI is handled separately; this field stays optional so the composer
   * can pass ids once that surface exists.
   */
  attachment_ids?: string[];
}

/* --------------------------------- Calls ---------------------------------- */

export const messagingApi = {
  /** My threads, masked + per-thread unread, sorted `last_message_at DESC`. */
  listThreads(opts?: {
    cursor?: string | null;
    limit?: number;
  }): Promise<ApiListEnvelope<ThreadSummary>> {
    return api.list<ThreadSummary>("/messaging/threads", {
      query: { cursor: opts?.cursor ?? undefined, limit: opts?.limit },
    });
  },

  /** Create a thread within the permission matrix (server re-checks). */
  createThread(body: CreateThreadBody): Promise<ThreadSummary> {
    return api.post<ThreadSummary>("/messaging/threads", {
      kind: body.kind ?? "direct",
      context_type: body.context_type ?? null,
      context_id: body.context_id ?? null,
      recipient_ids: body.recipient_ids ?? [],
      target_org_id: body.target_org_id ?? null,
      target_department_id: body.target_department_id ?? null,
      subject: body.subject ?? null,
      first_message: body.first_message ?? null,
    });
  },

  /**
   * Org shared inbox (`GET /inbox`) — the team queue for partner/university
   * personas. RBAC + department scoped server-side. `scope` = the triage filter.
   */
  listInbox(opts?: {
    scope?: InboxScope;
    departmentId?: string | null;
    q?: string | null;
    cursor?: string | null;
    limit?: number;
  }): Promise<ApiListEnvelope<InboxThreadSummary>> {
    return api.list<InboxThreadSummary>("/messaging/inbox", {
      query: {
        scope: opts?.scope ?? undefined,
        department_id: opts?.departmentId ?? undefined,
        q: opts?.q?.trim() || undefined,
        cursor: opts?.cursor ?? undefined,
        limit: opts?.limit,
      },
    });
  },

  /** Team-level read: clear unread on the shared org party cursor. */
  markInboxRead(threadId: string): Promise<InboxReadResult> {
    return api.post<InboxReadResult>(`/messaging/inbox/${threadId}/read`, {});
  },

  /**
   * Search valid recipients for the "new message" composer. Returns only targets
   * the caller may message (students receive `org` targets only). `q` filters by
   * name; an empty `q` returns the default set.
   */
  async searchRecipients(
    q?: string | null,
    limit = 20,
  ): Promise<RecipientTarget[]> {
    const data = await api.get<{ items: RecipientTarget[] }>(
      "/messaging/recipients",
      { query: { q: q?.trim() || undefined, limit } },
    );
    return data.items ?? [];
  },

  /** Respond to a pending message request (accept | decline | block). */
  respondRequest(
    threadId: string,
    action: RequestAction,
  ): Promise<RequestActionResult> {
    return api.post<RequestActionResult>(
      `/messaging/threads/${threadId}/request/${action}`,
      {},
    );
  },

  /** Route an org thread to a department and/or assignee (RBAC-gated). */
  assignThread(
    threadId: string,
    body: { department_id?: string | null; assignee_id?: string | null },
  ): Promise<AssignThreadResult> {
    return api.post<AssignThreadResult>(
      `/messaging/threads/${threadId}/assign`,
      {
        department_id: body.department_id ?? null,
        assignee_id: body.assignee_id ?? null,
      },
    );
  },

  /** Mark an org thread resolved (or reopen it). */
  resolveThread(
    threadId: string,
    resolved: boolean,
  ): Promise<ResolveThreadResult> {
    return api.post<ResolveThreadResult>(
      `/messaging/threads/${threadId}/resolve`,
      { resolved },
    );
  },

  /** Thread detail (participant/moderator only; 404 otherwise). */
  getThread(threadId: string): Promise<ThreadDetail> {
    return api.get<ThreadDetail>(`/messaging/threads/${threadId}`);
  },

  /**
   * Messages in a thread, ascending (oldest → newest), cursor-paginated.
   * `after` returns messages strictly newer than the cursor (poll for new).
   */
  listMessages(
    threadId: string,
    opts?: { after?: string | null; limit?: number },
  ): Promise<ApiListEnvelope<Message>> {
    return api.list<Message>(`/messaging/threads/${threadId}/messages`, {
      query: { after: opts?.after ?? undefined, limit: opts?.limit },
    });
  },

  /** Send a message (re-checks permission + rate limit; idempotent on key). */
  sendMessage(threadId: string, body: SendMessageBody): Promise<Message> {
    return api.post<Message>(`/messaging/threads/${threadId}/messages`, {
      body: body.body,
      reply_to_id: body.reply_to_id ?? null,
      client_dedupe_key: body.client_dedupe_key ?? null,
      attachment_ids: body.attachment_ids ?? [],
    });
  },

  /** Clear unread for the caller (sets `last_read_at = now`). */
  markRead(threadId: string): Promise<MarkReadResult> {
    return api.post<MarkReadResult>(`/messaging/threads/${threadId}/read`, {});
  },

  /** Mute/unmute a thread (suppresses notifications + badge). */
  muteThread(threadId: string, muted: boolean): Promise<MuteResult> {
    return api.post<MuteResult>(`/messaging/threads/${threadId}/mute`, { muted });
  },

  /** Soft-delete own message (≤10min) / university any / system never. */
  deleteMessage(
    threadId: string,
    messageId: string,
  ): Promise<DeleteMessageResult> {
    return api.delete<DeleteMessageResult>(
      `/messaging/threads/${threadId}/messages/${messageId}`,
    );
  },

  /** Report a thread → audit + notify university moderators. */
  reportThread(
    threadId: string,
    reason?: string,
  ): Promise<ReportThreadResult> {
    return api.post<ReportThreadResult>(
      `/messaging/threads/${threadId}/report`,
      { reason: reason ?? null },
    );
  },

  /**
   * Download a message attachment's bytes through the gated endpoint (Bearer
   * auth via {@link apiDownload}). Returns a Blob — the caller makes an object
   * URL for inline images / a download link for files, and revokes it on unmount.
   */
  downloadAttachment(attachmentId: string): Promise<Blob> {
    return apiDownload(`/messaging/attachments/${attachmentId}`);
  },

  /** Lightweight badge poll: unread sum across non-muted threads. */
  async unreadCount(): Promise<number> {
    const data = await api.get<{ unread_count: number }>(
      "/messaging/unread-count",
    );
    return data.unread_count;
  },
};

/** Generate a retry-safe idempotency key for an optimistic send. */
export function newDedupeKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `m-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}
