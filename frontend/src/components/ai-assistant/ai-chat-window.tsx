"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowsInSimple,
  ArrowsOutSimple,
  ArrowUp,
  ClockCounterClockwise,
  Paperclip,
  Plus,
  Robot,
  Spinner,
  X,
} from "@phosphor-icons/react";
import {
  aiAssistantApi,
  ApiError,
  type ChatAttachment,
  type ChatMessage,
  type ChatSession,
} from "@/lib/api";
import { getAccessToken } from "@/lib/api/session";
import { env } from "@/lib/env";
import { cn } from "@/lib/utils";
import { useToast } from "@/components/ui";
import { useAuthStore } from "@/stores/auth-store";
import {
  ACCEPTED_ATTACHMENT_ACCEPT,
  buildAttachmentRef,
  isAcceptedAttachment,
  MAX_ATTACHMENT_BYTES,
  MAX_ATTACHMENTS,
  MAX_INPUT_LENGTH,
  STATUS_LABELS,
  type StreamEvent,
} from "./chat-window/constants";
import {
  AssistantActivity,
  MessageBubble,
  StreamingBubble,
  TypingIndicator,
} from "./chat-window/message-bubble";
import { SessionHistorySheet } from "./chat-window/session-history-sheet";
import { SessionList } from "./chat-window/session-list";
import { SessionRail } from "./chat-window/session-rail";
import { AuthLoadingPrompt, GuestPrompt, WelcomeScreen } from "./chat-window/welcome-screen";

/** A composer-local pending attachment. `descriptor` is present once the upload
 * resolves; it only ever carries backend-safe display metadata (never a
 * storage key). */
interface ComposerAttachment {
  localId: string;
  filename: string;
  size: number;
  status: "uploading" | "ready";
  descriptor?: ChatAttachment;
}

/** Human-readable file size (KB/MB) — display only, mirrors the CV preview. */
function formatSize(bytes: number): string {
  const kb = bytes / 1024;
  if (kb < 1024) return `${Math.max(1, Math.round(kb))} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}

/**
 * AI career assistant chat window. Renders as a floating panel anchored at the
 * bottom-right. Uses SSE streaming when the session is live so partial responses
 * render incrementally. Falls back to a sign-in prompt for guests.
 *
 * Provider/model/token internals are never surfaced (AI_PRODUCT_SPEC §9).
 */
export function AiChatWindow({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const t = useTranslations("aiAssistant");
  const toast = useToast();
  const authStatus = useAuthStore((s) => s.status);
  const isAuthed = authStatus === "authenticated";
  const isAuthLoading = authStatus === "unknown";
  const qc = useQueryClient();

  const [sessionId, setSessionId] = useState<string | null>(null);
  const [attachments, setAttachments] = useState<ComposerAttachment[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [streamingText, setStreamingText] = useState<string | null>(null);
  const [activeToolName, setActiveToolName] = useState<string | null>(null);
  const [activityStatus, setActivityStatus] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [expanded, setExpanded] = useState(false);
  const [draftSession, setDraftSession] = useState(false);
  const [confirmingMessageId, setConfirmingMessageId] = useState<string | null>(null);
  // Conversation-history overlay (mobile/tablet/collapsed) + per-row delete state.
  const [historyOpen, setHistoryOpen] = useState(false);
  const [deletingSessionId, setDeletingSessionId] = useState<string | null>(null);
  const [confirmDeleteSessionId, setConfirmDeleteSessionId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const messagesRef = useRef<ChatMessage[]>([]);
  // Dedupes concurrent session creation so picking multiple files at once (or
  // upload + send racing) never spawns more than one session.
  const createSessionPromiseRef = useRef<Promise<string> | null>(null);

  const uploadingCount = attachments.filter((a) => a.status === "uploading").length;
  const readyCount = attachments.filter((a) => a.status === "ready").length;

  // Fetch existing sessions to restore the most recent one.
  const sessionsQuery = useQuery({
    queryKey: ["ai-assistant", "sessions"],
    queryFn: () => aiAssistantApi.listSessions(),
    enabled: isAuthed && open,
    staleTime: 60_000,
  });

  // When sessions load, restore the most recent or create a new one.
  useEffect(() => {
    if (!isAuthed || !open) return;
    if (sessionsQuery.data && sessionId === null && !draftSession) {
      const recent = sessionsQuery.data[0];
      if (recent) {
        setSessionId(recent.id);
      }
    }
  }, [sessionsQuery.data, sessionId, isAuthed, open, draftSession]);

  // Load messages when session is set.
  const messagesQuery = useQuery({
    queryKey: ["ai-assistant", "messages", sessionId],
    queryFn: () => aiAssistantApi.getMessages(sessionId!),
    enabled: !!sessionId,
    staleTime: 30_000,
  });

  useEffect(() => {
    if (messagesQuery.data && !sending) {
      const localMessages = messagesRef.current;
      const hasLocalDraft = localMessages.some((m) =>
        m.id.startsWith("opt-") || m.id.startsWith("err-") || m.id.startsWith("stream-"),
      );
      if (hasLocalDraft && messagesQuery.data.length < localMessages.length) {
        return;
      }
      setMessages(messagesQuery.data);
    }
  }, [messagesQuery.data, sending]);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  // Scroll to bottom on new messages or streaming text.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending, streamingText]);

  // Focus input when panel opens.
  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 80);
    }
  }, [open]);

  // Cleanup SSE on unmount or close.
  useEffect(() => {
    if (!open) {
      abortRef.current?.abort();
      abortRef.current = null;
      setHistoryOpen(false);
      setConfirmDeleteSessionId(null);
    }
    return () => {
      abortRef.current?.abort();
    };
  }, [open]);

  const ensureSession = useCallback(async (): Promise<string> => {
    if (sessionId) return sessionId;
    if (createSessionPromiseRef.current) return createSessionPromiseRef.current;
    const p = (async () => {
      const s = await aiAssistantApi.createSession();
      setSessionId(s.id);
      setDraftSession(false);
      void qc.invalidateQueries({ queryKey: ["ai-assistant", "sessions"] });
      return s.id;
    })();
    createSessionPromiseRef.current = p;
    try {
      return await p;
    } finally {
      createSessionPromiseRef.current = null;
    }
  }, [sessionId, qc]);

  function startNewChat() {
    abortRef.current?.abort();
    abortRef.current = null;
    setSessionId(null);
    setMessages([]);
    setAttachments([]);
    setStreamingText(null);
    setActiveToolName(null);
    setActivityStatus(null);
    setSending(false);
    setInput("");
    setDraftSession(true);
    setTimeout(() => inputRef.current?.focus(), 40);
  }

  function selectSession(session: ChatSession) {
    if (sending) return;
    abortRef.current?.abort();
    abortRef.current = null;
    setSessionId(session.id);
    setMessages([]);
    setAttachments([]);
    setStreamingText(null);
    setActiveToolName(null);
    setActivityStatus(null);
    setDraftSession(false);
  }

  /** Archive (soft-delete) a session with optimistic removal + rollback on
   * failure. If the deleted session is the active one, fall back to the most
   * recent remaining session or a fresh "new chat" state. */
  async function deleteSession(id: string) {
    if (deletingSessionId) return;
    setDeletingSessionId(id);
    const key = ["ai-assistant", "sessions"] as const;
    const prev =
      qc.getQueryData<ChatSession[]>(key) ?? sessionsQuery.data ?? [];
    const remaining = prev.filter((s) => s.id !== id);
    // Optimistic removal from the list.
    qc.setQueryData<ChatSession[]>(key, remaining);
    try {
      await aiAssistantApi.archiveSession(id);
      qc.removeQueries({ queryKey: ["ai-assistant", "messages", id] });
      if (sessionId === id) {
        abortRef.current?.abort();
        abortRef.current = null;
        setMessages([]);
        setAttachments([]);
        setStreamingText(null);
        setActiveToolName(null);
        setActivityStatus(null);
        setSending(false);
        const next = remaining[0];
        if (next) {
          setSessionId(next.id);
          setDraftSession(false);
        } else {
          setSessionId(null);
          setDraftSession(true);
        }
      }
      void qc.invalidateQueries({ queryKey: [...key] });
    } catch {
      // Roll back the optimistic removal and surface a user-safe error.
      qc.setQueryData<ChatSession[]>(key, prev);
      toast.show({
        tone: "error",
        title: t("deleteErrorTitle"),
        description: t("deleteError"),
      });
    } finally {
      setDeletingSessionId(null);
      setConfirmDeleteSessionId(null);
    }
  }

  /** Upload one file to the current session, showing an optimistic
   * uploading→ready chip. A failed upload drops its chip and surfaces the
   * backend's user-safe rejection message (too large / unsupported / rejected). */
  async function uploadOne(file: File) {
    const localId = `att-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    setAttachments((prev) => [
      ...prev,
      { localId, filename: file.name, size: file.size, status: "uploading" },
    ]);
    try {
      const sid = await ensureSession();
      const descriptor = await aiAssistantApi.uploadAttachment(sid, file);
      setAttachments((prev) =>
        prev.map((a) =>
          a.localId === localId
            ? {
                localId,
                filename: descriptor.filename,
                size: descriptor.size,
                status: "ready",
                descriptor,
              }
            : a,
        ),
      );
    } catch (err) {
      setAttachments((prev) => prev.filter((a) => a.localId !== localId));
      const message =
        err instanceof ApiError && err.message ? err.message : t("attachError");
      toast.show({
        tone: "error",
        title: t("attachErrorTitle"),
        description: message,
      });
    }
  }

  /** Validate a picked file list against remaining slots + type/size, then
   * upload the accepted files. Client checks are a courtesy; the backend is
   * authoritative. */
  function handleFilesPicked(fileList: FileList | null) {
    if (!fileList || fileList.length === 0) return;
    const files = Array.from(fileList);
    const slots = MAX_ATTACHMENTS - attachments.length;
    if (slots <= 0) {
      toast.show({
        tone: "warning",
        title: t("attachLimitTitle"),
        description: t("attachLimit", { max: MAX_ATTACHMENTS }),
      });
      return;
    }
    const accepted: File[] = [];
    for (const file of files) {
      if (accepted.length >= slots) break;
      if (!isAcceptedAttachment(file.name)) {
        toast.show({
          tone: "error",
          title: t("attachErrorTitle"),
          description: t("attachUnsupported"),
        });
        continue;
      }
      if (file.size > MAX_ATTACHMENT_BYTES) {
        toast.show({
          tone: "error",
          title: t("attachErrorTitle"),
          description: t("attachTooLarge"),
        });
        continue;
      }
      accepted.push(file);
    }
    if (files.length > slots) {
      toast.show({
        tone: "warning",
        title: t("attachLimitTitle"),
        description: t("attachLimit", { max: MAX_ATTACHMENTS }),
      });
    }
    for (const file of accepted) {
      void uploadOne(file);
    }
  }

  function removeAttachment(localId: string) {
    setAttachments((prev) => prev.filter((a) => a.localId !== localId));
  }

  async function send(textOverride?: string) {
    const text = (textOverride ?? input).trim();
    const ready = attachments.filter(
      (a): a is ComposerAttachment & { descriptor: ChatAttachment } =>
        a.status === "ready" && !!a.descriptor,
    );
    // Block while an upload is still in flight so refs are never dropped.
    if ((!text && ready.length === 0) || sending || uploadingCount > 0) return;

    // Embed a machine-readable analyze reference per ready attachment so the
    // assistant sees the id and calls its analyze_attachment tool. The bubble
    // renderer strips these lines back out and shows a paperclip chip instead.
    const refLines = ready
      .map((a) => buildAttachmentRef(a.descriptor.filename, a.descriptor.id))
      .join("");
    const outgoing = `${text}${refLines}`;

    setInput("");
    setAttachments([]);
    setSending(true);
    setStreamingText(null);
    setActiveToolName(null);
    setActivityStatus(t("statusReceived"));

    // Optimistic user message
    const optimistic: ChatMessage = {
      id: `opt-${Date.now()}`,
      session_id: sessionId ?? "",
      role: "user",
      content: outgoing,
      tool_name: null,
      tool_args: null,
      tool_result: null,
      requires_confirmation: false,
      confirmed_at: null,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimistic]);

    try {
      const sid = await ensureSession();
      await streamMessage(sid, outgoing, optimistic);
    } catch {
      setMessages((prev) => {
        const hasOptimistic = prev.some((m) => m.id === optimistic.id);
        const errMsg: ChatMessage = {
          id: `err-${Date.now()}`,
          session_id: sessionId ?? optimistic.session_id,
          role: "assistant",
          content: t("sendError"),
          tool_name: null,
          tool_args: null,
          tool_result: null,
          requires_confirmation: false,
          confirmed_at: null,
          created_at: new Date().toISOString(),
        };
        return hasOptimistic ? [...prev, errMsg] : [...prev, optimistic, errMsg];
      });
    } finally {
      setSending(false);
      setStreamingText(null);
      setActiveToolName(null);
      setActivityStatus(null);
    }
  }

  function mergeAssistantTurn(
    baseMessages: ChatMessage[],
    targetSessionId: string,
    optimistic: ChatMessage,
    assistant: ChatMessage,
  ) {
    const userMessage = { ...optimistic, session_id: targetSessionId };
    const filtered = baseMessages.filter(
      (m) => m.id !== optimistic.id && m.id !== assistant.id,
    );
    return [...filtered, userMessage, assistant];
  }

  function commitAssistantTurn(
    targetSessionId: string,
    optimistic: ChatMessage,
    assistant: ChatMessage,
  ) {
    const next = mergeAssistantTurn(
      messagesRef.current,
      targetSessionId,
      optimistic,
      assistant,
    );
    messagesRef.current = next;
    setMessages(next);
    qc.setQueryData(["ai-assistant", "messages", targetSessionId], next);
  }

  async function streamMessage(sid: string, text: string, optimistic: ChatMessage) {
    const ac = new AbortController();
    abortRef.current = ac;

    const sendViaHttp = async (targetSessionId: string) => {
      const reply = await aiAssistantApi.sendMessage(targetSessionId, text);
      commitAssistantTurn(targetSessionId, optimistic, reply);
      void qc.invalidateQueries({
        queryKey: ["ai-assistant", "messages", targetSessionId],
      });
    };

    const restartWithFreshSession = async () => {
      const fresh = await aiAssistantApi.createSession();
      setSessionId(fresh.id);
      setDraftSession(false);
      void qc.invalidateQueries({ queryKey: ["ai-assistant", "sessions"] });
      await sendViaHttp(fresh.id);
    };

    const base = env.apiBaseUrl.replace(/\/$/, "");
    const url = `${base}/ai/chat/sessions/${sid}/messages/stream`;
    const token = getAccessToken();
    const res = await fetch(url, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ text }),
      signal: ac.signal,
    });

    if (!res.ok || !res.body) {
      // Fall back to non-streaming send
      await sendViaHttp(sid);
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let accumulated = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const jsonStr = line.slice(6).trim();
        if (!jsonStr) continue;

        let event: StreamEvent;
        try {
          event = JSON.parse(jsonStr) as StreamEvent;
        } catch {
          continue;
        }

        if (event.type === "status") {
          setActivityStatus(STATUS_LABELS[event.code] ?? t("statusThinking"));
        } else if (event.type === "tool_call") {
          setActivityStatus(STATUS_LABELS.using_tool ?? t("statusThinking"));
          setActiveToolName(event.name);
        } else if (event.type === "tool_result") {
          setActiveToolName(null);
          setActivityStatus(STATUS_LABELS.synthesizing ?? t("statusThinking"));
        } else if (event.type === "token") {
          accumulated += event.text;
          setActivityStatus(STATUS_LABELS.responding ?? t("statusThinking"));
          setStreamingText(accumulated);
        } else if (event.type === "done") {
          const finalMsg = event.message;
          setStreamingText(null);
          setActiveToolName(null);
          setActivityStatus(null);
          commitAssistantTurn(sid, optimistic, finalMsg);
          void qc.invalidateQueries({ queryKey: ["ai-assistant", "messages", sid] });
          return;
        } else if (event.type === "error") {
          if (event.code === "session_not_found") {
            await restartWithFreshSession();
            return;
          }
          await sendViaHttp(sid);
          return;
        }
      }
    }

    // Stream ended without done — flush any accumulated text
    if (accumulated) {
      const fallbackMsg: ChatMessage = {
        id: `stream-${Date.now()}`,
        session_id: sid,
        role: "assistant",
        content: accumulated,
        tool_name: null,
        tool_args: null,
        tool_result: null,
        requires_confirmation: false,
        confirmed_at: null,
        created_at: new Date().toISOString(),
      };
      commitAssistantTurn(sid, optimistic, fallbackMsg);
    }
  }

  async function confirmTool(message: ChatMessage) {
    if (!sessionId || confirmingMessageId) return;
    setConfirmingMessageId(message.id);
    try {
      const result = await aiAssistantApi.confirmToolAction(sessionId, message.id);
      const next = messagesRef.current
        .map((m) => (m.id === message.id ? result.confirmed : m))
        .concat(result.reply);
      messagesRef.current = next;
      setMessages(next);
      qc.setQueryData(["ai-assistant", "messages", sessionId], next);
      void qc.invalidateQueries({ queryKey: ["ai-assistant", "messages", sessionId] });
    } catch {
      const errMsg: ChatMessage = {
        id: `err-${Date.now()}`,
        session_id: sessionId,
        role: "assistant",
        content: t("toolConfirmError"),
        tool_name: null,
        tool_args: null,
        tool_result: null,
        requires_confirmation: false,
        confirmed_at: null,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setConfirmingMessageId(null);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  }

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-label={t("panelTitle")}
      aria-modal="true"
      className={cn(
        "fixed z-50 flex flex-col",
        expanded
          ? "inset-4 w-auto"
          : "bottom-20 right-4 w-[min(92vw,400px)]",
        "rounded-2xl border border-[var(--glass-border)] shadow-[0_8px_40px_rgba(11,34,57,0.18)] backdrop-blur-xl",
        "bg-[var(--glass-surface)]",
        "animate-in fade-in slide-in-from-bottom-4 duration-200",
      )}
      style={{ maxHeight: expanded ? "calc(100vh - 2rem)" : "min(80vh, 640px)" }}
    >
      {/* Header */}
      <div
        className="flex items-center gap-2.5 rounded-t-2xl border-b border-[var(--glass-border)] px-4 py-3"
        style={{
          background: "linear-gradient(135deg, rgba(23,23,23,0.06) 0%, rgba(5,150,105,0.06) 100%)",
        }}
      >
        <span className="relative flex size-7 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-[var(--brand-primary)] to-[var(--brand-teal)] shadow-[var(--shadow-sm)]">
          <Robot aria-hidden weight="fill" className="size-4 text-white" />
          {/* Live indicator */}
          {isAuthed && (
            <span className="absolute -right-0.5 -top-0.5 size-2 rounded-full border border-[var(--surface-card)] bg-[var(--teal-400)]" />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-bold text-[var(--text-primary)]">
            {t("panelTitle")}
          </p>
          <p className="text-[11px] text-[var(--text-muted)]">
            {t("panelSubtitle")}
          </p>
        </div>
        {isAuthed && (
          <button
            type="button"
            onClick={() => setHistoryOpen((v) => !v)}
            aria-label={t("history")}
            title={t("history")}
            aria-expanded={historyOpen}
            aria-pressed={historyOpen}
            className={cn(
              "rounded-lg p-1 outline-none transition hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40",
              historyOpen
                ? "bg-[var(--bg-subtle)] text-[var(--text-primary)]"
                : "text-[var(--text-muted)]",
              // The persistent rail already shows history on the expanded desktop layout.
              expanded && "lg:hidden",
            )}
          >
            <ClockCounterClockwise aria-hidden weight="bold" className="size-4" />
          </button>
        )}
        <button
          type="button"
          onClick={startNewChat}
          aria-label={t("newChat")}
          title={t("newChat")}
          className="rounded-lg p-1 text-[var(--text-muted)] outline-none transition hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
        >
          <Plus aria-hidden weight="bold" className="size-4" />
        </button>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-label={expanded ? t("collapse") : t("expand")}
          title={expanded ? t("collapse") : t("expand")}
          className="rounded-lg p-1 text-[var(--text-muted)] outline-none transition hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
        >
          {expanded ? (
            <ArrowsInSimple aria-hidden weight="bold" className="size-4" />
          ) : (
            <ArrowsOutSimple aria-hidden weight="bold" className="size-4" />
          )}
        </button>
        <button
          type="button"
          onClick={onClose}
          aria-label={t("close")}
          className="rounded-lg p-1 text-[var(--text-muted)] outline-none transition hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
        >
          <X aria-hidden weight="bold" className="size-4" />
        </button>
      </div>

      <div className={cn("relative flex min-h-0 flex-1", expanded && "lg:grid lg:grid-cols-[260px_minmax(0,1fr)]")}>
        {expanded && isAuthed && (
          <SessionRail
            sessions={sessionsQuery.data ?? []}
            activeId={sessionId}
            loading={sessionsQuery.isPending}
            deletingId={deletingSessionId}
            confirmDeleteId={confirmDeleteSessionId}
            onNew={startNewChat}
            onSelect={selectSession}
            onRequestDelete={setConfirmDeleteSessionId}
            onCancelDelete={() => setConfirmDeleteSessionId(null)}
            onConfirmDelete={(id) => void deleteSession(id)}
            t={t}
          />
        )}

        {/* History overlay — reachable at every viewport and in the collapsed panel. */}
        {isAuthed && (
          <SessionHistorySheet
            open={historyOpen}
            title={t("history")}
            closeLabel={t("historyClose")}
            onClose={() => setHistoryOpen(false)}
          >
            <SessionList
              sessions={sessionsQuery.data ?? []}
              activeId={sessionId}
              loading={sessionsQuery.isPending}
              deletingId={deletingSessionId}
              confirmDeleteId={confirmDeleteSessionId}
              onNew={() => {
                startNewChat();
                setHistoryOpen(false);
              }}
              onSelect={(session) => {
                selectSession(session);
                setHistoryOpen(false);
              }}
              onRequestDelete={setConfirmDeleteSessionId}
              onCancelDelete={() => setConfirmDeleteSessionId(null)}
              onConfirmDelete={(id) => void deleteSession(id)}
              t={t}
            />
          </SessionHistorySheet>
        )}

        {/* Messages */}
        <div className="flex min-h-[260px] flex-1 flex-col gap-3 overflow-y-auto p-4">
          {isAuthLoading ? (
            <AuthLoadingPrompt />
          ) : !isAuthed ? (
            <GuestPrompt t={t} />
          ) : messages.length === 0 && !messagesQuery.isPending ? (
            <WelcomeScreen t={t} onPrompt={(prompt) => void send(prompt)} />
          ) : (
            messages.map((msg) => (
              <MessageBubble
                key={msg.id}
                message={msg}
                expanded={expanded}
                confirming={confirmingMessageId === msg.id}
                onConfirm={() => void confirmTool(msg)}
                t={t}
              />
            ))
          )}

          {(activityStatus || activeToolName) && (
            <AssistantActivity status={activityStatus} toolName={activeToolName} />
          )}

          {/* Streaming text bubble */}
          {streamingText && !activeToolName && (
            <StreamingBubble text={streamingText} expanded={expanded} />
          )}

          {/* Typing indicator (before streaming starts) */}
          {sending && !streamingText && !activeToolName && <TypingIndicator />}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input */}
      {isAuthed && (
        <div className="border-t border-[var(--glass-border)] px-3 pb-3 pt-2.5">
          {/* Pending attachment chips */}
          {attachments.length > 0 && (
            <ul
              aria-label={t("attachmentsLabel")}
              className="mb-2 flex flex-wrap gap-1.5"
            >
              {attachments.map((a) => (
                <li
                  key={a.localId}
                  className="flex max-w-[220px] items-center gap-1.5 rounded-lg border border-[var(--glass-border-strong)] bg-[var(--glass-surface-heavy)] py-1 pl-2 pr-1 text-xs text-[var(--text-primary)]"
                >
                  {a.status === "uploading" ? (
                    <Spinner
                      aria-hidden
                      weight="bold"
                      className="size-3.5 shrink-0 animate-spin text-[var(--text-muted)]"
                    />
                  ) : (
                    <Paperclip
                      aria-hidden
                      weight="bold"
                      className="size-3.5 shrink-0 text-[var(--text-muted)]"
                    />
                  )}
                  <span className="min-w-0 flex-1 truncate" title={a.filename}>
                    {a.filename}
                  </span>
                  <span className="shrink-0 text-[10px] tabular-nums text-[var(--text-muted)]">
                    {a.status === "uploading"
                      ? t("attachmentUploading")
                      : formatSize(a.size)}
                  </span>
                  <button
                    type="button"
                    onClick={() => removeAttachment(a.localId)}
                    aria-label={t("removeAttachment", { name: a.filename })}
                    className="shrink-0 rounded p-0.5 text-[var(--text-muted)] outline-none transition hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
                  >
                    <X aria-hidden weight="bold" className="size-3" />
                  </button>
                </li>
              ))}
            </ul>
          )}

          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={ACCEPTED_ATTACHMENT_ACCEPT}
            tabIndex={-1}
            aria-hidden="true"
            className="sr-only"
            onChange={(e) => {
              handleFilesPicked(e.target.files);
              // Reset so re-picking the same file fires onChange again.
              e.target.value = "";
            }}
          />

          <div className="flex items-end gap-2 rounded-xl border border-[var(--glass-border)] bg-[var(--glass-surface)] px-3 py-2 shadow-[0_1px_4px_rgba(11,34,57,0.06)] transition-all focus-within:border-[var(--brand-primary)]/50 focus-within:bg-[var(--glass-surface-heavy)] focus-within:shadow-[0_2px_8px_rgba(11,34,57,0.10)]">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value.slice(0, MAX_INPUT_LENGTH))}
              onKeyDown={handleKeyDown}
              placeholder={t("inputPlaceholder")}
              aria-label={t("inputPlaceholder")}
              rows={1}
              disabled={sending}
              className="flex-1 resize-none bg-transparent text-sm leading-snug text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)] disabled:opacity-60"
              style={{ maxHeight: "100px" }}
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={
                sending ||
                uploadingCount > 0 ||
                attachments.length >= MAX_ATTACHMENTS
              }
              aria-label={t("attach")}
              title={t("attach")}
              className={cn(
                "mb-0.5 shrink-0 rounded-lg p-1.5 outline-none transition-all",
                "text-[var(--text-muted)] hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)]",
                "focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40",
                "disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent",
              )}
            >
              <Paperclip aria-hidden weight="bold" className="size-4" />
            </button>
            <button
              type="button"
              onClick={() => void send()}
              disabled={(!input.trim() && readyCount === 0) || sending || uploadingCount > 0}
              aria-label={t("sendBtn")}
              className={cn(
                "shrink-0 rounded-lg p-1.5 outline-none transition-all",
                "text-white focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40",
                (input.trim() || readyCount > 0) && !sending && uploadingCount === 0
                  ? "bg-[var(--brand-primary)] hover:bg-[var(--brand-primary)]/90 shadow-[0_1px_4px_rgba(45,95,166,0.30)]"
                  : "bg-[var(--text-muted)]/30 cursor-not-allowed",
              )}
            >
              {sending ? (
                <Spinner aria-hidden weight="bold" className="size-3.5 animate-spin" />
              ) : (
                <ArrowUp aria-hidden weight="bold" className="size-3.5" />
              )}
            </button>
          </div>
          <p className="mt-1.5 text-center text-[11px] text-[var(--text-muted)]">
            {t("disclaimer")}
          </p>
        </div>
      )}
    </div>
  );
}
