"use client";

import {
  ArrowRight,
  CheckCircle,
  ClockCountdown,
  FileMagnifyingGlass,
  Info,
  Robot,
  ShieldCheck,
  SignOut,
  SpinnerGap,
  WarningCircle,
} from "@phosphor-icons/react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import type {
  PendingRegistration,
  RegistrationStatus,
} from "@/lib/api/types";

const statusOrder: RegistrationStatus[] = [
  "SUBMITTED",
  "VERIFYING",
  "UNDER_REVIEW",
  "CHANGES_REQUESTED",
  "RESUBMITTED",
  "APPROVED",
];

export function PendingRegistrationScreen({
  registration,
  locale,
}: {
  registration: PendingRegistration;
  locale: string;
}) {
  const vi = locale === "vi";
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [confirmed, setConfirmed] = useState<string[]>(
    registration.checklist.filter((item) => item.resolved).map((item) => item.code),
  );
  const confidence = Number(registration.assessment.confidence || 0);
  const currentStep = useMemo(() => {
    if (registration.status === "PENDING") return 0;
    if (registration.status === "NEEDS_CHANGES") return 3;
    const index = statusOrder.indexOf(registration.status);
    return index < 0 ? 0 : index;
  }, [registration.status]);

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push(`/${locale}/login`);
    router.refresh();
  }

  async function resubmit() {
    setSubmitting(true);
    const response = await fetch("/api/backend/registrations/me/resubmit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        checklist_codes: confirmed,
        note: vi
          ? "Tôi xác nhận đã kiểm tra và cập nhật các mục được yêu cầu."
          : "I confirm that the requested items have been reviewed and updated.",
      }),
    });
    if (response.ok) {
      toast.success(vi ? "Đã gửi lại hồ sơ phiên bản mới" : "New version submitted");
      router.refresh();
    } else {
      const body = await response.json().catch(() => ({}));
      toast.error(body?.error?.message || body?.detail || "Unable to resubmit");
    }
    setSubmitting(false);
  }

  const canResubmit = registration.allowed_actions.includes("resubmit");
  const allConfirmed =
    registration.checklist.length > 0 &&
    registration.checklist.every((item) => confirmed.includes(item.code));

  return (
    <main className="min-h-screen bg-slate-50">
      <header className="border-b bg-white">
        <div className="mx-auto flex h-20 max-w-6xl items-center gap-4 px-5">
          <Image
            src="/brand/vinuni-logo-text.png"
            alt="VinUniversity Career Platform"
            width={220}
            height={60}
            className="h-11 w-auto object-contain"
            priority
          />
          <Badge tone="blue" className="ml-auto hidden sm:inline-flex">
            {vi ? "Cổng theo dõi hồ sơ" : "Registration portal"}
          </Badge>
          <Button variant="ghost" size="sm" onClick={logout}>
            <SignOut className="size-4" />
            {vi ? "Đăng xuất" : "Sign out"}
          </Button>
        </div>
      </header>

      <div className="mx-auto max-w-6xl space-y-6 px-5 py-8">
        <section className="overflow-hidden rounded-2xl bg-navy text-white shadow-sm">
          <div className="grid gap-6 p-6 md:grid-cols-[1fr_260px] md:p-8">
            <div>
              <Badge tone={statusTone(registration.status)}>
                {statusLabel(registration.status, vi)}
              </Badge>
              <h1 className="mt-4 text-2xl font-semibold md:text-3xl">
                {vi
                  ? `Xin chào, ${registration.applicant_name}`
                  : `Hello, ${registration.applicant_name}`}
              </h1>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-blue-100">
                {vi
                  ? "Bạn có thể theo dõi từng bước xác minh, xem bằng chứng hệ thống sử dụng và xử lý chính xác các mục nhà trường yêu cầu."
                  : "Track each verification step, inspect the evidence used, and resolve exactly what the university requests."}
              </p>
              <p className="mt-5 font-mono text-xs text-blue-200">
                {vi ? "Mã hồ sơ" : "Application"} {registration.id} · v
                {registration.version}
              </p>
            </div>
            <div className="rounded-xl bg-white/10 p-5 backdrop-blur">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <Robot className="size-5 text-cyan" weight="duotone" />
                {vi ? "Đánh giá hỗ trợ" : "Assisted assessment"}
              </div>
              <p className="mt-4 text-4xl font-semibold">{confidence}%</p>
              <Progress
                value={confidence}
                className="mt-3 bg-white/15"
                indicatorClassName="bg-cyan"
              />
              <p className="mt-3 text-xs leading-5 text-blue-100">
                {vi
                  ? "Đây là khuyến nghị hỗ trợ; quyết định từ chối luôn do con người thực hiện."
                  : "This is decision support; rejection always requires a human reviewer."}
              </p>
            </div>
          </div>
        </section>

        <section className="rounded-2xl border bg-white p-5 md:p-6">
          <div className="flex items-center gap-2">
            <ClockCountdown className="size-5 text-primary" weight="duotone" />
            <h2 className="font-semibold">
              {vi ? "Tiến trình xác minh" : "Verification progress"}
            </h2>
          </div>
          <div className="mt-6 grid gap-3 md:grid-cols-6">
            {statusOrder.map((status, index) => {
              const done = index <= currentStep;
              const active = index === currentStep;
              return (
                <div key={status} className="relative">
                  <div
                    className={`flex size-9 items-center justify-center rounded-full border-2 ${
                      done
                        ? "border-primary bg-primary text-white"
                        : "border-slate-200 bg-white text-slate-400"
                    }`}
                  >
                    {done && !active ? (
                      <CheckCircle className="size-5" weight="fill" />
                    ) : (
                      index + 1
                    )}
                  </div>
                  <p className="mt-2 text-xs font-semibold">
                    {statusLabel(status, vi)}
                  </p>
                </div>
              );
            })}
          </div>
        </section>

        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
          <section className="rounded-2xl border bg-white">
            <div className="border-b p-5">
              <div className="flex items-center gap-2">
            <FileMagnifyingGlass className="size-5 text-primary" weight="duotone" />
                <h2 className="font-semibold">
                  {vi ? "Bằng chứng xác minh" : "Verification evidence"}
                </h2>
              </div>
              <p className="mt-1 text-sm text-muted">
                {vi
                  ? "Mỗi tín hiệu đều có nguồn, độ tin cậy và provenance."
                  : "Every signal includes its source, confidence, and provenance."}
              </p>
            </div>
            <div className="divide-y">
              {registration.evidence.map((item) => (
                <article key={item.id} className="p-5">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-semibold">
                      {item.field_name.replaceAll("_", " ")}
                    </p>
                    <Badge tone={item.mismatch ? "red" : item.confidence >= 80 ? "green" : "amber"}>
                      {item.confidence}% confidence
                    </Badge>
                  </div>
                  <p className="mt-2 text-sm text-muted">
                    {item.provider.replaceAll("_", " ")} · {item.authority.replaceAll("_", " ")}
                  </p>
                  {item.provenance.status === "provider_unavailable" ? (
                    <div className="mt-3 flex items-start gap-2 rounded-lg bg-amber-50 p-3 text-xs text-amber-800">
                      <Info className="mt-0.5 size-4 shrink-0" />
                      {vi
                        ? "Nhà cung cấp đang không khả dụng. Hồ sơ được chuyển sang duyệt thủ công, không bị từ chối tự động."
                        : "Provider unavailable. The application moves to manual review and is not automatically rejected."}
                    </div>
                  ) : null}
                </article>
              ))}
            </div>
          </section>

          <aside className="space-y-6">
            <section className="rounded-2xl border bg-white p-5">
              <div className="flex items-center gap-2">
                <ShieldCheck className="size-5 text-primary" weight="duotone" />
                <h2 className="font-semibold">
                  {vi ? "Chính sách đang áp dụng" : "Applied policy"}
                </h2>
              </div>
              <dl className="mt-5 space-y-3 text-sm">
                <InfoRow label="Mode" value={registration.policy_snapshot.mode || "SHADOW"} />
                <InfoRow
                  label={vi ? "Ngưỡng" : "Threshold"}
                  value={`${registration.policy_snapshot.confidence_threshold || 90}%`}
                />
                <InfoRow
                  label={vi ? "Phiên bản" : "Version"}
                  value={registration.policy_snapshot.model_version || "deterministic-v1"}
                />
              </dl>
            </section>

            {canResubmit ? (
              <section className="rounded-2xl border border-amber-200 bg-amber-50 p-5">
                <div className="flex items-center gap-2 text-amber-900">
                  <WarningCircle className="size-5" weight="fill" />
                  <h2 className="font-semibold">
                    {vi ? "Cần bổ sung thông tin" : "Changes requested"}
                  </h2>
                </div>
                {registration.review_note ? (
                  <p className="mt-3 text-sm leading-6 text-amber-900">
                    {registration.review_note}
                  </p>
                ) : null}
                <div className="mt-4 space-y-2">
                  {registration.checklist.map((item) => (
                    <label
                      key={item.code}
                      className="flex cursor-pointer items-start gap-3 rounded-lg bg-white p-3 text-sm"
                    >
                      <input
                        type="checkbox"
                        className="mt-1"
                        checked={confirmed.includes(item.code)}
                        onChange={(event) =>
                          setConfirmed((current) =>
                            event.target.checked
                              ? [...current, item.code]
                              : current.filter((code) => code !== item.code),
                          )
                        }
                      />
                      <span>{item.label}</span>
                    </label>
                  ))}
                </div>
                <Button
                  className="mt-4 w-full"
                  disabled={!allConfirmed || submitting}
                  onClick={resubmit}
                >
                  {submitting ? (
                    <SpinnerGap className="size-4 animate-spin" />
                  ) : (
                    <ArrowRight className="size-4" />
                  )}
                  {vi ? "Gửi lại phiên bản mới" : "Submit new version"}
                </Button>
              </section>
            ) : null}
          </aside>
        </div>
      </div>
    </main>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <dt className="text-muted">{label}</dt>
      <dd className="text-right font-semibold">{value}</dd>
    </div>
  );
}

function statusLabel(status: RegistrationStatus, vi: boolean) {
  const labels: Record<RegistrationStatus, [string, string]> = {
    DRAFT: ["Bản nháp", "Draft"],
    SUBMITTED: ["Đã gửi", "Submitted"],
    VERIFYING: ["Đang xác minh", "Verifying"],
    PENDING: ["Đã gửi", "Submitted"],
    UNDER_REVIEW: ["Đang duyệt", "Under review"],
    CHANGES_REQUESTED: ["Cần bổ sung", "Changes requested"],
    NEEDS_CHANGES: ["Cần bổ sung", "Changes requested"],
    RESUBMITTED: ["Đã gửi lại", "Resubmitted"],
    APPROVED: ["Đã phê duyệt", "Approved"],
    REJECTED: ["Đã từ chối", "Rejected"],
    WITHDRAWN: ["Đã rút", "Withdrawn"],
  };
  return labels[status][vi ? 0 : 1];
}

function statusTone(
  status: RegistrationStatus,
): "blue" | "green" | "amber" | "red" | "gray" {
  if (status === "APPROVED") return "green";
  if (status === "REJECTED" || status === "WITHDRAWN") return "red";
  if (status === "CHANGES_REQUESTED" || status === "NEEDS_CHANGES") return "amber";
  if (status === "DRAFT") return "gray";
  return "blue";
}
