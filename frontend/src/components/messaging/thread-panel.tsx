"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowClockwise,
  BellSlash,
  Bell,
  CircleNotch,
  Flag,
  Megaphone,
  PaperPlaneTilt,
  Trash,
  WarningCircle,
  WifiSlash,
} from "@phosphor-icons/react";
import { Button, EmptyState, Skeleton, useToast } from "@/components/ui";
import { ReportModal } from "@/components/report/report-modal";
import { cn } from "@/lib/utils";
import { relativeTime } from "@/lib/notifications/grouping";
import { renderMessageBody } from "@/lib/messaging/markdown";
import {
  ApiError,
  messagingApi,
  newDedupeKey,
  type MessagingMessage,
  type ThreadSummary,
} from "@/lib/api";
import {
  MESSAGING_THREADS_KEY,
  MESSAGING_UNREAD_KEY,
  messagingThreadKey,
} from "./query-keys";
import { useThreadMessages } from "./use-thread-messages";

const DELETE_WINDOW_MS = 10 * 60 * 1000;

interface PendingMessage {
  key: string;
  body: string;
  reply_to_id: string | null;
  status: "sending" | "failed";
  created_at: string;
}

export interface ThreadPanelProps {
  thread: ThreadSummary;
  open: boolean;
  onBack: () => void;
  onChanged: () => void;
}

/**
 * One open thread: header (masked counterpart + mute/report), a polled,
 * sanitized, aria-live transcript, and a composer with optimistic send + retry
 * (idempotent on a generated `client_dedupe_key`). Announcement threads and
 * closed/non-reply threads render the composer as a read-only notice. Identity
 * is the server label only — never a reconstructed name/email.
 */
export function ThreadPanel({ thread, open, onBack, onChanged }: ThreadPanelProps) {
  const t = useTranslations("messaging");
  const tc = useTranslations("common");
  const tStates = useTranslations("states");
  const locale = useLocale();
  const qc = useQueryClient();
  const { show } = useToast();

  const isAnnouncement = thread.kind === "announcement";
  const [closed, setClosed] = useState(thread.status === "closed");
  const [muted, setMuted] = useState(thread.muted);
  const [pending, setPending] = useState<PendingMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [rateLimitMsg, setRateLimitMsg] = useState<string | null>(null);
  const [reportOpen, setReportOpen] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const liveRef = useRef<HTMLDivElement>(null);
  const lastSeenId = useRef<string | null>(null);

  const messagesQuery = useThreadMessages(thread.id, open);
  const serverMessages = useMemo(
    () => messagesQuery.data ?? [],
    [messagesQuery.data],
  );

  /* Mark read on open + whenever new server messages land. */
  const markRead = useMutation({
    mutationFn: () => messagingApi.markRead(thread.id),
    onSuccess: () => {
      patchThreadUnread(qc, thread.id, 0);
      // Reconcile the global badge from the server (avoids over-decrement when
      // mark-read fires repeatedly as new messages poll in).
      void qc.invalidateQueries({ queryKey: MESSAGING_UNREAD_KEY });
    },
  });

  useEffect(() => {
    if (open) markRead.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, thread.id]);

  /* Announce + auto-scroll when the newest message changes. */
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

  /* --------------------------------- Send --------------------------------- */

  async function deliver(body: string, key: string, replyTo: string | null) {
    setRateLimitMsg(null);
    try {
      await messagingApi.sendMessage(thread.id, {
        body,
        reply_to_id: replyTo,
        client_dedupe_key: key,
      });
      await qc.invalidateQueries({ queryKey: messagingThreadKey(thread.id) });
      setPending((p) => p.filter((m) => m.key !== key));
      onChanged();
      void qc.invalidateQueries({ queryKey: MESSAGING_THREADS_KEY });
    } catch (err) {
      setPending((p) =>
        p.map((m) => (m.key === key ? { ...m, status: "failed" } : m)),
      );
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
    if (!body || closed) return;
    const key = newDedupeKey();
    setPending((p) => [
      ...p,
      { key, body, reply_to_id: null, status: "sending", created_at: new Date().toISOString() },
    ]);
    setDraft("");
    void deliver(body, key, null);
  }

  function retry(m: PendingMessage) {
    setPending((p) =>
      p.map((x) => (x.key === m.key ? { ...x, status: "sending" } : x)),
    );
    void deliver(m.body, m.key, m.reply_to_id);
  }

  function discard(key: string) {
    setPending((p) => p.filter((m) => m.key !== key));
  }

  /* ----------------------------- Mute / report ---------------------------- */

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
    mutationFn: (messageId: string) =>
      messagingApi.deleteMessage(thread.id, messageId),
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

  const isLoading = messagesQuery.isLoading;
  const isError = messagesQuery.isError && serverMessages.length === 0;
  const isStale = messagesQuery.isError && serverMessages.length > 0;
  const isEmpty =
    !isLoading && !isError && serverMessages.length === 0 && pending.length === 0;

  const canCompose = thread.can_reply && !isAnnouncement && !closed;

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-start gap-2 border-b border-[var(--border-default)] bg-white px-5 py-4">
        <button
          type="button"
          onClick={onBack}
          aria-label={tc("back")}
          className="-ml-1 rounded-lg p-1.5 text-[var(--text-secondary)] outline-none hover:bg-[#f2f1ee] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]"
        >
          <ArrowLeft aria-hidden weight="bold" className="size-5" />
        </button>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            {isAnnouncement && (
              <span className="flex size-5 shrink-0 items-center justify-center rounded-md icon-chip-warning shadow-sm">
                <Megaphone aria-hidden weight="duotone" className="size-3 text-white" />
              </span>
            )}
            <h3 className="truncate text-sm font-bold text-[var(--text-primary)]">
              {thread.counterpart_label}
            </h3>
          </div>
          <p className="mt-0.5 truncate text-xs text-[var(--text-muted)]">
            {thread.subject ||
              thread.context_label ||
              thread.kind_label}
            {thread.status !== "active" && ` · ${thread.status_label}`}
          </p>
        </div>
        {!isAnnouncement && (
          <div className="flex shrink-0 items-center">
            <button
              type="button"
              onClick={() => muteMutation.mutate(!muted)}
              aria-pressed={muted}
              aria-label={muted ? t("unmute") : t("mute")}
              title={muted ? t("unmute") : t("mute")}
              className="rounded-lg p-1.5 text-[var(--text-muted)] outline-none hover:bg-[#f2f1ee] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]"
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
          </div>
        )}
      </div>

      {/* Transcript */}
      <div
        ref={scrollRef}
        className="flex-1 space-y-3 overflow-y-auto bg-white px-5 py-4"
        aria-label={t("transcript")}
      >
        {isStale && (
          <p className="flex items-center justify-center gap-1.5 rounded-lg bg-[var(--amber-100)] px-3 py-1.5 text-xs font-medium text-[var(--amber-700)]">
            <WifiSlash aria-hidden weight="bold" className="size-3.5" />
            {t("staleReload")}
          </p>
        )}

        {isLoading && <TranscriptSkeleton />}

        {isError && (
          <EmptyState
            kind="offline"
            icon={WifiSlash}
            title={tStates("offlineTitle")}
            description={t("offlineRetry")}
            action={
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void messagesQuery.refetch()}
              >
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
            description={
              canCompose ? t("threadEmptyBody") : t("threadEmptyReadOnly")
            }
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
            onRetry={() => retry(m)}
            onDiscard={() => discard(m.key)}
          />
        ))}
      </div>

      {/* aria-live region for incoming messages (visually hidden) */}
      <div ref={liveRef} role="status" aria-live="polite" className="sr-only" />

      {/* Composer / read-only notice */}
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
      ) : !thread.can_reply ? (
        <ReadOnlyNotice text={t("replyNotAllowed")} icon={WarningCircle} />
      ) : (
        <form onSubmit={onSubmit} className="flex items-end gap-2 border-t border-[var(--border-default)] bg-[#fbfaf8] px-5 py-4">
          <label htmlFor="msg-composer" className="sr-only">
            {t("composerLabel")}
          </label>
          <textarea
            id="msg-composer"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                onSubmit(e);
              }
            }}
            rows={1}
            maxLength={8000}
            placeholder={t("composerPlaceholder")}
            className="max-h-32 min-h-[40px] flex-1 resize-none rounded-xl border border-[var(--border-default)] bg-white px-3 py-2 text-sm text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--brand-primary)]/50 focus:ring-2 focus:ring-[var(--brand-primary)]/20"
          />
          <Button
            type="submit"
            size="md"
            disabled={!draft.trim()}
            aria-label={t("send")}
            className="shrink-0"
          >
            <PaperPlaneTilt aria-hidden weight="fill" className="size-4" />
          </Button>
        </form>
      )}

      <ReportModal
        open={reportOpen}
        onClose={() => setReportOpen(false)}
        entityType="message"
        entityId={thread.id}
        entityLabel={thread.counterpart_label}
      />
    </div>
  );
}

/* ------------------------------- Sub-views -------------------------------- */

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
  onRetry,
  onDiscard,
}: {
  message: PendingMessage;
  sendingLabel: string;
  failedLabel: string;
  retryLabel: string;
  discardLabel: string;
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
}: {
  text: string;
  icon: typeof WarningCircle;
}) {
  return (
    <p className="flex items-center justify-center gap-1.5 border-t border-white/40 pt-3 text-xs font-medium text-[var(--text-muted)]">
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
          <Skeleton
            className={cn("h-10 rounded-2xl", i % 2 ? "w-2/5" : "w-3/5")}
          />
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
          data: page.data.map((th) =>
            th.id === threadId ? { ...th, unread } : th,
          ),
        })),
      };
    },
  );
}
