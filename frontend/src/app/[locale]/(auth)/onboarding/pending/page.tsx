"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "@/i18n/navigation";
import { useEffect } from "react";
import { onboardingApi } from "@/lib/api/onboarding";
import { onboardingStepHref, workspaceHomeHref } from "@/lib/onboarding/routes";
import { OnboardingShell } from "@/components/onboarding/onboarding-shell";
import { useAuthStore } from "@/stores/auth-store";
import { Clock, CheckCircle, XCircle, Envelope } from "@phosphor-icons/react";

type RequestStatus = "pending_review" | "approved" | "rejected";

const STATUS_CONFIG: Record<RequestStatus, {
  icon: React.ReactNode;
  title: string;
  desc: string;
  accent: string;
}> = {
  pending_review: {
    icon: <Clock weight="duotone" className="size-12 text-amber-500" />,
    title: "Đang chờ duyệt",
    desc: "Đội ngũ VinUni đang xét duyệt hồ sơ doanh nghiệp của bạn. Thời gian xử lý thường là 1–3 ngày làm việc. Chúng tôi sẽ gửi email thông báo kết quả.",
    accent: "bg-amber-50 text-amber-700",
  },
  approved: {
    icon: <CheckCircle weight="fill" className="size-12 text-green-500" />,
    title: "Hồ sơ được chấp thuận!",
    desc: "Chúc mừng! Tài khoản nhà tuyển dụng của bạn đã được kích hoạt. Bạn có thể bắt đầu đăng tin tuyển dụng và quản lý ứng viên ngay bây giờ.",
    accent: "bg-green-50 text-green-700",
  },
  rejected: {
    icon: <XCircle weight="fill" className="size-12 text-red-500" />,
    title: "Hồ sơ không được chấp thuận",
    desc: "Hồ sơ của bạn chưa đáp ứng yêu cầu. Vui lòng kiểm tra email để biết lý do và hướng dẫn nộp lại.",
    accent: "bg-red-50 text-red-700",
  },
};

export default function PendingPage() {
  const router = useRouter();
  const checkOnboarding = useAuthStore((s) => s.checkOnboarding);

  const { data, refetch } = useQuery({
    queryKey: ["employer-doc-status"],
    queryFn: () => onboardingApi.getEmployerDocStatus(),
    refetchInterval: 15_000, // Check every 15s while on this page
  });

  const requestStatus: RequestStatus = data?.request_status ?? "pending_review";
  const config = STATUS_CONFIG[requestStatus];

  // Auto-redirect approved employers to dashboard
  useEffect(() => {
    if (requestStatus === "approved") {
      const timer = window.setTimeout(async () => {
        await checkOnboarding();
        router.push(workspaceHomeHref("partner"));
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [requestStatus, checkOnboarding, router]);

  return (
    <OnboardingShell
      title="Trạng thái hồ sơ"
      subtitle="Cảm ơn bạn đã đăng ký trở thành nhà tuyển dụng trên VinUni Career Platform."
      step={3}
      totalSteps={3}
    >
      <div className="flex flex-col items-center gap-6 py-4">
        {config.icon}

        <div className="space-y-1 text-center">
          <h2 className="text-lg font-semibold">{config.title}</h2>
          <p className="max-w-xs text-sm text-[var(--text-secondary)] leading-relaxed">{config.desc}</p>
        </div>

        {/* Status badge */}
        <span className={`rounded-full px-3 py-1 text-xs font-medium ${config.accent}`}>
          {requestStatus === "pending_review" && "Đang xét duyệt"}
          {requestStatus === "approved" && "Đã chấp thuận"}
          {requestStatus === "rejected" && "Không được chấp thuận"}
        </span>

        {/* What to expect */}
        {requestStatus === "pending_review" && (
          <div className="w-full rounded-xl border border-[var(--border)] divide-y divide-[var(--border)]">
            {[
              { step: "1", text: "Kiểm tra tài liệu bởi AI" },
              { step: "2", text: "Xét duyệt bởi đội ngũ VinUni" },
              { step: "3", text: "Gửi email thông báo kết quả" },
            ].map(item => (
              <div key={item.step} className="flex items-center gap-3 px-4 py-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gray-100 text-xs font-semibold text-gray-600">
                  {item.step}
                </span>
                <span className="text-sm">{item.text}</span>
              </div>
            ))}
          </div>
        )}

        {/* Email reminder */}
        <div className="flex items-start gap-2.5 rounded-xl bg-gray-50 px-4 py-3 text-sm text-[var(--text-secondary)]">
          <Envelope weight="duotone" className="mt-0.5 size-4 shrink-0 text-[var(--ink)]" />
          <span>Theo dõi email để nhận thông báo kết quả xét duyệt.</span>
        </div>

        {/* Actions */}
        <div className="w-full space-y-2">
          {requestStatus === "approved" && (
            <button onClick={async () => { await checkOnboarding(); router.push(workspaceHomeHref("partner")); }}
              className="h-11 w-full rounded-xl bg-[var(--ink)] text-sm font-semibold text-white hover:bg-gray-800">
              Vào trang quản lý →
            </button>
          )}
          {requestStatus === "rejected" && (
            <button onClick={() => router.push(onboardingStepHref("employer_docs"))}
              className="h-11 w-full rounded-xl bg-[var(--ink)] text-sm font-semibold text-white hover:bg-gray-800">
              Nộp lại hồ sơ →
            </button>
          )}
          {requestStatus === "pending_review" && (
            <button onClick={() => refetch()}
              className="h-11 w-full rounded-xl border border-[var(--border)] text-sm font-medium hover:bg-gray-50">
              Kiểm tra lại trạng thái
            </button>
          )}
        </div>
      </div>
    </OnboardingShell>
  );
}
