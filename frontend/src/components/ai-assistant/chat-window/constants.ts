import type { ChatMessage } from "@/lib/api";
import { Briefcase, ReadCvLogo, CalendarCheck, PaperPlaneTilt, ChartBar, CurrencyDollar } from "@phosphor-icons/react";

export const MAX_INPUT_LENGTH = 1000;

/* ----------------------------- Attachments ------------------------------ */

/** Max number of files a single message may carry. */
export const MAX_ATTACHMENTS = 3;

/** Client-side courtesy cap for instant feedback. The backend limit is
 * authoritative — anything it rejects surfaces the backend's user-safe message. */
export const MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024;

/** Allowed upload extensions (mirrors the backend attachment contract:
 * images + PDF/CSV/DOCX/TXT). */
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
// tool (SendMessageRequest is text-only, so this is the only channel). The id
// is the staffer's OWN attachment id — not sensitive. This marker is internal
// plumbing, NOT user-facing copy: the message-bubble renderer strips these
// lines back out and shows a paperclip chip instead, so the raw ref never
// appears in the visible bubble (hence it is intentionally locale-neutral and
// exempt from the i18n gate).
const ATTACHMENT_REF_RE =
  /\n*\[Attachment — use analyze_attachment:\s*(.+?)\s*\(id:\s*[^)]+\)\]/g;

/** Build the ref line for one ready attachment. */
export function buildAttachmentRef(filename: string, id: string): string {
  return `\n\n[Attachment — use analyze_attachment: ${filename} (id: ${id})]`;
}

/**
 * Split a user message into its clean visible text and the attachment
 * filenames referenced by any appended ref lines. Only user content is passed
 * in (assistant text never embeds refs).
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
  const text = content.replace(re, "").trim();
  return { text, filenames };
}

export type StreamEvent =
  | { type: "status"; code: string }
  | { type: "token"; text: string }
  | { type: "tool_call"; name: string }
  | { type: "tool_result"; name: string; ok: boolean }
  | { type: "done"; message: ChatMessage }
  | { type: "error"; code: string };

/** Tool name → human-readable label shown in the UI during tool dispatch. */
export const TOOL_LABELS: Record<string, string> = {
  search_jobs: "Đang tìm kiếm việc làm…",
  get_my_applications: "Đang tải đơn ứng tuyển…",
  get_my_cvs: "Đang tải thư viện CV…",
  get_upcoming_events: "Đang tìm sự kiện…",
  get_saved_jobs: "Đang tải việc làm đã lưu…",
  get_profile_status: "Đang kiểm tra hồ sơ…",
  get_job_alerts: "Đang tải thông báo việc làm…",
  get_upcoming_interviews: "Đang tải lịch phỏng vấn…",
  search_companies: "Đang tìm kiếm công ty…",
  get_company_reviews: "Đang tải đánh giá công ty…",
  get_job_detail: "Đang xem chi tiết việc làm…",
  get_my_registered_events: "Đang tải sự kiện đã đăng ký…",
  get_company_detail: "Đang tải thông tin công ty…",
  search_events: "Đang tìm kiếm sự kiện…",
  get_partner_jobs: "Đang tải danh sách việc làm…",
  get_partner_pipeline_summary: "Đang tải tổng quan pipeline…",
  get_skill_gap: "Đang phân tích kỹ năng…",
  recommend_jobs: "Đang tìm gợi ý phù hợp…",
  get_career_advice: "Đang tra cứu định hướng nghề nghiệp…",
  get_salary_benchmark: "Đang tra cứu mức lương…",
  save_job: "Đang chuẩn bị lưu việc làm…",
  apply_job: "Đang chuẩn bị nộp đơn…",
  knowledge_base_query: "Đang tra cứu hướng dẫn hệ thống…",
  start_interview_sim: "Đang chuẩn bị luyện phỏng vấn…",
};

export const STATUS_LABELS: Record<string, string> = {
  received: "Đã nhận yêu cầu của bạn",
  confirming_action: "Cần bạn xác nhận trước khi thực hiện",
  thinking: "Đang phân tích ý định",
  retrieving_context: "Đang lấy ngữ cảnh hồ sơ",
  using_tool: "Đang tra cứu dữ liệu hệ thống",
  synthesizing: "Đang tổng hợp kết quả",
  responding: "Đang soạn câu trả lời",
};

export const SUGGESTION_ITEMS = [
  { icon: Briefcase, key: "suggestJobs", href: "/jobs" },
  { icon: ReadCvLogo, key: "suggestCv", href: "/student/cv" },
  { icon: CalendarCheck, key: "suggestEvents", href: "/events" },
  { icon: PaperPlaneTilt, key: "suggestApps", href: "/student/applications" },
  { icon: ChartBar, key: "suggestSkillGap", href: "/student/cv" },
  { icon: CurrencyDollar, key: "suggestSalary", href: "/jobs" },
] as const;

export const QUICK_PROMPTS = [
  "Tìm việc làm IT phù hợp với tôi",
  "Phân tích gap kỹ năng của tôi",
  "Mức lương Data Scientist tại Hà Nội?",
  "Sự kiện tuyển dụng sắp tới",
] as const;
