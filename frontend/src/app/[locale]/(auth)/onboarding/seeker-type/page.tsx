"use client";

import { useState } from "react";
import { useRouter } from "@/i18n/navigation";
import { useMutation } from "@tanstack/react-query";
import { GraduationCap, Briefcase, Star } from "@phosphor-icons/react";
import { onboardingApi, type SeekerType } from "@/lib/api/onboarding";
import { onboardingStepHref } from "@/lib/onboarding/routes";
import { OnboardingShell } from "@/components/onboarding/onboarding-shell";
import { useAuthStore } from "@/stores/auth-store";

interface TypeCard {
  type: SeekerType;
  icon: React.ReactNode;
  title: string;
  description: string;
}

const TYPES: TypeCard[] = [
  {
    type: "student",
    icon: <GraduationCap weight="duotone" className="size-6" />,
    title: "Sinh viên (đang học)",
    description: "Đang theo học tại một trường đại học hoặc cao đẳng.",
  },
  {
    type: "professional",
    icon: <Briefcase weight="duotone" className="size-6" />,
    title: "Đang đi làm",
    description: "Đang có việc làm và tìm kiếm cơ hội mới.",
  },
  {
    type: "fresh_graduate",
    icon: <Star weight="duotone" className="size-6" />,
    title: "Mới tốt nghiệp",
    description: "Vừa tốt nghiệp và bắt đầu hành trình sự nghiệp.",
  },
];

export default function SeekerTypePage() {
  const router = useRouter();
  const checkOnboarding = useAuthStore((s) => s.checkOnboarding);
  const [selected, setSelected] = useState<SeekerType | null>(null);

  const mutation = useMutation({
    mutationFn: (seeker_type: SeekerType) => onboardingApi.setSeekerType(seeker_type),
    onSuccess: async (data) => {
      await checkOnboarding();
      router.push(onboardingStepHref(data.current_step));
    },
  });

  return (
    <OnboardingShell
      title="Bạn đang ở giai đoạn nào?"
      subtitle="Giúp chúng tôi hiểu rõ hơn về bạn để đề xuất cơ hội phù hợp nhất."
      step={2}
      totalSteps={3}
    >
      <div className="space-y-2.5">
        {TYPES.map((card) => (
          <button
            key={card.type}
            type="button"
            onClick={() => setSelected(card.type)}
            className={`w-full rounded-xl border-2 p-3.5 text-left transition-all ${
              selected === card.type
                ? "border-[var(--ink)] bg-gray-50"
                : "border-[var(--border)] bg-white hover:border-gray-300"
            }`}
          >
            <div className="flex items-center gap-3">
              <span
                className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${
                  selected === card.type ? "bg-[var(--ink)] text-white" : "bg-gray-100 text-gray-500"
                }`}
              >
                {card.icon}
              </span>
              <div>
                <p className="text-sm font-semibold text-[var(--text-primary)]">{card.title}</p>
                <p className="text-xs text-[var(--text-secondary)]">{card.description}</p>
              </div>
              {selected === card.type && (
                <span className="ml-auto flex h-5 w-5 items-center justify-center rounded-full bg-[var(--ink)]">
                  <span className="h-2 w-2 rounded-full bg-white" />
                </span>
              )}
            </div>
          </button>
        ))}
      </div>

      <div className="mt-6 flex gap-3">
        <button
          type="button"
          onClick={() => router.push(onboardingStepHref("role_select"))}
          className="h-11 flex-1 rounded-xl border border-[var(--border)] text-sm font-medium text-[var(--text-primary)] transition-colors hover:bg-gray-50"
        >
          ← Quay lại
        </button>
        <button
          type="button"
          disabled={!selected || mutation.isPending}
          onClick={() => selected && mutation.mutate(selected)}
          className="h-11 flex-[2] rounded-xl bg-[var(--ink)] text-sm font-semibold text-white transition-colors hover:bg-gray-800 disabled:opacity-40"
        >
          {mutation.isPending ? "Đang xử lý..." : "Tiếp tục →"}
        </button>
      </div>
    </OnboardingShell>
  );
}
