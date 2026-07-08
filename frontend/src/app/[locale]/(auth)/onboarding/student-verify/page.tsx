"use client";

import { useState, useRef, useEffect } from "react";
import { useRouter } from "@/i18n/navigation";
import { useMutation } from "@tanstack/react-query";
import { onboardingApi } from "@/lib/api/onboarding";
import { onboardingStepHref, workspaceHomeHref } from "@/lib/onboarding/routes";
import { OnboardingShell } from "@/components/onboarding/onboarding-shell";
import { useAuthStore } from "@/stores/auth-store";
import { CheckCircle, UploadSimple, CircleNotch } from "@phosphor-icons/react";

const inputCls = "w-full rounded-xl border border-[var(--border)] bg-white px-3.5 py-2.5 text-sm outline-none transition-all placeholder:text-gray-400 focus:border-[var(--ink)] focus:ring-2 focus:ring-[var(--ink)]/10";

function OtpInput({ value, onChange, disabled }: { value: string; onChange: (v: string) => void; disabled?: boolean }) {
  const inputs = useRef<Array<HTMLInputElement | null>>([]);
  const handleChange = (i: number, ch: string) => {
    const digit = ch.replace(/\D/g, "").slice(-1);
    const arr = value.split("").slice(0, 6);
    arr[i] = digit;
    const next = arr.join("").padEnd(i + 1, "").slice(0, 6);
    onChange(next.replace(/\s/g, ""));
    if (digit && i < 5) inputs.current[i + 1]?.focus();
  };
  const handleKeyDown = (i: number, e: React.KeyboardEvent) => {
    if (e.key === "Backspace" && !value[i] && i > 0) inputs.current[i - 1]?.focus();
  };
  const handlePaste = (e: React.ClipboardEvent) => {
    const text = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
    if (text.length === 6) { onChange(text); inputs.current[5]?.focus(); }
  };
  return (
    <div className="flex justify-center gap-2" onPaste={handlePaste}>
      {Array.from({ length: 6 }).map((_, i) => (
        <input key={i} ref={el => { inputs.current[i] = el; }} type="text" inputMode="numeric" maxLength={1}
          value={value[i] ?? ""} disabled={disabled}
          onChange={e => handleChange(i, e.target.value)}
          onKeyDown={e => handleKeyDown(i, e)}
          onClick={e => (e.target as HTMLInputElement).select()}
          className="h-12 w-10 rounded-xl border border-[var(--border)] bg-white text-center text-lg font-bold outline-none transition-all focus:border-[var(--ink)] focus:ring-2 focus:ring-[var(--ink)]/10 disabled:bg-gray-50 disabled:text-gray-300"
        />
      ))}
    </div>
  );
}

export default function StudentVerifyPage() {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const checkOnboarding = useAuthStore((s) => s.checkOnboarding);
  const [phase, setPhase] = useState<"info" | "otp">("info");

  // Phase 1: info
  const [university, setUniversity] = useState("");
  const [studentId, setStudentId] = useState("");
  const [studentEmail, setStudentEmail] = useState("");
  const [idCardFile, setIdCardFile] = useState<File | null>(null);

  // Phase 2: OTP
  const [otp, setOtp] = useState("");

  const requestOtp = useMutation({
    mutationFn: () => onboardingApi.requestStudentVerify({ university_name: university, student_id_number: studentId, student_email: studentEmail }),
    onSuccess: () => setPhase("otp"),
  });

  const confirmOtp = useMutation({
    mutationFn: () => onboardingApi.confirmStudentVerify({ otp_code: otp, id_card_image: idCardFile }),
    onSuccess: async () => {
      await checkOnboarding();
      router.push(onboardingStepHref("seeker_profile"));
    },
  });

  const skipVerification = useMutation({
    mutationFn: () => onboardingApi.saveSeekerProfile({}),
    onSuccess: async () => {
      await checkOnboarding();
      router.replace(workspaceHomeHref(user?.persona));
    },
  });

  // Auto-submit OTP
  useEffect(() => {
    if (otp.length === 6 && !confirmOtp.isPending) confirmOtp.mutate();
  }, [otp]); // eslint-disable-line

  if (phase === "otp") {
    return (
      <OnboardingShell title="Xác minh email sinh viên" subtitle={`Nhập mã 6 số đã gửi đến ${studentEmail}`} step={3} totalSteps={3}>
        <div className="space-y-5">
          <OtpInput value={otp} onChange={setOtp} disabled={confirmOtp.isPending} />
          {confirmOtp.isPending && <div className="flex justify-center"><CircleNotch className="size-5 animate-spin text-[var(--ink)]" /></div>}
          {confirmOtp.isError && <p className="text-center text-sm text-red-600">Mã không đúng hoặc đã hết hạn. Vui lòng thử lại.</p>}
          <p className="text-center text-xs text-[var(--text-tertiary)]">Mã có hiệu lực trong 10 phút</p>
          <button type="button" className="w-full text-center text-sm text-[var(--ink)] underline underline-offset-2" onClick={() => { setOtp(""); requestOtp.mutate(); }}>
            Gửi lại mã
          </button>
          <button
            type="button"
            disabled={skipVerification.isPending}
            className="h-11 w-full rounded-xl border border-[var(--border)] text-sm font-semibold text-[var(--text-primary)] transition-colors hover:bg-gray-50 disabled:opacity-40"
            onClick={() => skipVerification.mutate()}
          >
            Xác minh sau
          </button>
        </div>
      </OnboardingShell>
    );
  }

  return (
    <OnboardingShell title="Xác minh tư cách sinh viên" subtitle="Thông tin này sẽ được hiển thị huy hiệu sinh viên đã xác minh trên hồ sơ của bạn." step={3} totalSteps={3}>
      <form onSubmit={e => { e.preventDefault(); requestOtp.mutate(); }} className="space-y-4">
        <div className="space-y-1.5">
          <label className="text-sm font-medium">Tên trường</label>
          <input required className={inputCls} placeholder="Ví dụ: VinUniversity" value={university} onChange={e => setUniversity(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <label className="text-sm font-medium">Mã số sinh viên</label>
          <input required className={inputCls} placeholder="Ví dụ: VNU2021001" value={studentId} onChange={e => setStudentId(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <label className="text-sm font-medium">Email sinh viên (.edu)</label>
          <input required type="email" className={inputCls} placeholder="abc@vinuni.edu.vn" value={studentEmail} onChange={e => setStudentEmail(e.target.value)} />
          <p className="text-xs text-[var(--text-tertiary)]">Mã OTP sẽ được gửi đến email sinh viên này</p>
        </div>

        {/* ID card upload */}
        <div className="space-y-1.5">
          <label className="text-sm font-medium">Ảnh thẻ sinh viên <span className="text-[var(--text-tertiary)] font-normal">(tùy chọn)</span></label>
          <label className={`flex cursor-pointer items-center gap-2.5 rounded-xl border-2 border-dashed p-3.5 transition-colors ${idCardFile ? "border-[var(--ink)] bg-gray-50" : "border-[var(--border)] hover:border-gray-300"}`}>
            <input type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" onChange={e => setIdCardFile(e.target.files?.[0] ?? null)} />
            {idCardFile ? (
              <><CheckCircle weight="fill" className="size-5 text-[var(--ink)]" /><span className="text-sm font-medium">{idCardFile.name}</span></>
            ) : (
              <><UploadSimple weight="duotone" className="size-5 text-gray-400" /><span className="text-sm text-gray-500">Tải ảnh thẻ sinh viên lên (JPG/PNG, tối đa 5MB)</span></>
            )}
          </label>
        </div>

        <div className="flex gap-3 pt-1">
          <button type="button" onClick={() => router.push(onboardingStepHref("seeker_type"))}
            className="h-11 flex-1 rounded-xl border border-[var(--border)] text-sm font-medium hover:bg-gray-50">
            ← Quay lại
          </button>
          <button type="submit" disabled={requestOtp.isPending || !university || !studentId || !studentEmail}
            className="h-11 flex-[2] rounded-xl bg-[var(--ink)] text-sm font-semibold text-white hover:bg-gray-800 disabled:opacity-40">
            {requestOtp.isPending ? "Đang gửi OTP..." : "Nhận mã xác minh →"}
          </button>
        </div>
        <button
          type="button"
          disabled={skipVerification.isPending}
          onClick={() => skipVerification.mutate()}
          className="h-11 w-full rounded-xl border border-[var(--border)] text-sm font-semibold text-[var(--text-primary)] transition-colors hover:bg-gray-50 disabled:opacity-40"
        >
          {skipVerification.isPending ? "Đang hoàn tất..." : "Xác minh sau và vào hệ thống"}
        </button>
      </form>
    </OnboardingShell>
  );
}
