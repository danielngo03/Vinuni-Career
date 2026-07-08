"use client";

import { useState } from "react";
import { useRouter } from "@/i18n/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { onboardingApi, type SeekerProfilePayload } from "@/lib/api/onboarding";
import { onboardingStepHref, workspaceHomeHref } from "@/lib/onboarding/routes";
import { OnboardingShell } from "@/components/onboarding/onboarding-shell";
import { useAuthStore } from "@/stores/auth-store";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <label className="text-sm font-medium text-[var(--text-primary)]">{label}</label>
      {children}
    </div>
  );
}

const inputCls = "w-full rounded-xl border border-[var(--border)] bg-white px-3.5 py-2.5 text-sm text-[var(--text-primary)] outline-none transition-all placeholder:text-gray-400 focus:border-[var(--ink)] focus:ring-2 focus:ring-[var(--ink)]/10";

export default function SeekerProfilePage() {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const checkOnboarding = useAuthStore((s) => s.checkOnboarding);

  // Fetch status to know seeker_type
  const { data: statusData } = useQuery({
    queryKey: ["onboarding-status"],
    queryFn: () => onboardingApi.getStatus(),
  });

  const seekerType = statusData?.seeker_type ?? "professional";

  // Professional fields
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");
  const [industry, setIndustry] = useState("");
  const [yearsExp, setYearsExp] = useState("");

  // Fresh graduate fields
  const [university, setUniversity] = useState("");
  const [major, setMajor] = useState("");
  const [gradYear, setGradYear] = useState("");

  const mutation = useMutation({
    mutationFn: (data: SeekerProfilePayload) => onboardingApi.saveSeekerProfile(data),
    onSuccess: async () => {
      await checkOnboarding();
      router.replace(workspaceHomeHref(user?.persona));
    },
  });

  const hasProfileData =
    Boolean(title.trim()) ||
    Boolean(company.trim()) ||
    Boolean(industry.trim()) ||
    Boolean(yearsExp.trim()) ||
    Boolean(university.trim()) ||
    Boolean(major.trim()) ||
    Boolean(gradYear.trim());

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const payload: SeekerProfilePayload =
      seekerType === "fresh_graduate"
        ? { university: university || undefined, major: major || undefined, graduation_year: gradYear ? Number(gradYear) : undefined }
        : { title: title || undefined, company: company || undefined, industry: industry || undefined, years_experience: yearsExp ? Number(yearsExp) : undefined };
    mutation.mutate(payload);
  };

  return (
    <OnboardingShell
      title={seekerType === "fresh_graduate" ? "Thông tin tốt nghiệp" : "Thông tin nghề nghiệp"}
      subtitle="Hoàn thiện hồ sơ để nhận đề xuất việc làm phù hợp nhất."
      step={3}
      totalSteps={3}
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {seekerType === "professional" && (
          <>
            <Field label="Chức vụ hiện tại">
              <input className={inputCls} placeholder="Ví dụ: Product Manager" value={title} onChange={e => setTitle(e.target.value)} />
            </Field>
            <Field label="Công ty">
              <input className={inputCls} placeholder="Tên công ty đang làm" value={company} onChange={e => setCompany(e.target.value)} />
            </Field>
            <Field label="Ngành nghề">
              <input className={inputCls} placeholder="Ví dụ: Công nghệ thông tin" value={industry} onChange={e => setIndustry(e.target.value)} />
            </Field>
            <Field label="Số năm kinh nghiệm">
              <input className={inputCls} type="number" min="0" max="60" placeholder="0" value={yearsExp} onChange={e => setYearsExp(e.target.value)} />
            </Field>
          </>
        )}
        {seekerType === "fresh_graduate" && (
          <>
            <Field label="Trường đại học">
              <input className={inputCls} placeholder="Ví dụ: VinUniversity" value={university} onChange={e => setUniversity(e.target.value)} />
            </Field>
            <Field label="Chuyên ngành">
              <input className={inputCls} placeholder="Ví dụ: Kỹ thuật máy tính" value={major} onChange={e => setMajor(e.target.value)} />
            </Field>
            <Field label="Năm tốt nghiệp">
              <input className={inputCls} type="number" min="1980" max="2030" value={gradYear} onChange={e => setGradYear(e.target.value)} />
            </Field>
          </>
        )}

        <p className="text-xs text-[var(--text-tertiary)]">
          Bạn có thể bổ sung thêm thông tin này sau trong trang hồ sơ.
        </p>

        <div className="flex gap-3 pt-2">
          <button
            type="button"
            onClick={() => router.push(onboardingStepHref("seeker_type"))}
            className="h-11 flex-1 rounded-xl border border-[var(--border)] text-sm font-medium transition-colors hover:bg-gray-50"
          >
            ← Quay lại
          </button>
          <button
            type="submit"
            disabled={mutation.isPending}
            className="h-11 flex-[2] rounded-xl bg-[var(--ink)] text-sm font-semibold text-white transition-colors hover:bg-gray-800 disabled:opacity-40"
          >
            {mutation.isPending ? "Đang lưu..." : hasProfileData ? "Lưu và vào hệ thống →" : "Bỏ qua và vào hệ thống →"}
          </button>
        </div>
      </form>
    </OnboardingShell>
  );
}
