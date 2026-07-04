"use client";

import { useState } from "react";
import { useRouter } from "@/i18n/navigation";
import { useMutation } from "@tanstack/react-query";
import { onboardingApi } from "@/lib/api/onboarding";
import { onboardingStepHref } from "@/lib/onboarding/routes";
import { OnboardingShell } from "@/components/onboarding/onboarding-shell";
import { useAuthStore } from "@/stores/auth-store";

const inputCls = "w-full rounded-xl border border-[var(--border)] bg-white px-3.5 py-2.5 text-sm outline-none transition-all placeholder:text-gray-400 focus:border-[var(--ink)] focus:ring-2 focus:ring-[var(--ink)]/10";
const selectCls = inputCls + " appearance-none cursor-pointer";

const COMPANY_SIZES = [
  { value: "1-10", label: "1–10 nhân viên" },
  { value: "11-50", label: "11–50 nhân viên" },
  { value: "51-200", label: "51–200 nhân viên" },
  { value: "201-500", label: "201–500 nhân viên" },
  { value: "501-1000", label: "501–1.000 nhân viên" },
  { value: "1000+", label: "Trên 1.000 nhân viên" },
];

const INDUSTRIES = [
  "Công nghệ thông tin", "Tài chính – Ngân hàng", "Giáo dục – Đào tạo",
  "Y tế – Chăm sóc sức khỏe", "Bán lẻ – Thương mại điện tử", "Sản xuất",
  "Truyền thông – Marketing", "Xây dựng – Bất động sản", "Logistics – Vận tải",
  "Năng lượng", "Khác",
];

export default function EmployerInfoPage() {
  const router = useRouter();
  const checkOnboarding = useAuthStore((s) => s.checkOnboarding);
  const [companyName, setCompanyName] = useState("");
  const [industry, setIndustry] = useState("");
  const [companySize, setCompanySize] = useState("");
  const [address, setAddress] = useState("");
  const [registrantRole, setRegistrantRole] = useState("");

  const mutation = useMutation({
    mutationFn: () => onboardingApi.saveEmployerInfo({ company_name: companyName, industry: industry || undefined, company_size: companySize || undefined, address: address || undefined, registrant_role: registrantRole || undefined }),
    onSuccess: async (data) => {
      await checkOnboarding();
      router.push(onboardingStepHref(data.current_step));
    },
  });

  return (
    <OnboardingShell
      title="Thông tin doanh nghiệp"
      subtitle="Điền thông tin công ty của bạn để tạo hồ sơ nhà tuyển dụng."
      step={2}
      totalSteps={3}
    >
      <form onSubmit={e => { e.preventDefault(); mutation.mutate(); }} className="space-y-4">
        <div className="space-y-1.5">
          <label className="text-sm font-medium">Tên doanh nghiệp <span className="text-red-500">*</span></label>
          <input required className={inputCls} placeholder="Tên công ty đầy đủ" value={companyName} onChange={e => setCompanyName(e.target.value)} />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <label className="text-sm font-medium">Ngành nghề</label>
            <select className={selectCls} value={industry} onChange={e => setIndustry(e.target.value)}>
              <option value="">Chọn ngành</option>
              {INDUSTRIES.map(i => <option key={i} value={i}>{i}</option>)}
            </select>
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium">Quy mô</label>
            <select className={selectCls} value={companySize} onChange={e => setCompanySize(e.target.value)}>
              <option value="">Chọn quy mô</option>
              {COMPANY_SIZES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
          </div>
        </div>

        <div className="space-y-1.5">
          <label className="text-sm font-medium">Địa chỉ văn phòng</label>
          <input className={inputCls} placeholder="Số nhà, đường, quận, tỉnh/thành phố" value={address} onChange={e => setAddress(e.target.value)} />
        </div>

        <div className="space-y-1.5">
          <label className="text-sm font-medium">Vị trí của bạn tại công ty</label>
          <input className={inputCls} placeholder="Ví dụ: CEO, HR Manager, Giám đốc nhân sự" value={registrantRole} onChange={e => setRegistrantRole(e.target.value)} />
        </div>

        {mutation.isError && (
          <p className="text-sm text-red-600">Đã xảy ra lỗi. Vui lòng thử lại.</p>
        )}

        <div className="flex gap-3 pt-2">
          <button type="button" onClick={() => router.push(onboardingStepHref("role_select"))}
            className="h-11 flex-1 rounded-xl border border-[var(--border)] text-sm font-medium hover:bg-gray-50">
            ← Quay lại
          </button>
          <button type="submit" disabled={mutation.isPending || !companyName}
            className="h-11 flex-[2] rounded-xl bg-[var(--ink)] text-sm font-semibold text-white hover:bg-gray-800 disabled:opacity-40">
            {mutation.isPending ? "Đang lưu..." : "Tiếp tục →"}
          </button>
        </div>
      </form>
    </OnboardingShell>
  );
}
