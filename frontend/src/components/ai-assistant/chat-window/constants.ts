import type { ChatMessage } from "@/lib/api";
import { Briefcase, ReadCvLogo, CalendarCheck, PaperPlaneTilt, ChartBar, CurrencyDollar } from "@phosphor-icons/react";

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
};

export const STATUS_LABELS: Record<string, string> = {
  received: "Đã nhận yêu cầu của bạn",
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
