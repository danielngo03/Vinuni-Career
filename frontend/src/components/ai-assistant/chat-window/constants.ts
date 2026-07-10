import type { ChatMessage } from "@/lib/api";
import {
  Briefcase,
  FileText,
  CalendarCheck,
  Send,
  BarChart3,
  CircleDollarSign,
  Users,
  type LucideIcon,
} from "lucide-react";

export const MAX_INPUT_LENGTH = 1000;

/* ----------------------------- Attachments ------------------------------ */

/** Max number of files a single message may carry. */
export const MAX_ATTACHMENTS = 3;

/** Client-side courtesy cap for instant feedback. The backend limit is
 * authoritative — anything it rejects surfaces the backend's user-safe message. */
export const MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024;

/** Allowed upload extensions (mirrors the backend attachment contract). */
export const ACCEPTED_ATTACHMENT_EXT = [
  "pdf",
  "png",
  "jpg",
  "jpeg",
  "docx",
  "txt",
  "csv",
] as const;

/** `accept` attribute for the hidden file input. */
export const ACCEPTED_ATTACHMENT_ACCEPT =
  ".pdf,.png,.jpg,.jpeg,.docx,.txt,.csv," +
  "application/pdf,image/png,image/jpeg," +
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document," +
  "text/plain,text/csv";

/** True when the file's extension is one the backend can accept. */
export function isAcceptedAttachment(filename: string): boolean {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  return (ACCEPTED_ATTACHMENT_EXT as readonly string[]).includes(ext);
}

// Machine-readable reference the composer appends to the outgoing message text
// so the assistant sees the attachment id and calls its `analyze_attachment`
// tool. `SendMessageRequest` is text-only, so this is the only channel. The id
// is the user's own attachment id — not sensitive. The message-bubble renderer
// strips these lines back out and shows a paperclip chip instead, so the raw
// ref never appears in the visible bubble.
const ATTACHMENT_REF_RE =
  /\n*\[Tệp đính kèm — dùng analyze_attachment:\s*(.+?)\s*\(id:\s*[^)]+\)\]/g;

/** Build the ref line for one ready attachment. */
export function buildAttachmentRef(filename: string, id: string): string {
  return `\n\n[Tệp đính kèm — dùng analyze_attachment: ${filename} (id: ${id})]`;
}

// Machine-readable CV-selection marker appended when a student clicks a chip in
// a `cv_picker` card. The backend pre-processor consumes `[[cv:<id>]]` to re-run
// the pending CV tool with the chosen CV (design §3); the marker is stripped
// before the user bubble is displayed, mirroring the attachment-ref pattern.
const CV_MARKER_RE = /\s*\[\[cv:[^\]]+\]\]/g;

/** Build a user-turn text that carries a chosen CV id for the picker resolution. */
export function buildCvSelectionMessage(displayText: string, cvId: string): string {
  return `${displayText.trim()} [[cv:${cvId}]]`;
}

/**
 * Split a user message into its clean visible text and the attachment
 * filenames referenced by any appended ref lines. Also strips any
 * machine-readable `[[cv:...]]` selection marker so it never shows in a bubble.
 */
export function extractAttachmentRefs(content: string): {
  text: string;
  filenames: string[];
} {
  const re = new RegExp(ATTACHMENT_REF_RE.source, "g");
  const filenames: string[] = [];
  for (const match of content.matchAll(re)) {
    const name = match[1]?.trim();
    if (name) filenames.push(name);
  }
  const text = content
    .replace(re, "")
    .replace(CV_MARKER_RE, "")
    .trim();
  return { text, filenames };
}

export type StreamEvent =
  | { type: "status"; code: string }
  | { type: "token"; text: string }
  | { type: "tool_call"; name: string }
  | { type: "tool_result"; name: string; ok: boolean }
  | { type: "done"; message: ChatMessage }
  | { type: "error"; code: string };

// Tool-dispatch and status labels live in the `aiAssistant` i18n namespace
// (`tools.{tool_name}`, `toolNames.{tool_name}`, `status.{code}`) and are
// resolved with `t.has(...)` fallbacks — see message-bubble/ai-chat-window.

/** Persona of the current chat user — drives greeting, quick prompts, and links. */
export type ChatPersona = "student" | "partner" | "university";

export type SuggestionItem = {
  icon: LucideIcon;
  key: string;
  href: string;
};

const STUDENT_SUGGESTIONS: readonly SuggestionItem[] = [
  { icon: Briefcase, key: "suggestJobs", href: "/jobs" },
  { icon: FileText, key: "suggestCv", href: "/student/cv" },
  { icon: CalendarCheck, key: "suggestEvents", href: "/events" },
  { icon: Send, key: "suggestApps", href: "/student/applications" },
  { icon: BarChart3, key: "suggestSkillGap", href: "/student/cv" },
  { icon: CircleDollarSign, key: "suggestSalary", href: "/jobs" },
];

// Partner (recruiter) shortcuts point at partner operating surfaces — never the
// student /jobs, /student/cv, /student/applications routes.
const PARTNER_SUGGESTIONS: readonly SuggestionItem[] = [
  { icon: Briefcase, key: "suggestPartnerJobs", href: "/partner/jobs" },
  { icon: Users, key: "suggestPartnerPipeline", href: "/partner/pipeline" },
  { icon: CalendarCheck, key: "suggestPartnerEvents", href: "/partner/events" },
  { icon: BarChart3, key: "suggestPartnerAnalytics", href: "/partner/analytics" },
];

export const SUGGESTION_ITEMS_BY_PERSONA: Record<ChatPersona, readonly SuggestionItem[]> = {
  student: STUDENT_SUGGESTIONS,
  partner: PARTNER_SUGGESTIONS,
  university: STUDENT_SUGGESTIONS,
};

// Quick prompts are i18n keys under the `aiAssistant` namespace; the welcome
// screen resolves them with `t(key)` and sends the localized prompt text.
const STUDENT_QUICK_PROMPT_KEYS: readonly string[] = [
  "quickPrompts.studentCvMatch",
  "quickPrompts.studentBestCv",
  "quickPrompts.studentSkillGap",
  "quickPrompts.studentSalary",
  "quickPrompts.studentEvents",
];

const PARTNER_QUICK_PROMPT_KEYS: readonly string[] = [
  "quickPrompts.partnerOpenJobs",
  "quickPrompts.partnerFunnel",
  "quickPrompts.partnerPipeline",
  "quickPrompts.partnerDraftJd",
  "quickPrompts.partnerEvents",
];

export const QUICK_PROMPT_KEYS_BY_PERSONA: Record<ChatPersona, readonly string[]> = {
  student: STUDENT_QUICK_PROMPT_KEYS,
  partner: PARTNER_QUICK_PROMPT_KEYS,
  university: STUDENT_QUICK_PROMPT_KEYS,
};
