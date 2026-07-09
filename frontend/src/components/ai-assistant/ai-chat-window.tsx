"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowsInSimple,
  ArrowsOutSimple,
  ArrowUp,
  Check,
  PencilSimple,
  Plus,
  Spinner,
  X,
} from "@phosphor-icons/react";
import { Sparkles } from "lucide-react";
import { aiAssistantApi, type ChatMessage, type ChatSession } from "@/lib/api";
import { getAccessToken } from "@/lib/api/session";
import { env } from "@/lib/env";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth-store";
import { MAX_INPUT_LENGTH, STATUS_LABELS, type StreamEvent } from "./chat-window/constants";
import {
  AssistantActivity,
  MessageBubble,
  StreamingBubble,
  TypingIndicator,
} from "./chat-window/message-bubble";
import { SessionRail } from "./chat-window/session-rail";
import { AuthLoadingPrompt, GuestPrompt, WelcomeScreen } from "./chat-window/welcome-screen";

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
  variant = "floating",
}: {
  open: boolean;
  onClose: () => void;
  variant?: "floating" | "embedded";
}) {
  const t = useTranslations("aiAssistant");
  const authStatus = useAuthStore((s) => s.status);
  // Persona drives the persona-specific greeting, quick prompts, and shortcut
  // links so a partner recruiter never sees the student CV/applications welcome.
  const persona = useAuthStore((s) => s.user?.persona) ?? "student";
  const isAuthed = authStatus === "authenticated";
  const isAuthLoading = authStatus === "unknown";
  const qc = useQueryClient();

  const [sessionId, setSessionId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [streamingText, setStreamingText] = useState<string | null>(null);
  const [activeToolName, setActiveToolName] = useState<string | null>(null);
  const [activityStatus, setActivityStatus] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [expanded, setExpanded] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [renameDraft, setRenameDraft] = useState("");
  const [savingTitle, setSavingTitle] = useState(false);
  const [draftSession, setDraftSession] = useState(false);
  const [confirmingMessageId, setConfirmingMessageId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const messagesRef = useRef<ChatMessage[]>([]);

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

  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 112)}px`;
    el.style.overflowY = el.scrollHeight > 112 ? "auto" : "hidden";
  }, [input]);

  // Cleanup SSE on unmount or close.
  useEffect(() => {
    if (!open) {
      abortRef.current?.abort();
      abortRef.current = null;
    }
    return () => {
      abortRef.current?.abort();
    };
  }, [open]);

  const ensureSession = useCallback(async (): Promise<string> => {
    if (sessionId) return sessionId;
    const s = await aiAssistantApi.createSession();
    setSessionId(s.id);
    setDraftSession(false);
    void qc.invalidateQueries({ queryKey: ["ai-assistant", "sessions"] });
    return s.id;
  }, [sessionId, qc]);

  function startNewChat() {
    abortRef.current?.abort();
    abortRef.current = null;
    setSessionId(null);
    setMessages([]);
    setStreamingText(null);
    setActiveToolName(null);
    setActivityStatus(null);
    setSending(false);
    setInput("");
    setDraftSession(true);
    setHistoryOpen(false);
    setTimeout(() => inputRef.current?.focus(), 40);
  }

  function selectSession(session: ChatSession) {
    if (sending) return;
    abortRef.current?.abort();
    abortRef.current = null;
    setSessionId(session.id);
    setMessages([]);
    setStreamingText(null);
    setActiveToolName(null);
    setActivityStatus(null);
    setDraftSession(false);
    setHistoryOpen(false);
  }

  async function send(textOverride?: string) {
    const text = (textOverride ?? input).trim();
    if (!text || sending) return;

    setInput("");
    setSending(true);
    setStreamingText(null);
    setActiveToolName(null);
    setActivityStatus(t("statusReceived"));

    // Optimistic user message
    const optimistic: ChatMessage = {
      id: `opt-${Date.now()}`,
      session_id: sessionId ?? "",
      role: "user",
      content: text,
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
      await streamMessage(sid, text, optimistic);
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

  const embedded = variant === "embedded";
  const showExpandedLayout = expanded && !embedded;
  const isWorkspaceFullscreen = embedded && expanded;
  const showHistoryPane = historyOpen || showExpandedLayout;
  const historyAsFullPanel = historyOpen && embedded && !expanded;
  const activeSession = sessionsQuery.data?.find((session) => session.id === sessionId);
  const currentTitle = draftSession
    ? t("untitledSession")
    : (activeSession?.title || t("untitledSession"));

  function startRename() {
    setRenameDraft(currentTitle);
    setRenaming(true);
    setHistoryOpen(false);
  }

  async function saveRename() {
    if (!sessionId || savingTitle) return;
    const title = renameDraft.trim();
    if (!title) return;
    setSavingTitle(true);
    try {
      const updated = await aiAssistantApi.renameSession(sessionId, title);
      qc.setQueryData<ChatSession[]>(["ai-assistant", "sessions"], (prev) =>
        prev?.map((session) => (session.id === updated.id ? updated : session)) ?? [updated],
      );
      await qc.invalidateQueries({ queryKey: ["ai-assistant", "sessions"] });
      setRenaming(false);
    } finally {
      setSavingTitle(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-label={t("panelTitle")}
      aria-modal={embedded && !isWorkspaceFullscreen ? undefined : true}
      className={cn(
        "flex min-h-0 flex-col bg-[var(--surface-card)]",
        embedded
          ? isWorkspaceFullscreen
            ? "fixed inset-x-0 bottom-0 top-[60px] z-[60] h-[calc(100dvh-60px)] w-screen overflow-hidden bg-[var(--surface-card)] animate-in slide-in-from-right-4 duration-200"
            : "h-full w-full overflow-hidden"
          : cn(
              "fixed z-50 rounded-2xl border border-[var(--glass-border)] shadow-[0_8px_40px_rgba(11,34,57,0.18)] backdrop-blur-xl",
              expanded ? "inset-4 w-auto" : "bottom-20 right-4 w-[min(92vw,400px)]",
              "bg-[var(--glass-surface)] animate-in fade-in slide-in-from-bottom-4 duration-200",
            ),
      )}
      style={
        embedded
          ? undefined
          : { maxHeight: expanded ? "calc(100vh - 2rem)" : "min(80vh, 640px)" }
      }
    >
      {/* Header */}
      <div
        className={cn(
          "flex items-center gap-2.5 border-b border-[var(--border-default)] px-4 py-2.5",
          embedded ? "bg-[var(--surface-card)]" : "rounded-t-2xl bg-[var(--bg-subtle)]",
        )}
      >
        <Sparkles
          aria-hidden
          strokeWidth={1.9}
          className="size-5 shrink-0 text-[var(--text-primary)]"
        />
        <div className="min-w-0 flex-1">
          <p className="truncate text-[0.8125rem] font-bold text-[var(--text-primary)]">
            {t("panelTitle")}
          </p>
        </div>
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

      <div className="flex h-10 shrink-0 items-center gap-2 border-b border-[var(--border-subtle)] px-3">
        {historyOpen ? (
          <p className="min-w-0 flex-1 truncate text-[0.8125rem] font-semibold text-[var(--text-primary)]">
            {t("conversationHistory")}
          </p>
        ) : (
          <>
            <button
              type="button"
              onClick={() => setHistoryOpen(true)}
              aria-label={t("conversationHistory")}
              title={t("conversationHistory")}
              className="rounded-lg p-1.5 text-[var(--text-muted)] outline-none transition hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
            >
              <ArrowLeft aria-hidden weight="bold" className="size-4" />
            </button>
            {renaming ? (
              <input
                value={renameDraft}
                onChange={(event) => setRenameDraft(event.target.value.slice(0, 120))}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    void saveRename();
                  }
                  if (event.key === "Escape") {
                    setRenaming(false);
                  }
                }}
                autoFocus
                className="min-w-0 flex-1 rounded-lg border border-[var(--border-default)] bg-[var(--surface-card)] px-2.5 py-1 text-[0.8125rem] font-semibold text-[var(--text-primary)] outline-none focus:border-[var(--text-primary)]/35"
              />
            ) : (
              <p className="min-w-0 flex-1 truncate text-[0.8125rem] font-semibold text-[var(--text-primary)]">
                {currentTitle}
              </p>
            )}
            <button
              type="button"
              onClick={() => (renaming ? void saveRename() : startRename())}
              disabled={renaming && (!renameDraft.trim() || savingTitle || !sessionId)}
              aria-label={renaming ? t("saveTitle") : t("renameSession")}
              title={renaming ? t("saveTitle") : t("renameSession")}
              className="rounded-lg p-1.5 text-[var(--text-muted)] outline-none transition hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40 disabled:cursor-not-allowed disabled:opacity-45"
            >
              {savingTitle ? (
                <Spinner aria-hidden weight="bold" className="size-4 animate-spin" />
              ) : renaming ? (
                <Check aria-hidden weight="bold" className="size-4" />
              ) : (
                <PencilSimple aria-hidden weight="bold" className="size-4" />
              )}
            </button>
            <button
              type="button"
              onClick={startNewChat}
              aria-label={t("newChat")}
              title={t("newChat")}
              className="rounded-lg p-1.5 text-[var(--text-muted)] outline-none transition hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
            >
              <Plus aria-hidden weight="bold" className="size-4" />
            </button>
          </>
        )}
      </div>

      <div className="flex min-h-0 flex-1">
        {showHistoryPane && isAuthed && (
          <SessionRail
            sessions={sessionsQuery.data ?? []}
            activeId={sessionId}
            loading={sessionsQuery.isPending}
            onNew={startNewChat}
            onSelect={selectSession}
            t={t}
            searchable
            showHeading={!historyAsFullPanel}
            showNewButton={false}
            className={cn(
              "w-[280px] shrink-0",
              historyAsFullPanel && "!flex w-full border-r-0",
              !historyAsFullPanel && "!hidden lg:!flex",
            )}
          />
        )}

        <div className={cn("flex min-w-0 flex-1 flex-col", historyAsFullPanel && "hidden")}>
          {/* Messages */}
          <div
            className={cn(
              "flex flex-1 flex-col gap-3 overflow-y-auto p-4",
              embedded ? "min-h-0 text-[0.9rem]" : "min-h-[260px]",
            )}
          >
            {isAuthLoading ? (
              <AuthLoadingPrompt />
            ) : !isAuthed ? (
              <GuestPrompt t={t} />
            ) : messages.length === 0 && !messagesQuery.isPending ? (
              <WelcomeScreen t={t} persona={persona} onPrompt={(prompt) => void send(prompt)} />
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

          {/* Input */}
          {isAuthed && (
            <div className="border-t border-[var(--border-default)] bg-[var(--surface-card)] px-4 pb-3 pt-3">
              <div className="flex items-end gap-2">
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value.slice(0, MAX_INPUT_LENGTH))}
                  onKeyDown={handleKeyDown}
                  placeholder={t("inputPlaceholder")}
                  aria-label={t("inputPlaceholder")}
                  rows={1}
                  wrap="soft"
                  disabled={sending}
                  className="min-h-9 min-w-0 flex-1 resize-none appearance-none overflow-y-hidden overflow-x-hidden rounded-xl border border-[var(--border-default)] bg-transparent px-3 py-2 text-[0.8125rem] leading-5 text-[var(--text-primary)] outline-none [overflow-wrap:anywhere] [word-break:break-word] placeholder:text-[var(--text-muted)] focus:border-[var(--text-primary)]/35 focus:ring-0 disabled:opacity-60"
                  style={{ maxHeight: "112px" }}
                />
                <button
                  type="button"
                  onClick={() => void send()}
                  disabled={!input.trim() || sending}
                  aria-label={t("sendBtn")}
                  className={cn(
                    "flex size-8 shrink-0 items-center justify-center rounded-full outline-none transition-all",
                    "text-white focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40",
                    input.trim() && !sending
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
      </div>
    </div>
  );
}
