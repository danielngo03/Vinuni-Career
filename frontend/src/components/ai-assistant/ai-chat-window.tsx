"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowUp,
  Check,
  Loader2,
  Maximize2,
  Minimize2,
  Paperclip,
  Pencil,
  Plus,
  Sparkles,
  X,
} from "lucide-react";
import { aiAssistantApi, type ChatMessage, type ChatSession } from "@/lib/api";
import { getAccessToken } from "@/lib/api/session";
import { env } from "@/lib/env";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth-store";
import {
  ACCEPTED_ATTACHMENT_ACCEPT,
  buildAttachmentRef,
  isAcceptedAttachment,
  MAX_ATTACHMENT_BYTES,
  MAX_ATTACHMENTS,
  MAX_INPUT_LENGTH,
  type StreamEvent,
} from "./chat-window/constants";
import {
  MessageBubble,
  PhaseIndicator,
  StreamingBubble,
  type ToolResolution,
} from "./chat-window/message-bubble";
import { SessionRail } from "./chat-window/session-rail";
import { AuthLoadingPrompt, GuestPrompt, WelcomeScreen } from "./chat-window/welcome-screen";

/**
 * Map a tool-call to a leak-safe phase code. The tool NAME is never rendered —
 * this only advances the animated "thinking" line when the backend omits an
 * explicit `status` event. Frozen leak-safe codes only (AI_PRODUCT_SPEC §9).
 */
function derivePhaseFromTool(name: string): string {
  if (name.startsWith("export_")) return "exporting";
  if (name === "generate_image") return "generating_image";
  return "retrieving";
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
  // Leak-safe high-level phase code for the animated "thinking" line. Never a
  // raw tool/provider/model name — it only maps to localized `phase.*` text.
  const [phase, setPhase] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [expanded, setExpanded] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [renameDraft, setRenameDraft] = useState("");
  const [savingTitle, setSavingTitle] = useState(false);
  const [draftSession, setDraftSession] = useState(false);
  const [confirmingAction, setConfirmingAction] = useState<{
    id: string;
    decision: "confirm" | "cancel";
  } | null>(null);
  // Local record of how tool-calls were resolved (cancel has no server marker).
  const [resolvedActions, setResolvedActions] = useState<Record<string, ToolResolution>>({});
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const [editBusy, setEditBusy] = useState(false);
  const [attachments, setAttachments] = useState<
    { localId: string; filename: string; status: "uploading" | "ready" | "error"; id?: string }[]
  >([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
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
    setPhase(null);
    setSending(false);
    setInput("");
    setDraftSession(true);
    setHistoryOpen(false);
    setResolvedActions({});
    setEditingMessageId(null);
    setTimeout(() => inputRef.current?.focus(), 40);
  }

  function selectSession(session: ChatSession) {
    if (sending) return;
    abortRef.current?.abort();
    abortRef.current = null;
    setSessionId(session.id);
    setMessages([]);
    setStreamingText(null);
    setPhase(null);
    setDraftSession(false);
    setHistoryOpen(false);
    setResolvedActions({});
    setEditingMessageId(null);
  }

  async function send(textOverride?: string) {
    if (attachments.some((a) => a.status === "uploading")) return;
    const ready = attachments.filter((a) => a.status === "ready" && a.id);
    const refs = ready.map((a) => buildAttachmentRef(a.filename, a.id!)).join("");
    const text = ((textOverride ?? input).trim() + refs).trim();
    if (!text || sending) return;

    setInput("");
    setAttachments([]);
    setSending(true);
    setStreamingText(null);
    setPhase(null);

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
      setPhase(null);
    }
  }

  async function handleFilesPicked(files: FileList | null) {
    if (!files || files.length === 0) return;
    const room = MAX_ATTACHMENTS - attachments.length;
    const picked = Array.from(files).slice(0, Math.max(0, room));
    if (fileInputRef.current) fileInputRef.current.value = "";
    for (const [idx, file] of picked.entries()) {
      const localId = `att-${Date.now()}-${idx}-${file.size}`;
      if (!isAcceptedAttachment(file.name) || file.size > MAX_ATTACHMENT_BYTES) {
        setAttachments((prev) => [
          ...prev,
          { localId, filename: file.name, status: "error" as const },
        ]);
        continue;
      }
      setAttachments((prev) => [
        ...prev,
        { localId, filename: file.name, status: "uploading" as const },
      ]);
      try {
        const sid = await ensureSession();
        const desc = await aiAssistantApi.uploadAttachment(sid, file);
        setAttachments((prev) =>
          prev.map((a) =>
            a.localId === localId ? { ...a, status: "ready" as const, id: desc.id } : a,
          ),
        );
      } catch {
        setAttachments((prev) =>
          prev.map((a) => (a.localId === localId ? { ...a, status: "error" as const } : a)),
        );
      }
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
          // Authoritative leak-safe phase code from the backend.
          setPhase(event.code);
        } else if (event.type === "tool_call") {
          // Never render the tool name; only derive a leak-safe phase from it
          // so the animated line stays lively if a `status` event is missing.
          setPhase(derivePhaseFromTool(event.name));
        } else if (event.type === "tool_result") {
          setPhase("analyzing");
        } else if (event.type === "token") {
          accumulated += event.text;
          setStreamingText(accumulated);
        } else if (event.type === "done") {
          const finalMsg = event.message;
          setStreamingText(null);
          setPhase(null);
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

  function appendLocalError(content: string) {
    const errMsg: ChatMessage = {
      id: `err-${Date.now()}`,
      session_id: sessionId ?? "",
      role: "assistant",
      content,
      tool_name: null,
      tool_args: null,
      tool_result: null,
      requires_confirmation: false,
      confirmed_at: null,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, errMsg]);
  }

  /** Confirm or cancel a pending AI write action. The confirmation gate is
   * preserved: nothing executes until the user explicitly decides. */
  async function resolveTool(message: ChatMessage, decision: "confirm" | "cancel") {
    if (!sessionId || confirmingAction) return;
    setConfirmingAction({ id: message.id, decision });
    try {
      const result = await aiAssistantApi.confirmToolAction(sessionId, message.id, decision);
      const confirmedMsg =
        result.confirmed && typeof result.confirmed === "object" ? result.confirmed : null;
      const next = messagesRef.current
        .map((m) => (m.id === message.id ? (confirmedMsg ?? m) : m))
        .concat(result.reply);
      messagesRef.current = next;
      setMessages(next);
      setResolvedActions((prev) => ({
        ...prev,
        [message.id]: decision === "confirm" ? "confirmed" : "canceled",
      }));
      qc.setQueryData(["ai-assistant", "messages", sessionId], next);
      void qc.invalidateQueries({ queryKey: ["ai-assistant", "messages", sessionId] });
    } catch {
      appendLocalError(t("toolConfirmError"));
    } finally {
      setConfirmingAction(null);
    }
  }

  /** Refetch and commit the full thread (after a server-side edit re-run). */
  async function reloadThread(sid: string) {
    const fresh = await aiAssistantApi.getMessages(sid);
    messagesRef.current = fresh;
    setMessages(fresh);
    qc.setQueryData(["ai-assistant", "messages", sid], fresh);
  }

  /** Edit the last user message: server truncates later turns and re-runs. */
  async function submitEdit(message: ChatMessage, text: string) {
    if (!sessionId || editBusy || sending) return;
    setEditBusy(true);
    setSending(true);
    setEditingMessageId(null);
    // Optimistic: swap in the edited text and truncate everything after it.
    const idx = messagesRef.current.findIndex((m) => m.id === message.id);
    if (idx >= 0) {
      const truncated = [
        ...messagesRef.current.slice(0, idx),
        { ...message, content: text },
      ];
      messagesRef.current = truncated;
      setMessages(truncated);
    }
    try {
      await aiAssistantApi.editMessage(sessionId, message.id, text);
      await reloadThread(sessionId);
    } catch {
      appendLocalError(t("editFailed"));
      void qc.invalidateQueries({ queryKey: ["ai-assistant", "messages", sessionId] });
    } finally {
      setSending(false);
      setEditBusy(false);
    }
  }

  /** Archive (soft-delete) a session from the history rail. */
  async function deleteSession(session: ChatSession) {
    await aiAssistantApi.archiveSession(session.id);
    qc.setQueryData<ChatSession[]>(
      ["ai-assistant", "sessions"],
      (prev) => prev?.filter((s) => s.id !== session.id) ?? [],
    );
    void qc.invalidateQueries({ queryKey: ["ai-assistant", "sessions"] });
    if (session.id === sessionId) {
      abortRef.current?.abort();
      abortRef.current = null;
      setSessionId(null);
      setMessages([]);
      setStreamingText(null);
      setPhase(null);
      setResolvedActions({});
      setEditingMessageId(null);
      // Not a draft: the restore effect picks the next most-recent session.
      setDraftSession(false);
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
  // In the compact (non-expanded) panel — floating or embedded — the history
  // list takes over the whole panel so the session rail (with its always-visible
  // "new chat" button) is never clipped by a breakpoint.
  const historyAsFullPanel = historyOpen && !expanded && isAuthed;
  const activeSession = sessionsQuery.data?.find((session) => session.id === sessionId);
  const currentTitle = draftSession
    ? t("untitledSession")
    : (activeSession?.title || t("untitledSession"));

  // Conversation management targets: only server-persisted messages qualify
  // (optimistic/error/stream drafts have local prefixes and no server row).
  const isServerId = (id: string) => !/^(opt|err|stream)-/.test(id);
  const lastUserMessage = [...messages].reverse().find((m) => m.role === "user");
  const editableMessageId =
    sessionId && !sending && lastUserMessage && isServerId(lastUserMessage.id)
      ? lastUserMessage.id
      : null;

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
              "fixed z-50 rounded-2xl border border-[var(--border-default)] shadow-[var(--shadow-xl)]",
              expanded ? "inset-4 w-auto" : "bottom-20 right-4 w-[min(92vw,400px)]",
              "bg-[var(--surface-card)] animate-in fade-in slide-in-from-bottom-4 duration-200",
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
        <span
          aria-hidden
          className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-[var(--content-ai-soft)]"
        >
          <Sparkles strokeWidth={1.9} className="size-4 text-[var(--content-ai)]" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="type-caption truncate font-semibold text-[var(--text-primary)]">
            {t("panelTitle")}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-label={expanded ? t("collapse") : t("expand")}
          title={expanded ? t("collapse") : t("expand")}
          className="rounded-lg p-1 text-[var(--text-muted)] outline-none transition-colors hover:bg-[var(--bg-muted)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
        >
          {expanded ? (
            <Minimize2 aria-hidden strokeWidth={1.9} className="size-4" />
          ) : (
            <Maximize2 aria-hidden strokeWidth={1.9} className="size-4" />
          )}
        </button>
        <button
          type="button"
          onClick={onClose}
          aria-label={t("close")}
          className="rounded-lg p-1 text-[var(--text-muted)] outline-none transition-colors hover:bg-[var(--bg-muted)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
        >
          <X aria-hidden strokeWidth={1.9} className="size-4" />
        </button>
      </div>

      <div className="flex h-10 shrink-0 items-center gap-2 border-b border-[var(--border-subtle)] px-3">
        {historyOpen ? (
          <>
            <button
              type="button"
              onClick={() => setHistoryOpen(false)}
              aria-label={t("backToChat")}
              title={t("backToChat")}
              className="rounded-lg p-1.5 text-[var(--text-muted)] outline-none transition-colors hover:bg-[var(--bg-muted)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
            >
              <ArrowLeft aria-hidden strokeWidth={1.9} className="size-4" />
            </button>
            <p className="type-caption min-w-0 flex-1 truncate font-semibold text-[var(--text-primary)]">
              {t("conversationHistory")}
            </p>
          </>
        ) : (
          <>
            <button
              type="button"
              onClick={() => setHistoryOpen(true)}
              aria-label={t("conversationHistory")}
              title={t("conversationHistory")}
              className="rounded-lg p-1.5 text-[var(--text-muted)] outline-none transition-colors hover:bg-[var(--bg-muted)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
            >
              <ArrowLeft aria-hidden strokeWidth={1.9} className="size-4" />
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
                className="type-caption min-w-0 flex-1 rounded-lg border border-[var(--border-default)] bg-[var(--surface-card)] px-2.5 py-1 font-semibold text-[var(--text-primary)] outline-none transition-colors focus:border-[var(--field-focus-border)]"
              />
            ) : (
              <p className="type-caption min-w-0 flex-1 truncate font-semibold text-[var(--text-primary)]">
                {currentTitle}
              </p>
            )}
            <button
              type="button"
              onClick={() => (renaming ? void saveRename() : startRename())}
              disabled={renaming && (!renameDraft.trim() || savingTitle || !sessionId)}
              aria-label={renaming ? t("saveTitle") : t("renameSession")}
              title={renaming ? t("saveTitle") : t("renameSession")}
              className="rounded-lg p-1.5 text-[var(--text-muted)] outline-none transition-colors hover:bg-[var(--bg-muted)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)] disabled:cursor-not-allowed disabled:opacity-45"
            >
              {savingTitle ? (
                <Loader2 aria-hidden className="size-4 animate-spin" />
              ) : renaming ? (
                <Check aria-hidden strokeWidth={1.9} className="size-4" />
              ) : (
                <Pencil aria-hidden strokeWidth={1.9} className="size-4" />
              )}
            </button>
            <button
              type="button"
              onClick={startNewChat}
              aria-label={t("newChat")}
              title={t("newChat")}
              className="rounded-lg p-1.5 text-[var(--text-muted)] outline-none transition-colors hover:bg-[var(--bg-muted)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
            >
              <Plus aria-hidden strokeWidth={1.9} className="size-4" />
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
            onDelete={deleteSession}
            t={t}
            searchable
            showHeading={!historyAsFullPanel}
            showNewButton
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
              embedded ? "min-h-0" : "min-h-[260px]",
            )}
          >
            {isAuthLoading ? (
              <AuthLoadingPrompt />
            ) : !isAuthed ? (
              <GuestPrompt t={t} />
            ) : messages.length === 0 && !messagesQuery.isFetching ? (
              <WelcomeScreen t={t} persona={persona} onPrompt={(prompt) => void send(prompt)} />
            ) : (
              messages.map((msg) => (
                <MessageBubble
                  key={msg.id}
                  message={msg}
                  expanded={expanded}
                  confirmBusy={confirmingAction?.id === msg.id ? confirmingAction.decision : null}
                  resolution={resolvedActions[msg.id] ?? null}
                  onConfirm={() => void resolveTool(msg, "confirm")}
                  onCancel={() => void resolveTool(msg, "cancel")}
                  editable={msg.id === editableMessageId}
                  editing={editingMessageId === msg.id}
                  editBusy={editBusy}
                  onEditStart={() => setEditingMessageId(msg.id)}
                  onEditCancel={() => setEditingMessageId(null)}
                  onEditSubmit={(text) => void submitEdit(msg, text)}
                />
              ))
            )}

            {/* Streamed answer */}
            {streamingText && <StreamingBubble text={streamingText} expanded={expanded} />}

            {/* Animated, leak-safe phase line before the streamed text appears */}
            {sending && !streamingText && <PhaseIndicator phase={phase} />}

            <div ref={bottomRef} />
          </div>

          {/* Input */}
          {isAuthed && (
            <div className="border-t border-[var(--border-default)] bg-[var(--surface-card)] px-4 pb-3 pt-3">
              {attachments.length > 0 && (
                <div className="mb-2 flex flex-wrap gap-1.5">
                  {attachments.map((a) => (
                    <span
                      key={a.localId}
                      className={cn(
                        "type-caption inline-flex max-w-[200px] items-center gap-1.5 rounded-lg border px-2 py-1 font-normal",
                        a.status === "error"
                          ? "border-[var(--content-danger)]/30 bg-[var(--content-danger-soft)] text-[var(--content-danger)]"
                          : "border-[var(--border-default)] bg-[var(--bg-subtle)] text-[var(--text-secondary)]",
                      )}
                    >
                      {a.status === "uploading" ? (
                        <Loader2 aria-hidden className="size-3 shrink-0 animate-spin" />
                      ) : (
                        <Paperclip aria-hidden strokeWidth={1.9} className="size-3 shrink-0" />
                      )}
                      <span className="truncate">{a.filename}</span>
                      <button
                        type="button"
                        onClick={() =>
                          setAttachments((prev) => prev.filter((x) => x.localId !== a.localId))
                        }
                        aria-label={t("removeAttachment")}
                        className="shrink-0 opacity-60 transition-opacity hover:opacity-100"
                      >
                        <X aria-hidden strokeWidth={1.9} className="size-3" />
                      </button>
                    </span>
                  ))}
                </div>
              )}
              <div className="flex items-end gap-2">
                <input
                  type="file"
                  multiple
                  ref={fileInputRef}
                  accept={ACCEPTED_ATTACHMENT_ACCEPT}
                  onChange={(e) => void handleFilesPicked(e.target.files)}
                  className="hidden"
                />
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={sending || attachments.length >= MAX_ATTACHMENTS}
                  aria-label={t("attachButton")}
                  className="flex size-8 shrink-0 items-center justify-center rounded-full text-[var(--text-muted)] outline-none transition-colors hover:bg-[var(--bg-muted)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)] disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <Paperclip aria-hidden strokeWidth={1.9} className="size-4" />
                </button>
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
                  className="type-small min-h-9 min-w-0 flex-1 resize-none appearance-none overflow-x-hidden overflow-y-hidden rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] px-3 py-2 leading-5 text-[var(--text-primary)] outline-none [overflow-wrap:anywhere] [word-break:break-word] transition-colors placeholder:text-[var(--text-muted)] focus:border-[var(--field-focus-border)] focus:ring-0 disabled:opacity-60"
                  style={{ maxHeight: "112px" }}
                />
                <button
                  type="button"
                  onClick={() => void send()}
                  disabled={(!input.trim() && !attachments.some((a) => a.status === "ready")) || sending}
                  aria-label={t("sendBtn")}
                  className={cn(
                    "flex size-8 shrink-0 items-center justify-center rounded-full outline-none transition-colors",
                    "focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]",
                    (input.trim() || attachments.some((a) => a.status === "ready")) && !sending
                      ? "bg-[var(--btn-primary-bg)] text-[var(--btn-primary-fg)] shadow-[var(--shadow-sm)] hover:opacity-90"
                      : "cursor-not-allowed bg-[var(--bg-muted)] text-[var(--text-muted)]",
                  )}
                >
                  {sending ? (
                    <Loader2 aria-hidden className="size-3.5 animate-spin" />
                  ) : (
                    <ArrowUp aria-hidden strokeWidth={2} className="size-3.5" />
                  )}
                </button>
              </div>
              <p className="type-caption mt-1.5 text-center font-normal text-[var(--text-muted)]">
                {t("disclaimer")}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
