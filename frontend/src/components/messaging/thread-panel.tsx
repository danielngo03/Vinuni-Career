"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowClockwise,
  ArrowUUpLeft,
  BellSlash,
  Bell,
  CheckCircle,
  CircleNotch,
  Flag,
  HourglassMedium,
  Megaphone,
  PaperPlaneTilt,
  Paperclip,
  Prohibit,
  Trash,
  UserSwitch,
  WarningCircle,
  WifiSlash,
  X,
  XCircle,
} from "@phosphor-icons/react";
import { Button, EmptyState, Skeleton, useToast } from "@/components/ui";
import { CompanyAvatar } from "@/components/companies/company-avatar";
import { ReportModal } from "@/components/report/report-modal";
import { cn } from "@/lib/utils";
import { relativeTime } from "@/lib/notifications/grouping";
import { renderMessageBody } from "@/lib/messaging/markdown";
import {
  ApiError,
  messagingApi,
  newDedupeKey,
  type InboxThreadSummary,
  type MessagingMessage,
  type RequestAction,
  type RequestState,
  type ThreadSummary,
} from "@/lib/api";
import {
  MESSAGING_INBOX_ROOT,
  MESSAGING_THREADS_KEY,
  MESSAGING_UNREAD_KEY,
  messagingThreadDetailKey,
  messagingThreadKey,
} from "./query-keys";
import { useThreadMessages } from "./use-thread-messages";
import { useThreadTyping } from "./use-messaging-socket";
import { RequestChip } from "./thread-chips";
import { AssignThreadModal } from "./assign-thread-modal";
import { MessageAttachments } from "./message-attachments";
import {
  ATTACHMENT_ACCEPT,
  ATTACHMENT_MAX_COUNT,
  AttachmentUploadError,
  attachmentKindOf,
  formatBytes,
  uploadMessagingAttachment,
  validateAttachment,
} from "./attachment-api";

const DELETE_WINDOW_MS = 10 * 60 * 1000;

/** Party axes where a staff member replies AS the org Page (masked identity). */
const ORG_PAGE_KINDS = new Set(["org_dm", "org_to_org", "application", "support"]);

interface PendingMessage {
  key: string;
  body: string;
  reply_to_id: string | null;
  attachment_ids: string[];
  status: "sending" | "failed";
  created_at: string;
}

interface PendingAttachment {
  localId: string;
  name: string;
  size: number;
  kind: "image" | "file";
  previewUrl?: string;
  status: "uploading" | "done" | "error";
  progress: number;
  attachmentId?: string;
}

/** The org identity the caller replies as (for the "Replying as" affordance). */
export interface OrgIdentity {
  name: string;
  slug?: string | null;
  logoUrl?: string | null;
}

export interface ThreadPanelProps {
  thread: ThreadSummary | InboxThreadSummary;
  open: boolean;
  onBack: () => void;
  onChanged: () => void;
  variant?: "personal" | "org";
  orgIdentity?: OrgIdentity | null;
  canAssign?: boolean;
  onAssignmentChanged?: () => void;
}

/**
 * One open thread: header (masked counterpart + request/assignment state +
 * mute/report, plus Assign/Resolve in the org inbox), a polled + socket-accelerated
 * sanitized aria-live transcript with a typing indicator, and a composer with
 * optimistic send, retry, and attachments. The Messaging V2 request gate uses the
 * authoritative `viewer_is_recipient` (Accept/Decline/Block bar) and the exact
 * `request_message_count/limit` intro counter. Identity is the server label only.
 */
export function ThreadPanel({
  thread,
  open,
  onBack,
  onChanged,
  variant = "personal",
  orgIdentity = null,
  canAssign = false,
  onAssignmentChanged,
}: ThreadPanelProps) {
  const t = useTranslations("messaging");
  const tc = useTranslations("common");
  const tStates = useTranslations("states");
  const locale = useLocale();
  const qc = useQueryClient();
  const { show } = useToast();

  const isAnnouncement = thread.kind === "announcement";
  const isOrg = variant === "org";
  const [closed, setClosed] = useState(thread.status === "closed");
  const [muted, setMuted] = useState(thread.muted);
  const [pending, setPending] = useState<PendingMessage[]>([]);
  const [attachments, setAttachments] = useState<PendingAttachment[]>([]);
  const [draft, setDraft] = useState("");
  const [rateLimitMsg, setRateLimitMsg] = useState<string | null>(null);
  const [reportOpen, setReportOpen] = useState(false);
  const [assignOpen, setAssignOpen] = useState(false);
  const [requestState, setRequestState] = useState<RequestState>(thread.request_state);
  const [introLimitReached, setIntroLimitReached] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const liveRef = useRef<HTMLDivElement>(null);
  const lastSeenId = useRef<string | null>(null);
  const attachmentsRef = useRef<PendingAttachment[]>([]);
  attachmentsRef.current = attachments;

  const assignmentState = (thread as Partial<InboxThreadSummary>).assignment_state;
  const isResolved = assignmentState === "resolved";

  const isPending = requestState === "pending";

  // Reset per-thread local state when the open thread changes.
  useEffect(() => {
    setRequestState(thread.request_state);
    setClosed(thread.status === "closed");
    setMuted(thread.muted);
    setPending([]);
    setDraft("");
    setRateLimitMsg(null);
    setIntroLimitReached(false);
    lastSeenId.current = null;
    for (const a of attachmentsRef.current) {
      if (a.previewUrl) URL.revokeObjectURL(a.previewUrl);
    }
    setAttachments([]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [thread.id]);

  // Revoke any remaining previews on unmount.
  useEffect(
    () => () => {
      for (const a of attachmentsRef.current) {
        if (a.previewUrl) URL.revokeObjectURL(a.previewUrl);
      }
    },
    [],
  );

  const messagesQuery = useThreadMessages(thread.id, open);
  const serverMessages = useMemo(
    () => messagesQuery.data ?? [],
    [messagesQuery.data],
  );

  // Authoritative request facts (viewer_is_recipient + intro counter) come from
  // the thread detail — only fetched while the thread is a pending request.
  const detailQuery = useQuery({
    queryKey: messagingThreadDetailKey(thread.id),
    queryFn: () => messagingApi.getThread(thread.id),
    enabled: open && isPending,
    staleTime: 8_000,
    retry: false,
  });
  const detail = detailQuery.data;

  const { typing, sendTyping } = useThreadTyping(thread.id, open && !isAnnouncement);

  // Mark read: org inbox = team cursor; personal = participant cursor.
  const markRead = useMutation({
    mutationFn: () =>
      isOrg ? messagingApi.markInboxRead(thread.id) : messagingApi.markRead(thread.id),
    onSuccess: () => {
      patchThreadUnread(qc, thread.id, 0);
      void qc.invalidateQueries({ queryKey: MESSAGING_UNREAD_KEY });
      if (isOrg) void qc.invalidateQueries({ queryKey: MESSAGING_INBOX_ROOT });
    },
    onError: () => undefined,
  });

  useEffect(() => {
    if (open) markRead.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, thread.id]);

  useEffect(() => {
    const newest = serverMessages[serverMessages.length - 1];
    if (!newest) return;
    if (lastSeenId.current && newest.id !== lastSeenId.current && !newest.is_mine) {
      if (liveRef.current) {
        liveRef.current.textContent = t("newMessageAnnounce", {
          sender: newest.sender_label || thread.counterpart_label,
        });
      }
      if (open) markRead.mutate();
    }
    lastSeenId.current = newest.id;
    requestAnimationFrame(() => {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverMessages]);

  /* ------------------------------ Request gate ---------------------------- */

  const iSent = serverMessages.some((m) => m.is_mine && !m.is_system);
  const hasIncoming = serverMessages.some((m) => !m.is_mine && !m.is_system);
  const inferredRecipient = isPending && !iSent && (isOrg ? true : hasIncoming);
  // Prefer the authoritative flag; fall back to inference while detail loads.
  const iAmRequestRecipient =
    isPending && (detail ? detail.viewer_is_recipient : inferredRecipient);
  const iAmRequestInitiator = isPending && !iAmRequestRecipient;

  const introCount = detail?.request_message_count ?? thread.request_message_count;
  const introLimit = detail?.request_message_limit ?? thread.request_message_limit;
  const introRemaining = Math.max(0, introLimit - introCount);
  const introExhausted =
    introLimitReached ||
    (iAmRequestInitiator && introLimit > 0 && introCount >= introLimit);

  const respond = useMutation({
    mutationFn: (action: RequestAction) => messagingApi.respondRequest(thread.id, action),
    onSuccess: (res, action) => {
      setRequestState(res.request_state);
      show({
        tone: action === "accept" ? "success" : "info",
        title:
          action === "accept"
            ? t("requestAcceptedToast")
            : action === "decline"
              ? t("requestDeclinedToast")
              : t("requestBlockedToast"),
      });
      void messagesQuery.refetch();
      void qc.invalidateQueries({ queryKey: messagingThreadDetailKey(thread.id) });
      onChanged();
      void qc.invalidateQueries({ queryKey: MESSAGING_THREADS_KEY });
      if (isOrg) void qc.invalidateQueries({ queryKey: MESSAGING_INBOX_ROOT });
    },
    onError: (err) => {
      if (err instanceof ApiError && err.status === 409) {
        show({ tone: "info", title: t("requestNotPendingToast") });
        void messagesQuery.refetch();
        void qc.invalidateQueries({ queryKey: messagingThreadDetailKey(thread.id) });
        onChanged();
      } else {
        show({
          tone: "error",
          title: err instanceof ApiError ? err.message : t("errors.requestActionFailed"),
        });
      }
    },
  });

  /* ------------------------------ Assign / resolve ------------------------ */

  const resolve = useMutation({
    mutationFn: (next: boolean) => messagingApi.resolveThread(thread.id, next),
    onSuccess: (_res, next) => {
      show({ tone: "success", title: next ? t("resolvedToast") : t("reopenedToast") });
      void qc.invalidateQueries({ queryKey: MESSAGING_INBOX_ROOT });
      onAssignmentChanged?.();
      onChanged();
    },
    onError: (err) =>
      show({
        tone: "error",
        title:
          err instanceof ApiError && err.isPermissionError
            ? t("errors.notAllowedAssign")
            : err instanceof ApiError
              ? err.message
              : tStates("errorTitle"),
      }),
  });

  /* -------------------------------- Attachments --------------------------- */

  function onPickFiles(list: FileList | null) {
    if (!list || list.length === 0) return;
    let room = ATTACHMENT_MAX_COUNT - attachmentsRef.current.length;
    if (room <= 0) {
      show({ tone: "error", title: t("attachTooMany", { max: ATTACHMENT_MAX_COUNT }) });
      return;
    }
    for (const file of Array.from(list)) {
      if (room <= 0) {
        show({ tone: "error", title: t("attachTooMany", { max: ATTACHMENT_MAX_COUNT }) });
        break;
      }
      const check = validateAttachment(file);
      if (check === "type") {
        show({ tone: "error", title: t("attachBadType", { name: file.name }) });
        continue;
      }
      if (check === "size") {
        show({ tone: "error", title: t("attachTooLarge", { name: file.name }) });
        continue;
      }
      room -= 1;
      const localId = newDedupeKey();
      const kind = attachmentKindOf(file);
      const previewUrl = kind === "image" ? URL.createObjectURL(file) : undefined;
      setAttachments((prev) => [
        ...prev,
        { localId, name: file.name, size: file.size, kind, previewUrl, status: "uploading", progress: 0 },
      ]);
      void uploadMessagingAttachment(thread.id, file, {
        onProgress: (percent) =>
          setAttachments((prev) =>
            prev.map((a) => (a.localId === localId ? { ...a, progress: percent } : a)),
          ),
      })
        .then((att) =>
          setAttachments((prev) =>
            prev.map((a) =>
              a.localId === localId
                ? { ...a, status: "done", progress: 100, attachmentId: att.id }
                : a,
            ),
          ),
        )
        .catch((err) => {
          setAttachments((prev) =>
            prev.map((a) => (a.localId === localId ? { ...a, status: "error" } : a)),
          );
          const reason = err instanceof AttachmentUploadError ? err.reason : "generic";
          show({
            tone: "error",
            title:
              reason === "size"
                ? t("attachTooLarge", { name: file.name })
                : reason === "type"
                  ? t("attachBadType", { name: file.name })
                  : t("attachUploadFailed", { name: file.name }),
          });
        });
    }
  }

  function removeAttachment(localId: string) {
    setAttachments((prev) => {
      const target = prev.find((a) => a.localId === localId);
      if (target?.previewUrl) URL.revokeObjectURL(target.previewUrl);
      return prev.filter((a) => a.localId !== localId);
    });
  }

  function clearAttachments() {
    for (const a of attachmentsRef.current) {
      if (a.previewUrl) URL.revokeObjectURL(a.previewUrl);
    }
    setAttachments([]);
  }

  const uploadingCount = attachments.filter((a) => a.status === "uploading").length;

  /* --------------------------------- Send --------------------------------- */

  async function deliver(
    body: string,
    key: string,
    replyTo: string | null,
    attachmentIds: string[],
  ) {
    setRateLimitMsg(null);
    try {
      await messagingApi.sendMessage(thread.id, {
        body,
        reply_to_id: replyTo,
        client_dedupe_key: key,
        attachment_ids: attachmentIds,
      });
      await qc.invalidateQueries({ queryKey: messagingThreadKey(thread.id) });
      setPending((p) => p.filter((m) => m.key !== key));
      onChanged();
      void qc.invalidateQueries({ queryKey: MESSAGING_THREADS_KEY });
      void qc.invalidateQueries({ queryKey: messagingThreadDetailKey(thread.id) });
      if (isOrg) void qc.invalidateQueries({ queryKey: MESSAGING_INBOX_ROOT });
    } catch (err) {
      if (err instanceof ApiError) {
        const reason =
          typeof err.details?.reason === "string" ? err.details.reason : undefined;
        if (err.status === 409 && reason === "request_pending_limit") {
          setPending((p) => p.filter((m) => m.key !== key));
          setIntroLimitReached(true);
          show({ tone: "info", title: t("requestLimitToast") });
          return;
        }
        if (err.status === 409 && reason === "request_declined") {
          setPending((p) => p.filter((m) => m.key !== key));
          setRequestState("declined");
          return;
        }
        if (err.status === 409 && reason === "request_blocked") {
          setPending((p) => p.filter((m) => m.key !== key));
          setRequestState("blocked");
          return;
        }
      }
      setPending((p) => p.map((m) => (m.key === key ? { ...m, status: "failed" } : m)));
      if (err instanceof ApiError) {
        if (err.isConflict) {
          setClosed(true);
        } else if (err.code === "RATE_LIMITED" || err.status === 429) {
          const resetAt = err.details?.reset_at;
          let msg = t("rateLimited");
          if (typeof resetAt === "string") {
            const d = new Date(resetAt);
            if (!Number.isNaN(d.getTime())) {
              msg = t("rateLimitedUntil", {
                time: d.toLocaleString(undefined, {
                  hour: "2-digit",
                  minute: "2-digit",
                  day: "2-digit",
                  month: "2-digit",
                }),
              });
            }
          }
          setRateLimitMsg(msg);
        } else if (err.isPermissionError) {
          show({ tone: "error", title: t("errors.notAllowed") });
        } else {
          show({ tone: "error", title: err.message });
        }
      } else {
        show({ tone: "error", title: tStates("offlineTitle") });
      }
    }
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const body = draft.trim();
    const attachmentIds = attachments
      .filter((a) => a.status === "done" && a.attachmentId)
      .map((a) => a.attachmentId as string);
    // Allow an attachment-only message (no text) — the backend accepts a blank body
    // when attachments are present.
    if ((!body && attachmentIds.length === 0) || closed || uploadingCount > 0) return;
    const key = newDedupeKey();
    setPending((p) => [
      ...p,
      {
        key,
        body,
        reply_to_id: null,
        attachment_ids: attachmentIds,
        status: "sending",
        created_at: new Date().toISOString(),
      },
    ]);
    setDraft("");
    clearAttachments();
    void deliver(body, key, null, attachmentIds);
  }

  function retry(m: PendingMessage) {
    setPending((p) => p.map((x) => (x.key === m.key ? { ...x, status: "sending" } : x)));
    void deliver(m.body, m.key, m.reply_to_id, m.attachment_ids);
  }

  function discard(key: string) {
    setPending((p) => p.filter((m) => m.key !== key));
  }

  /* ----------------------------- Mute / delete ---------------------------- */

  const muteMutation = useMutation({
    mutationFn: (next: boolean) => messagingApi.muteThread(thread.id, next),
    onMutate: (next) => setMuted(next),
    onSuccess: (res) => {
      setMuted(res.muted);
      onChanged();
      void qc.invalidateQueries({ queryKey: MESSAGING_UNREAD_KEY });
    },
    onError: () => {
      setMuted((m) => !m);
      show({ tone: "error", title: tStates("errorTitle") });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (messageId: string) => messagingApi.deleteMessage(thread.id, messageId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: messagingThreadKey(thread.id) });
    },
    onError: (err) =>
      show({
        tone: "error",
        title: err instanceof ApiError ? err.message : tStates("errorTitle"),
      }),
  });

  /* --------------------------------- Render ------------------------------- */

  const readError = messagesQuery.error;
  const isReadBlocked =
    isOrg &&
    readError instanceof ApiError &&
    (readError.isNotFound || readError.isPermissionError);

  const isLoading = messagesQuery.isLoading;
  const isError = messagesQuery.isError && serverMessages.length === 0 && !isReadBlocked;
  const isStale = messagesQuery.isError && serverMessages.length > 0;
  const isEmpty =
    !isLoading &&
    !isError &&
    !isReadBlocked &&
    serverMessages.length === 0 &&
    pending.length === 0;

  const requestBlocked = requestState === "declined" || requestState === "blocked";
  const showRequestActions = iAmRequestRecipient && !requestBlocked;
  const canCompose =
    thread.can_reply &&
    !isAnnouncement &&
    !closed &&
    !showRequestActions &&
    !requestBlocked &&
    !introExhausted;

  const actsAsOrgPage =
    !!orgIdentity && ORG_PAGE_KINDS.has(thread.thread_kind) && !isAnnouncement;

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-start gap-2 border-b border-[var(--border-default)] bg-[var(--surface-card)] px-5 py-4">
        <button
          type="button"
          onClick={onBack}
          aria-label={tc("back")}
          className="-ml-1 rounded-lg p-1.5 text-[var(--text-secondary)] outline-none hover:bg-[var(--bg-subtle)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]"
        >
          <ArrowLeft aria-hidden weight="bold" className="size-5" />
        </button>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            {isAnnouncement && (
              <span className="flex size-5 shrink-0 items-center justify-center rounded-md icon-chip-warning shadow-sm">
                <Megaphone aria-hidden weight="duotone" className="size-3 text-white" />
              </span>
            )}
            <h3 className="truncate text-sm font-bold text-[var(--text-primary)]">
              {thread.counterpart_label}
            </h3>
            <RequestChip state={requestState} label={thread.request_label} />
          </div>
          <p className="mt-0.5 truncate text-xs text-[var(--text-muted)]">
            {thread.subject || thread.context_label || thread.kind_label}
            {thread.status !== "active" && ` · ${thread.status_label}`}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {isOrg && canAssign && !isAnnouncement && (
            <>
              <Button
                variant="secondary"
                size="xs"
                onClick={() => setAssignOpen(true)}
                className="hidden sm:inline-flex"
              >
                <UserSwitch aria-hidden weight="bold" className="size-3.5" />
                {assignmentState === "assigned" ? t("reassign") : t("assign")}
              </Button>
              <Button
                variant={isResolved ? "ghost" : "secondary"}
                size="xs"
                loading={resolve.isPending}
                onClick={() => resolve.mutate(!isResolved)}
                className="hidden sm:inline-flex"
              >
                {isResolved ? (
                  <ArrowUUpLeft aria-hidden weight="bold" className="size-3.5" />
                ) : (
                  <CheckCircle aria-hidden weight="bold" className="size-3.5" />
                )}
                {isResolved ? t("reopen") : t("resolve")}
              </Button>
            </>
          )}
          {!isAnnouncement && (
            <>
              <button
                type="button"
                onClick={() => muteMutation.mutate(!muted)}
                aria-pressed={muted}
                aria-label={muted ? t("unmute") : t("mute")}
                title={muted ? t("unmute") : t("mute")}
                className="rounded-lg p-1.5 text-[var(--text-muted)] outline-none hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]"
              >
                {muted ? (
                  <BellSlash aria-hidden weight="duotone" className="size-4" />
                ) : (
                  <Bell aria-hidden weight="duotone" className="size-4" />
                )}
              </button>
              <button
                type="button"
                onClick={() => setReportOpen(true)}
                aria-label={t("report")}
                title={t("report")}
                className="rounded-lg p-1.5 text-[var(--text-muted)] outline-none hover:bg-[var(--red-50)] hover:text-[var(--brand-red)] focus-visible:ring-2 focus-visible:ring-[var(--brand-red)]"
              >
                <Flag aria-hidden weight="duotone" className="size-4" />
              </button>
            </>
          )}
        </div>
      </div>

      {/* Org inbox: mobile Assign/Resolve row */}
      {isOrg && canAssign && !isAnnouncement && (
        <div className="flex items-center gap-2 border-b border-[var(--border-default)] bg-[var(--bg-subtle)] px-5 py-2 sm:hidden">
          <Button variant="secondary" size="xs" fullWidth onClick={() => setAssignOpen(true)}>
            <UserSwitch aria-hidden weight="bold" className="size-3.5" />
            {assignmentState === "assigned" ? t("reassign") : t("assign")}
          </Button>
          <Button
            variant={isResolved ? "ghost" : "secondary"}
            size="xs"
            fullWidth
            loading={resolve.isPending}
            onClick={() => resolve.mutate(!isResolved)}
          >
            {isResolved ? t("reopen") : t("resolve")}
          </Button>
        </div>
      )}

      {/* Transcript */}
      <div
        ref={scrollRef}
        className="flex-1 space-y-3 overflow-y-auto bg-[var(--surface-card)] px-5 py-4"
        aria-label={t("transcript")}
      >
        {isStale && (
          <p className="flex items-center justify-center gap-1.5 rounded-lg bg-[var(--amber-100)] px-3 py-1.5 text-xs font-medium text-[var(--amber-700)]">
            <WifiSlash aria-hidden weight="bold" className="size-3.5" />
            {t("staleReload")}
          </p>
        )}

        {isLoading && <TranscriptSkeleton />}

        {isReadBlocked && (
          <EmptyState
            kind="empty"
            icon={HourglassMedium}
            title={t("joinToViewTitle")}
            description={isPending ? t("joinToViewPendingBody") : t("joinToViewBody")}
          />
        )}

        {isError && (
          <EmptyState
            kind="offline"
            icon={WifiSlash}
            title={tStates("offlineTitle")}
            description={t("offlineRetry")}
            action={
              <Button variant="secondary" size="sm" onClick={() => void messagesQuery.refetch()}>
                {tc("retry")}
              </Button>
            }
          />
        )}

        {isEmpty && (
          <EmptyState
            kind="empty"
            icon={PaperPlaneTilt}
            title={t("threadEmptyTitle")}
            description={canCompose ? t("threadEmptyBody") : t("threadEmptyReadOnly")}
          />
        )}

        {serverMessages.map((m) => (
          <MessageBubble
            key={m.id}
            message={m}
            locale={locale}
            deletableUntil={DELETE_WINDOW_MS}
            onDelete={() => deleteMutation.mutate(m.id)}
            deleteLabel={tc("delete")}
          />
        ))}

        {pending.map((m) => (
          <PendingBubble
            key={m.key}
            message={m}
            sendingLabel={t("sending")}
            failedLabel={t("sendFailed")}
            retryLabel={tc("retry")}
            discardLabel={tc("cancel")}
            attachmentLabel={t("attachmentCount", { count: m.attachment_ids.length })}
            onRetry={() => retry(m)}
            onDiscard={() => discard(m.key)}
          />
        ))}

        {typing && (
          <TypingIndicator label={t("typingIndicator", { name: thread.counterpart_label })} />
        )}
      </div>

      {/* aria-live region for incoming messages (visually hidden) */}
      <div ref={liveRef} role="status" aria-live="polite" className="sr-only" />

      {/* Composer / request bar / read-only notice */}
      {rateLimitMsg && (
        <p
          role="alert"
          className="mb-2 flex items-center gap-1.5 rounded-lg bg-[var(--amber-100)] px-3 py-2 text-xs font-medium text-[var(--amber-700)]"
        >
          <WarningCircle aria-hidden weight="bold" className="size-4 shrink-0" />
          {rateLimitMsg}
        </p>
      )}

      {closed ? (
        <ReadOnlyNotice text={t("threadClosed")} icon={WarningCircle} />
      ) : isAnnouncement ? (
        <ReadOnlyNotice text={t("announcementReadOnly")} icon={Megaphone} />
      ) : requestState === "blocked" ? (
        <ReadOnlyNotice
          text={t("requestBlockedNotice", { name: thread.counterpart_label })}
          icon={Prohibit}
          tone="danger"
        />
      ) : requestState === "declined" ? (
        <ReadOnlyNotice
          text={t("requestDeclinedNotice", { name: thread.counterpart_label })}
          icon={XCircle}
        />
      ) : showRequestActions ? (
        <RequestActionBar
          counterpart={thread.counterpart_label}
          pending={respond.isPending}
          onAction={(a) => respond.mutate(a)}
        />
      ) : introExhausted ? (
        <ReadOnlyNotice
          text={t("requestLimitReachedNotice", { name: thread.counterpart_label })}
          icon={HourglassMedium}
        />
      ) : !thread.can_reply ? (
        <ReadOnlyNotice text={t("replyNotAllowed")} icon={WarningCircle} />
      ) : (
        <div className="border-t border-[var(--border-default)] bg-[var(--bg-subtle)]">
          {iAmRequestInitiator && (
            <p className="flex flex-wrap items-center gap-x-2 gap-y-0.5 px-5 pt-3 text-xs font-medium text-[var(--text-secondary)]">
              <span className="flex items-center gap-1.5">
                <HourglassMedium
                  aria-hidden
                  weight="duotone"
                  className="size-4 shrink-0 text-[var(--text-muted)]"
                />
                {t("requestWaitingNotice", { name: thread.counterpart_label })}
              </span>
              {introLimit > 0 && (
                <span className="rounded-full bg-[var(--bg-muted)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--text-muted)]">
                  {t("introMessagesLeft", { remaining: introRemaining, limit: introLimit })}
                </span>
              )}
            </p>
          )}
          {actsAsOrgPage && (
            <div className="flex items-center gap-1.5 px-5 pt-3 text-[11px] font-medium text-[var(--text-muted)]">
              <CompanyAvatar
                name={orgIdentity!.name}
                logoUrl={orgIdentity!.logoUrl ?? null}
                size="sm"
                className="!size-4 !rounded"
              />
              {t("replyingAs", { name: orgIdentity!.name })}
            </div>
          )}

          {attachments.length > 0 && (
            <ul className="flex flex-wrap gap-2 px-5 pt-3">
              {attachments.map((a) => (
                <li key={a.localId}>
                  <AttachmentDraftChip
                    attachment={a}
                    onRemove={() => removeAttachment(a.localId)}
                    removeLabel={tc("cancel")}
                    uploadingLabel={t("attachUploading")}
                    failedLabel={t("attachFailedShort")}
                  />
                </li>
              ))}
            </ul>
          )}

          <form onSubmit={onSubmit} className="flex items-end gap-2 px-5 py-3">
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept={ATTACHMENT_ACCEPT}
              className="sr-only"
              onChange={(e) => {
                onPickFiles(e.target.files);
                e.target.value = "";
              }}
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              aria-label={t("attachAdd")}
              title={t("attachAdd")}
              className="mb-0.5 shrink-0 rounded-lg p-2 text-[var(--text-muted)] outline-none hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]"
            >
              <Paperclip aria-hidden weight="bold" className="size-5" />
            </button>
            <label htmlFor="msg-composer" className="sr-only">
              {t("composerLabel")}
            </label>
            <textarea
              id="msg-composer"
              value={draft}
              onChange={(e) => {
                setDraft(e.target.value);
                if (e.target.value.trim()) sendTyping();
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  onSubmit(e);
                }
              }}
              rows={1}
              maxLength={8000}
              placeholder={t("composerPlaceholder")}
              className="max-h-32 min-h-[40px] flex-1 resize-none rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--brand-primary)]/50 focus:ring-2 focus:ring-[var(--brand-primary)]/20"
            />
            <Button
              type="submit"
              size="md"
              disabled={
                (!draft.trim() && !attachments.some((a) => a.status === "done")) ||
                uploadingCount > 0
              }
              aria-label={t("send")}
              className="shrink-0"
            >
              <PaperPlaneTilt aria-hidden weight="fill" className="size-4" />
            </Button>
          </form>
          {uploadingCount > 0 && (
            <p className="px-5 pb-2 text-[11px] text-[var(--text-muted)]">
              {t("attachUploading")}
            </p>
          )}
        </div>
      )}

      <ReportModal
        open={reportOpen}
        onClose={() => setReportOpen(false)}
        entityType="message"
        entityId={thread.id}
        entityLabel={thread.counterpart_label}
      />

      {isOrg && (
        <AssignThreadModal
          open={assignOpen}
          onClose={() => setAssignOpen(false)}
          thread={thread}
          onAssigned={() => {
            onAssignmentChanged?.();
            onChanged();
          }}
        />
      )}
    </div>
  );
}

/* ------------------------------- Sub-views -------------------------------- */

function RequestActionBar({
  counterpart,
  pending,
  onAction,
}: {
  counterpart: string;
  pending: boolean;
  onAction: (action: RequestAction) => void;
}) {
  const t = useTranslations("messaging");
  return (
    <div className="border-t border-[var(--border-default)] bg-[var(--bg-subtle)] px-5 py-4">
      <p className="text-sm font-semibold text-[var(--text-primary)]">
        {t("requestActionsTitle")}
      </p>
      <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
        {t("requestActionsBody", { name: counterpart })}
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button variant="primary" size="sm" loading={pending} onClick={() => onAction("accept")}>
          <CheckCircle aria-hidden weight="bold" className="size-4" />
          {t("requestAccept")}
        </Button>
        <Button variant="secondary" size="sm" disabled={pending} onClick={() => onAction("decline")}>
          <XCircle aria-hidden weight="bold" className="size-4" />
          {t("requestDecline")}
        </Button>
        <Button variant="danger" size="sm" disabled={pending} onClick={() => onAction("block")}>
          <Prohibit aria-hidden weight="bold" className="size-4" />
          {t("requestBlock")}
        </Button>
      </div>
    </div>
  );
}

function AttachmentDraftChip({
  attachment,
  onRemove,
  removeLabel,
  uploadingLabel,
  failedLabel,
}: {
  attachment: PendingAttachment;
  onRemove: () => void;
  removeLabel: string;
  uploadingLabel: string;
  failedLabel: string;
}) {
  const failed = attachment.status === "error";
  const uploading = attachment.status === "uploading";
  return (
    <div
      className={cn(
        "relative flex items-center gap-2 rounded-lg border px-2 py-1.5 pr-7",
        failed
          ? "border-[var(--brand-red)]/40 bg-[var(--red-50)]"
          : "border-[var(--border-default)] bg-[var(--surface-card)]",
      )}
    >
      {attachment.previewUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={attachment.previewUrl}
          alt=""
          aria-hidden
          className={cn("size-8 rounded object-cover", uploading && "opacity-60")}
        />
      ) : (
        <span className="flex size-8 items-center justify-center rounded bg-[var(--bg-muted)] text-[var(--text-secondary)]">
          <Paperclip aria-hidden weight="bold" className="size-4" />
        </span>
      )}
      <span className="min-w-0 max-w-[9rem]">
        <span className="block truncate text-xs font-semibold text-[var(--text-primary)]">
          {attachment.name}
        </span>
        <span className="block text-[10px] text-[var(--text-muted)]">
          {failed
            ? failedLabel
            : uploading
              ? `${uploadingLabel} ${attachment.progress}%`
              : formatBytes(attachment.size)}
        </span>
      </span>
      {uploading ? (
        <CircleNotch aria-hidden className="size-3.5 shrink-0 animate-spin text-[var(--text-muted)]" />
      ) : null}
      <button
        type="button"
        onClick={onRemove}
        aria-label={removeLabel}
        className="absolute right-1 top-1 rounded p-0.5 text-[var(--text-muted)] outline-none hover:bg-[var(--bg-subtle)] hover:text-[var(--brand-red)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]"
      >
        <X aria-hidden weight="bold" className="size-3" />
      </button>
    </div>
  );
}

function TypingIndicator({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-start">
      <span className="sr-only" role="status">
        {label}
      </span>
      <div className="flex items-center gap-1 rounded-2xl rounded-bl-sm bg-[var(--bg-subtle)] px-3 py-2.5">
        {[0, 150, 300].map((delay) => (
          <span
            key={delay}
            className="size-1.5 animate-bounce rounded-full bg-[var(--text-muted)] motion-reduce:animate-none"
            style={{ animationDelay: `${delay}ms` }}
          />
        ))}
      </div>
    </div>
  );
}

function MessageBubble({
  message,
  locale,
  deletableUntil,
  onDelete,
  deleteLabel,
}: {
  message: MessagingMessage;
  locale: string;
  deletableUntil: number;
  onDelete: () => void;
  deleteLabel: string;
}) {
  const mine = message.is_mine;
  const ts = relativeTime(message.created_at, locale);
  const age = Date.now() - new Date(message.created_at).getTime();
  const canDelete =
    mine && !message.is_system && !message.is_deleted && age < deletableUntil;
  const hasAttachments = !message.is_deleted && message.attachments?.length > 0;

  return (
    <div className={cn("flex flex-col", mine ? "items-end" : "items-start")}>
      {!mine && !message.is_system && (
        <span className="mb-0.5 px-1 text-[11px] font-semibold text-[var(--text-muted)]">
          {message.sender_label}
        </span>
      )}
      <div
        className={cn(
          "group relative max-w-[85%] rounded-2xl px-3 py-2 text-sm",
          message.is_system
            ? "mx-auto bg-[var(--bg-muted)] text-center text-xs text-[var(--text-secondary)]"
            : mine
              ? "rounded-br-sm bg-[var(--brand-primary)] text-white"
              : "rounded-bl-sm bg-[var(--bg-subtle)] text-[var(--text-primary)]",
        )}
      >
        <div
          className={cn(
            "whitespace-pre-wrap break-words",
            message.is_deleted && "italic opacity-70",
          )}
        >
          {message.is_deleted ? message.body : renderMessageBody(message.body)}
        </div>
        {hasAttachments && (
          <MessageAttachments attachments={message.attachments} mine={mine} />
        )}
        {canDelete && (
          <button
            type="button"
            onClick={onDelete}
            aria-label={deleteLabel}
            title={deleteLabel}
            className="absolute -left-7 top-1/2 hidden -translate-y-1/2 rounded-md p-1 text-[var(--text-muted)] outline-none hover:text-[var(--brand-red)] focus-visible:block group-hover:block"
          >
            <Trash aria-hidden weight="bold" className="size-3.5" />
          </button>
        )}
      </div>
      {ts && !message.is_system && (
        <time
          dateTime={message.created_at}
          className="mt-0.5 px-1 text-[10px] text-[var(--text-muted)]"
        >
          {ts}
        </time>
      )}
    </div>
  );
}

function PendingBubble({
  message,
  sendingLabel,
  failedLabel,
  retryLabel,
  discardLabel,
  attachmentLabel,
  onRetry,
  onDiscard,
}: {
  message: PendingMessage;
  sendingLabel: string;
  failedLabel: string;
  retryLabel: string;
  discardLabel: string;
  attachmentLabel: string;
  onRetry: () => void;
  onDiscard: () => void;
}) {
  const failed = message.status === "failed";
  return (
    <div className="flex flex-col items-end">
      <div
        className={cn(
          "max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-br-sm px-3 py-2 text-sm",
          failed
            ? "border border-[var(--brand-red)]/40 bg-[var(--red-50)] text-[var(--text-primary)]"
            : "bg-[var(--brand-primary)]/70 text-white",
        )}
      >
        {renderMessageBody(message.body)}
        {message.attachment_ids.length > 0 && (
          <span
            className={cn(
              "mt-1 flex items-center gap-1 text-[10px]",
              failed ? "text-[var(--text-muted)]" : "text-white/80",
            )}
          >
            <Paperclip aria-hidden weight="bold" className="size-3" />
            {attachmentLabel}
          </span>
        )}
      </div>
      {failed ? (
        <div className="mt-0.5 flex items-center gap-2 px-1 text-[10px]">
          <span className="font-medium text-[var(--brand-red)]">{failedLabel}</span>
          <button
            type="button"
            onClick={onRetry}
            className="flex items-center gap-0.5 font-semibold text-[var(--brand-primary)] underline-offset-2 hover:underline"
          >
            <ArrowClockwise aria-hidden weight="bold" className="size-3" />
            {retryLabel}
          </button>
          <button
            type="button"
            onClick={onDiscard}
            className="text-[var(--text-muted)] underline-offset-2 hover:underline"
          >
            {discardLabel}
          </button>
        </div>
      ) : (
        <span className="mt-0.5 flex items-center gap-1 px-1 text-[10px] text-[var(--text-muted)]">
          <CircleNotch aria-hidden className="size-3 animate-spin" />
          {sendingLabel}
        </span>
      )}
    </div>
  );
}

function ReadOnlyNotice({
  text,
  icon: Icon,
  tone = "muted",
}: {
  text: string;
  icon: typeof WarningCircle;
  tone?: "muted" | "danger";
}) {
  return (
    <p
      className={cn(
        "flex items-center justify-center gap-1.5 border-t border-[var(--border-default)] bg-[var(--bg-subtle)] px-5 py-4 text-xs font-medium",
        tone === "danger" ? "text-[var(--brand-red)]" : "text-[var(--text-muted)]",
      )}
    >
      <Icon aria-hidden weight="duotone" className="size-4 shrink-0" />
      {text}
    </p>
  );
}

function TranscriptSkeleton() {
  return (
    <div className="space-y-3" aria-hidden>
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className={cn("flex", i % 2 ? "justify-end" : "justify-start")}>
          <Skeleton className={cn("h-10 rounded-2xl", i % 2 ? "w-2/5" : "w-3/5")} />
        </div>
      ))}
    </div>
  );
}

/* -------------------------------- Helpers --------------------------------- */

/** Optimistically set one thread's unread to a value across the inbox cache. */
function patchThreadUnread(
  qc: ReturnType<typeof useQueryClient>,
  threadId: string,
  unread: number,
) {
  qc.setQueriesData<{ pages: { data: ThreadSummary[] }[] }>(
    { queryKey: MESSAGING_THREADS_KEY },
    (prev) => {
      if (!prev?.pages) return prev;
      return {
        ...prev,
        pages: prev.pages.map((page) => ({
          ...page,
          data: page.data.map((th) => (th.id === threadId ? { ...th, unread } : th)),
        })),
      };
    },
  );
}
