import type { ChatMessage } from "@/lib/api";
import {
  Briefcase,
  ReadCvLogo,
  CalendarCheck,
  PaperPlaneTilt,
  ChartBar,
  CurrencyDollar,
  UsersThree,
} from "@phosphor-icons/react";

export const MAX_INPUT_LENGTH = 1000;

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
  // Partner (recruiter) tools
  search_partner_candidates: "Đang tìm ứng viên…",
  get_candidate_detail: "Đang tải hồ sơ ứng viên…",
  draft_job_description: "Đang soạn mô tả công việc…",
  rewrite_job_description: "Đang biên tập lại mô tả công việc…",
  check_jd_bias: "Đang kiểm tra ngôn ngữ thiên kiến…",
  suggest_scorecard: "Đang gợi ý phiếu đánh giá…",
  generate_screening_brief: "Đang tóm tắt sàng lọc ứng viên…",
  get_upcoming_partner_events: "Đang tải sự kiện của công ty…",
  move_candidate_stage: "Đang chuẩn bị chuyển vòng ứng viên…",
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

/** Persona of the current chat user — drives greeting, quick prompts, and links. */
export type ChatPersona = "student" | "partner" | "university";

export type SuggestionItem = {
  icon: typeof Briefcase;
  key: string;
  href: string;
};

const STUDENT_SUGGESTIONS: readonly SuggestionItem[] = [
  { icon: Briefcase, key: "suggestJobs", href: "/jobs" },
  { icon: ReadCvLogo, key: "suggestCv", href: "/student/cv" },
  { icon: CalendarCheck, key: "suggestEvents", href: "/events" },
  { icon: PaperPlaneTilt, key: "suggestApps", href: "/student/applications" },
  { icon: ChartBar, key: "suggestSkillGap", href: "/student/cv" },
  { icon: CurrencyDollar, key: "suggestSalary", href: "/jobs" },
];

// Partner (recruiter) shortcuts point at partner operating surfaces — never the
// student /jobs, /student/cv, /student/applications routes.
const PARTNER_SUGGESTIONS: readonly SuggestionItem[] = [
  { icon: Briefcase, key: "suggestPartnerJobs", href: "/partner/jobs" },
  { icon: UsersThree, key: "suggestPartnerPipeline", href: "/partner/pipeline" },
  { icon: CalendarCheck, key: "suggestPartnerEvents", href: "/partner/events" },
  { icon: ChartBar, key: "suggestPartnerAnalytics", href: "/partner/analytics" },
];

export const SUGGESTION_ITEMS_BY_PERSONA: Record<ChatPersona, readonly SuggestionItem[]> = {
  student: STUDENT_SUGGESTIONS,
  partner: PARTNER_SUGGESTIONS,
  university: STUDENT_SUGGESTIONS,
};

const STUDENT_QUICK_PROMPTS: readonly string[] = [
  "Tìm việc làm IT phù hợp với tôi",
  "Phân tích gap kỹ năng của tôi",
  "Mức lương Data Scientist tại Hà Nội?",
  "Sự kiện tuyển dụng sắp tới",
];

const PARTNER_QUICK_PROMPTS: readonly string[] = [
  "Liệt kê tin tuyển dụng đang mở của tôi",
  "Tổng quan pipeline ứng viên của tôi",
  "Soạn mô tả công việc cho một vị trí mới",
  "Sự kiện tuyển dụng sắp tới của công ty",
];

export const QUICK_PROMPTS_BY_PERSONA: Record<ChatPersona, readonly string[]> = {
  student: STUDENT_QUICK_PROMPTS,
  partner: PARTNER_QUICK_PROMPTS,
  university: STUDENT_QUICK_PROMPTS,
};

// Back-compat aliases (default = student) for any other importer.
export const SUGGESTION_ITEMS = STUDENT_SUGGESTIONS;
export const QUICK_PROMPTS = STUDENT_QUICK_PROMPTS;
