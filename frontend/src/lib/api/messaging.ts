import { api } from "./client";
import type { ApiListEnvelope } from "./types";

/* ------------------------------- Vocabularies ----------------------------- */

/** Thread kind. `announcement` recipients are one-way (read-only). */
export type ThreadKind = "direct" | "announcement";

/**
 * Thread context. Drives initiation rules server-side:
 * - `application` — partner↔candidate, bound to an application (fully identified).
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

/* ------------------------------- Wire types ------------------------------- */

/**
 * A thread row in the inbox. Every identity field is a SERVER-rendered label
 * (`counterpart_label`, participant `label`, message `sender_label`) rendered
 * verbatim. `is_anonymous` is a residual backend field that is always `false`
 * (the identity-reveal flow was removed) — the UI never renders masking.
 */
export interface ThreadSummary {
  id: string;
  kind: ThreadKind;
  kind_label: string;
  context_type: ThreadContextType | null;
  context_label: string | null;
  subject: string | null;
  /** Real label for the OTHER side (server-rendered). */
  counterpart_label: string;
  status: ThreadStatus;
  status_label: string;
  /** Residual backend field, always `false`; never drives masking in the UI. */
  is_anonymous: boolean;
  unread: number;
  can_reply: boolean;
  muted: boolean;
  last_message_at: string | null;
}

/** One rendered participant (label is the server-rendered real name). */
export interface ThreadParticipant {
  label: string;
  can_reply: boolean;
  role_in_thread: string;
}

/** Thread detail = summary + the rendered participant roster. */
export interface ThreadDetail extends ThreadSummary {
  participants: ThreadParticipant[];
}

/**
 * A single message. `body` is markdown-lite and MUST be rendered through the
 * sanitizing renderer (never `dangerouslySetInnerHTML`). `sender_label` is the
 * server-rendered real name; for system/announcement rows it is the system
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
  created_at: string;
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
  recipient_ids: string[];
  subject?: string | null;
  first_message?: string | null;
}

/** Send-message body. `client_dedupe_key` makes a retry idempotent. */
export interface SendMessageBody {
  body: string;
  reply_to_id?: string | null;
  client_dedupe_key?: string | null;
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
      recipient_ids: body.recipient_ids,
      subject: body.subject ?? null,
      first_message: body.first_message ?? null,
    });
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
