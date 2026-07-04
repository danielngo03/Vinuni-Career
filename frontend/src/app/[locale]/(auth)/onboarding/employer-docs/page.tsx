"use client";

import { useState, useCallback, useEffect } from "react";
import { useRouter } from "@/i18n/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { onboardingApi, type AiDocStatus } from "@/lib/api/onboarding";
import { onboardingStepHref } from "@/lib/onboarding/routes";
import { OnboardingShell } from "@/components/onboarding/onboarding-shell";
import { useAuthStore } from "@/stores/auth-store";
import { CheckCircle, UploadSimple, FilePdf, CircleNotch, Warning, MagnifyingGlass } from "@phosphor-icons/react";

const inputCls = "w-full rounded-xl border border-[var(--border)] bg-white px-3.5 py-2.5 text-sm outline-none transition-all placeholder:text-gray-400 focus:border-[var(--ink)] focus:ring-2 focus:ring-[var(--ink)]/10";

type Phase = "upload" | "processing" | "result";

const STATUS_LABELS: Record<AiDocStatus, { label: string; desc: string; color: string }> = {
  pending:       { label: "Đang xử lý...", desc: "Hệ thống đang phân tích tài liệu của bạn.", color: "text-gray-500" },
  passed:        { label: "Tài liệu hợp lệ", desc: "Tài liệu đã vượt qua kiểm tra xác thực AI.", color: "text-green-600" },
  tampered:      { label: "Phát hiện gian lận", desc: "Tài liệu có dấu hiệu chỉnh sửa. Vui lòng cung cấp tài liệu gốc.", color: "text-red-600" },
  manual_review: { label: "Đang xét duyệt thủ công", desc: "Tài liệu cần được đội ngũ VinUni xem xét thêm. Chúng tôi sẽ liên hệ trong 1-3 ngày làm việc.", color: "text-amber-600" },
};

export default function EmployerDocsPage() {
  const router = useRouter();
  const checkOnboarding = useAuthStore((s) => s.checkOnboarding);
  const [phase, setPhase] = useState<Phase>("upload");
  const [docFile, setDocFile] = useState<File | null>(null);
  const [taxId, setTaxId] = useState("");
  const [dragOver, setDragOver] = useState(false);

  const submitMutation = useMutation({
    mutationFn: () => onboardingApi.submitEmployerDocs({ document: docFile!, tax_id: taxId || undefined }),
    onSuccess: async () => {
      await checkOnboarding();
      setPhase("processing");
    },
  });

  // Poll AI verification status once submitted
  const statusQuery = useQuery({
    queryKey: ["employer-doc-status"],
    queryFn: () => onboardingApi.getEmployerDocStatus(),
    enabled: phase === "processing",
    refetchInterval: (query) => {
      const status = query.state.data?.ai_doc_status;
      // Stop polling when terminal state reached
      if (status === "passed" || status === "tampered" || status === "manual_review") {
        return false;
      }
      return 3000; // Poll every 3 seconds
    },
  });

  const aiStatus: AiDocStatus = statusQuery.data?.ai_doc_status ?? "pending";
  const info = STATUS_LABELS[aiStatus];

  // When status is determined, switch to result phase
  const isTerminal = aiStatus === "passed" || aiStatus === "tampered" || aiStatus === "manual_review";
  useEffect(() => {
    if (phase !== "processing" || !isTerminal || !statusQuery.isFetched) return;
    const timer = window.setTimeout(() => setPhase("result"), 300);
    return () => window.clearTimeout(timer);
  }, [phase, isTerminal, statusQuery.isFetched]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) setDocFile(file);
  }, []);

  const handleContinue = () => {
    if (aiStatus === "passed") {
      router.push(onboardingStepHref("pending"));
    } else if (aiStatus === "tampered") {
      // Let user re-upload
      setPhase("upload");
      setDocFile(null);
    } else {
      // manual_review - go to pending
      router.push(onboardingStepHref("pending"));
    }
  };

  // ── Processing phase ──────────────────────────────────────────────────────
  if (phase === "processing") {
    return (
      <OnboardingShell title="Đang xác minh tài liệu" subtitle="AI đang kiểm tra tính xác thực của giấy đăng ký kinh doanh." step={3} totalSteps={3}>
        <div className="flex flex-col items-center gap-6 py-8">
          <div className="relative flex h-20 w-20 items-center justify-center rounded-2xl bg-gray-50">
            {aiStatus === "pending" && <CircleNotch className="size-10 animate-spin text-[var(--ink)]" />}
            {aiStatus === "passed" && <CheckCircle weight="fill" className="size-10 text-green-500" />}
            {aiStatus === "tampered" && <Warning weight="fill" className="size-10 text-red-500" />}
            {aiStatus === "manual_review" && <MagnifyingGlass weight="duotone" className="size-10 text-amber-500" />}
          </div>
          <div className="space-y-1 text-center">
            <p className={`font-semibold ${info.color}`}>{info.label}</p>
            <p className="text-sm text-[var(--text-secondary)]">{info.desc}</p>
          </div>
          {aiStatus === "pending" && (
            <p className="text-xs text-[var(--text-tertiary)]">Thường mất 10–30 giây</p>
          )}
        </div>
      </OnboardingShell>
    );
  }

  // ── Result phase ──────────────────────────────────────────────────────────
  if (phase === "result") {
    return (
      <OnboardingShell title="Kết quả kiểm tra" subtitle="Kết quả xác thực tài liệu đăng ký kinh doanh." step={3} totalSteps={3}>
        <div className="flex flex-col items-center gap-6 py-6">
          <div className="flex h-20 w-20 items-center justify-center rounded-2xl bg-gray-50">
            {aiStatus === "passed" && <CheckCircle weight="fill" className="size-10 text-green-500" />}
            {aiStatus === "tampered" && <Warning weight="fill" className="size-10 text-red-500" />}
            {aiStatus === "manual_review" && <MagnifyingGlass weight="duotone" className="size-10 text-amber-500" />}
          </div>
          <div className="space-y-1 text-center">
            <p className={`font-semibold ${info.color}`}>{info.label}</p>
            <p className="max-w-xs text-sm text-[var(--text-secondary)]">{info.desc}</p>
          </div>
        </div>

        <div className="flex gap-3">
          {aiStatus === "tampered" ? (
            <>
              <button onClick={() => { setPhase("upload"); setDocFile(null); }}
                className="h-11 flex-1 rounded-xl border border-[var(--border)] text-sm font-medium hover:bg-gray-50">
                Tải lại tài liệu
              </button>
              <button onClick={() => router.push(onboardingStepHref("employer_info"))}
                className="h-11 flex-1 rounded-xl bg-[var(--ink)] text-sm font-semibold text-white hover:bg-gray-800">
                ← Quay lại
              </button>
            </>
          ) : (
            <button onClick={handleContinue}
              className="h-11 w-full rounded-xl bg-[var(--ink)] text-sm font-semibold text-white hover:bg-gray-800">
              {aiStatus === "passed" ? "Tiếp tục →" : "Xem trạng thái đơn →"}
            </button>
          )}
        </div>
      </OnboardingShell>
    );
  }

  // ── Upload phase (default) ────────────────────────────────────────────────
  return (
    <OnboardingShell
      title="Tài liệu doanh nghiệp"
      subtitle="Tải lên giấy đăng ký kinh doanh. AI sẽ xác minh tính xác thực tự động."
      step={3}
      totalSteps={3}
    >
      <form onSubmit={e => { e.preventDefault(); submitMutation.mutate(); }} className="space-y-5">

        {/* File Drop Zone */}
        <div>
          <p className="mb-1.5 text-sm font-medium">Giấy đăng ký kinh doanh <span className="text-red-500">*</span></p>
          <label
            onDragOver={e => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            className={`flex cursor-pointer flex-col items-center gap-3 rounded-xl border-2 border-dashed py-8 text-center transition-colors ${
              dragOver ? "border-[var(--ink)] bg-gray-50" :
              docFile ? "border-[var(--ink)] bg-gray-50" :
              "border-[var(--border)] hover:border-gray-300"
            }`}
          >
            <input type="file" accept=".pdf,image/jpeg,image/png" className="sr-only"
              onChange={e => setDocFile(e.target.files?.[0] ?? null)} />
            {docFile ? (
              <>
                <FilePdf weight="duotone" className="size-8 text-[var(--ink)]" />
                <div>
                  <p className="text-sm font-medium text-[var(--ink)]">{docFile.name}</p>
                  <p className="text-xs text-[var(--text-tertiary)]">{(docFile.size / 1024 / 1024).toFixed(1)} MB</p>
                </div>
                <span className="text-xs text-[var(--text-tertiary)] underline">Chọn lại</span>
              </>
            ) : (
              <>
                <UploadSimple weight="duotone" className="size-8 text-gray-400" />
                <div>
                  <p className="text-sm font-medium">Kéo thả hoặc nhấn để tải file</p>
                  <p className="text-xs text-[var(--text-tertiary)]">PDF, JPG, PNG — tối đa 10MB</p>
                </div>
              </>
            )}
          </label>
          <p className="mt-1.5 text-xs text-[var(--text-tertiary)]">
            Vui lòng cung cấp bản gốc hoặc bản sao công chứng. Ảnh chụp rõ nét cũng được chấp nhận.
          </p>
        </div>

        {/* Tax ID */}
        <div className="space-y-1.5">
          <label className="text-sm font-medium">Mã số thuế (MST)</label>
          <input className={inputCls} placeholder="Ví dụ: 0123456789" value={taxId}
            onChange={e => setTaxId(e.target.value.replace(/\D/g, "").slice(0, 14))}
          />
          <p className="text-xs text-[var(--text-tertiary)]">
            Hệ thống sẽ tự động tra cứu MST qua cơ sở dữ liệu Tổng cục Thuế (GDT).
          </p>
        </div>

        {/* Privacy notice */}
        <div className="rounded-xl bg-gray-50 px-4 py-3 text-xs text-[var(--text-secondary)]">
          Tài liệu của bạn được mã hóa và chỉ dùng cho mục đích xác minh. Chúng tôi không chia sẻ với bên thứ ba.
        </div>

        {submitMutation.isError && (
          <p className="text-sm text-red-600">Đã xảy ra lỗi khi tải lên. Vui lòng thử lại.</p>
        )}

        <div className="flex gap-3">
          <button type="button" onClick={() => router.push(onboardingStepHref("employer_info"))}
            className="h-11 flex-1 rounded-xl border border-[var(--border)] text-sm font-medium hover:bg-gray-50">
            ← Quay lại
          </button>
          <button type="submit" disabled={submitMutation.isPending || !docFile}
            className="h-11 flex-[2] rounded-xl bg-[var(--ink)] text-sm font-semibold text-white hover:bg-gray-800 disabled:opacity-40">
            {submitMutation.isPending ? (
              <span className="flex items-center justify-center gap-2">
                <CircleNotch className="size-4 animate-spin" /> Đang tải lên...
              </span>
            ) : "Gửi để xác minh →"}
          </button>
        </div>
      </form>
    </OnboardingShell>
  );
}
