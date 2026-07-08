"use client";

import { useState } from "react";
import { useRouter } from "@/i18n/navigation";
import { useMutation } from "@tanstack/react-query";
import { Briefcase, MagnifyingGlass } from "@phosphor-icons/react";
import { onboardingApi, type OnboardingRole } from "@/lib/api/onboarding";
import { onboardingStepHref } from "@/lib/onboarding/routes";
import { OnboardingShell } from "@/components/onboarding/onboarding-shell";
import { useAuthStore } from "@/stores/auth-store";

interface RoleCard {
  role: OnboardingRole;
  icon: React.ReactNode;
  title: string;
  description: string;
}

const ROLES: RoleCard[] = [
  {
    role: "job_seeker",
    icon: <MagnifyingGlass weight="duotone" className="size-7" />,
    title: "Người tìm việc",
    description: "Sinh viên, người đang đi làm, hoặc mới tốt nghiệp tìm kiếm cơ hội nghề nghiệp.",
  },
  {
    role: "employer",
    icon: <Briefcase weight="duotone" className="size-7" />,
    title: "Nhà tuyển dụng",
    description: "Doanh nghiệp muốn đăng tin tuyển dụng và tiếp cận ứng viên chất lượng từ VinUni.",
  },
];

export default function RoleSelectPage() {
  const router = useRouter();
  const checkOnboarding = useAuthStore((s) => s.checkOnboarding);
  const [selected, setSelected] = useState<OnboardingRole | null>(null);

  const mutation = useMutation({
    mutationFn: (role: OnboardingRole) => onboardingApi.setRole(role),
    onSuccess: async (data) => {
      await checkOnboarding();
      router.push(onboardingStepHref(data.current_step));
    },
  });

  return (
    <OnboardingShell
      title="Bạn tham gia với tư cách nào?"
      subtitle="Chọn vai trò phù hợp để chúng tôi cá nhân hóa trải nghiệm của bạn."
      step={1}
      totalSteps={3}
    >
      <div className="space-y-3">
        {ROLES.map((card) => (
          <button
            key={card.role}
            type="button"
            onClick={() => setSelected(card.role)}
            className={`w-full rounded-xl border-2 p-4 text-left transition-all ${
              selected === card.role
                ? "border-[var(--ink)] bg-gray-50"
                : "border-[var(--border)] bg-white hover:border-gray-300"
            }`}
          >
            <div className="flex items-start gap-3">
              <span
                className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${
                  selected === card.role ? "bg-[var(--ink)] text-white" : "bg-gray-100 text-[var(--text-secondary)]"
                }`}
              >
                {card.icon}
              </span>
              <div>
                <p className="font-semibold text-[var(--text-primary)]">{card.title}</p>
                <p className="mt-0.5 text-sm text-[var(--text-secondary)]">{card.description}</p>
              </div>
            </div>
          </button>
        ))}
      </div>

      <button
        type="button"
        disabled={!selected || mutation.isPending}
        onClick={() => selected && mutation.mutate(selected)}
        className="mt-6 inline-flex h-11 w-full items-center justify-center rounded-xl bg-[var(--ink)] text-sm font-semibold text-white transition-colors hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {mutation.isPending ? "Đang xử lý..." : "Tiếp tục →"}
      </button>

      {mutation.isError && (
        <p className="mt-2 text-center text-sm text-red-600">
          Đã xảy ra lỗi. Vui lòng thử lại.
        </p>
      )}
    </OnboardingShell>
  );
}
