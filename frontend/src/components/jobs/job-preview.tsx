"use client";

import type { JobFormValues } from "@/lib/validation/jobs";
import type { JobLocationItem, CandidateRequirements } from "@/lib/api/jobs";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Salary display helper
// ---------------------------------------------------------------------------

function formatSalaryPreview(values: JobFormValues): string {
  const { salary_mode, salary_min, salary_max, salary_period, salary_currency } = values;
  const currency = salary_currency?.trim() || "VND";
  const periodLabel = salary_period === "yearly" ? "/năm" : "/tháng";

  function fmt(n: string | undefined): string {
    if (!n) return "";
    const num = Number(n);
    if (Number.isNaN(num)) return n;
    // Simplified display: divide by 1,000,000 → e.g. 20 triệu
    if (currency === "VND" && num >= 1_000_000) {
      return `${(num / 1_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 1 })} triệu`;
    }
    return num.toLocaleString();
  }

  switch (salary_mode) {
    case "negotiable":
      return "Thỏa thuận";
    case "hidden":
      return "Không công khai";
    case "fixed":
      return salary_min ? `${fmt(salary_min)}${periodLabel}` : "";
    case "from":
      return salary_min ? `Từ ${fmt(salary_min)}${periodLabel}` : "";
    case "to":
      return salary_max ? `Đến ${fmt(salary_max)}${periodLabel}` : "";
    case "range":
      if (salary_min && salary_max) {
        return `${fmt(salary_min)}–${fmt(salary_max)}${periodLabel}`;
      }
      if (salary_min) return `Từ ${fmt(salary_min)}${periodLabel}`;
      if (salary_max) return `Đến ${fmt(salary_max)}${periodLabel}`;
      return "";
    default:
      return "";
  }
}

// ---------------------------------------------------------------------------
// Eligibility summary — only active (non-"not_required") groups
// ---------------------------------------------------------------------------

function buildEligibilitySummary(cr: CandidateRequirements): string {
  const parts: string[] = [];

  // Gender
  const gender = cr.gender;
  if (gender && gender.mode !== "not_required" && gender.values.length > 0) {
    parts.push(gender.values.join("/"));
  }

  // Age
  const age = cr.age;
  if (age && age.mode !== "not_required") {
    if (age.mode === "range" && age.min != null && age.max != null) {
      parts.push(`${age.min}–${age.max} tuổi`);
    } else if (age.mode === "at_least" && age.min != null) {
      parts.push(`≥ ${age.min} tuổi`);
    } else if (age.mode === "up_to" && age.max != null) {
      parts.push(`≤ ${age.max} tuổi`);
    }
  }

  // Languages
  const langs = cr.languages ?? [];
  const activeLangs = langs.filter((l) => l.language.trim() !== "");
  if (activeLangs.length > 0) {
    parts.push(activeLangs.map((l) => l.language).join(", "));
  }

  // Education
  const edu = cr.education;
  if (edu && edu.mode !== "not_required" && edu.values.length > 0) {
    const firstEdu = edu.values[0];
    if (firstEdu) parts.push(firstEdu);
  }

  return parts.join(" · ");
}

// ---------------------------------------------------------------------------
// Prop types
// ---------------------------------------------------------------------------

export interface JobPreviewProps {
  values: JobFormValues;
  locations: JobLocationItem[];
  candidateReq: CandidateRequirements;
  companyName?: string;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function PreviewSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h3 className="mb-1.5 text-xs font-bold uppercase tracking-wide text-[var(--text-muted)]">
        {title}
      </h3>
      {children}
    </div>
  );
}

function PreviewChip({ label, muted }: { label: string; muted?: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-semibold",
        muted
          ? "bg-[var(--bg-subtle)] text-[var(--text-muted)]"
          : "bg-[var(--bg-subtle)] text-[var(--text-secondary)]",
      )}
    >
      {label}
    </span>
  );
}

function PreviewPlaceholder({ text }: { text: string }) {
  return (
    <p className="text-sm italic text-[var(--text-muted)]">{text}</p>
  );
}

function SkillChips({ raw, label }: { raw: string; label: string }) {
  const skills = raw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  if (skills.length === 0) return null;
  return (
    <div>
      <p className="mb-1 text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide">
        {label}
      </p>
      <div className="flex flex-wrap gap-1.5">
        {skills.map((s) => (
          <span
            key={s}
            className="inline-flex items-center rounded-full border border-[var(--border-default)] bg-[var(--surface-card)] px-2.5 py-0.5 text-[12px] font-medium text-[var(--text-primary)]"
          >
            {s}
          </span>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main presentational component — READ-ONLY, never mutates form state
// ---------------------------------------------------------------------------

export function JobPreview({
  values,
  locations,
  candidateReq,
  companyName,
}: JobPreviewProps) {
  const {
    title,
    employment_type,
    description,
    requirements,
    benefits,
    required_skills,
    preferred_skills,
    application_deadline,
    seniority_level,
  } = values;

  const displayTitle = title?.trim() || "Chưa có tiêu đề";
  const isTitleEmpty = !title?.trim();

  const locationLabel =
    locations.length > 0
      ? locations
          .map((l) => l.city ?? l.country)
          .filter((s): s is string => !!s)
          .join(", ")
      : null;

  const locationTypes = [...new Set(locations.map((l) => l.type).filter(Boolean))];

  const salaryDisplay = formatSalaryPreview(values);
  const eligibilitySummary = buildEligibilitySummary(candidateReq);

  const deadlineDisplay = application_deadline
    ? (() => {
        const d = new Date(application_deadline);
        return Number.isNaN(d.getTime())
          ? null
          : d.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" });
      })()
    : null;

  const employmentTypeLabel: Record<string, string> = {
    full_time: "Toàn thời gian",
    part_time: "Bán thời gian",
    internship: "Thực tập",
    contract: "Hợp đồng",
  };

  const locationTypeLabel: Record<string, string> = {
    onsite: "Tại văn phòng",
    remote: "Từ xa",
    hybrid: "Kết hợp",
  };

  const seniorityLabel: Record<string, string> = {
    intern: "Thực tập sinh",
    fresher: "Fresher",
    junior: "Junior",
    middle: "Middle",
    senior: "Senior",
    lead: "Trưởng nhóm",
    manager: "Quản lý",
    director: "Giám đốc",
    executive: "C-level",
  };

  return (
    <article
      aria-label="Xem trước tin tuyển dụng"
      className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card,#ffffff)] shadow-sm"
    >
      {/* Header */}
      <div className="border-b border-[var(--border-default)] px-5 py-4">
        <div className="mb-0.5 flex items-start justify-between gap-2">
          <h2
            className={cn(
              "text-base font-bold leading-snug",
              isTitleEmpty
                ? "text-[var(--text-muted)] italic"
                : "text-[var(--text-primary)]",
            )}
          >
            {displayTitle}
          </h2>
        </div>
        {(companyName || locationLabel) && (
          <p className="text-sm text-[var(--text-secondary)]">
            {[companyName, locationLabel].filter(Boolean).join(" · ")}
          </p>
        )}
      </div>

      {/* Meta chips row */}
      <div className="border-b border-[var(--border-default)] px-5 py-3">
        <div className="flex flex-wrap gap-1.5">
          {employment_type && employmentTypeLabel[employment_type] && (
            <PreviewChip label={employmentTypeLabel[employment_type]} />
          )}
          {locationTypes.map((lt) =>
            lt && locationTypeLabel[lt] ? (
              <PreviewChip key={lt} label={locationTypeLabel[lt]} />
            ) : null,
          )}
          {salaryDisplay ? (
            <PreviewChip label={salaryDisplay} />
          ) : (
            <PreviewChip label="Lương thỏa thuận" muted />
          )}
          {seniority_level && seniorityLabel[seniority_level] && (
            <PreviewChip label={seniorityLabel[seniority_level]} />
          )}
        </div>
      </div>

      {/* Body sections */}
      <div className="space-y-4 px-5 py-4">
        {/* Description */}
        <PreviewSection title="Mô tả công việc">
          {description?.trim() ? (
            <p className="whitespace-pre-line text-sm text-[var(--text-primary)] leading-relaxed">
              {description.trim()}
            </p>
          ) : (
            <PreviewPlaceholder text="Chưa có mô tả" />
          )}
        </PreviewSection>

        {/* Requirements */}
        {requirements?.trim() && (
          <div className="border-t border-[var(--border-default)] pt-4">
            <PreviewSection title="Yêu cầu">
              <p className="whitespace-pre-line text-sm text-[var(--text-primary)] leading-relaxed">
                {requirements.trim()}
              </p>
            </PreviewSection>
          </div>
        )}

        {/* Benefits */}
        {benefits?.trim() && (
          <div className="border-t border-[var(--border-default)] pt-4">
            <PreviewSection title="Quyền lợi">
              <p className="whitespace-pre-line text-sm text-[var(--text-primary)] leading-relaxed">
                {benefits.trim()}
              </p>
            </PreviewSection>
          </div>
        )}

        {/* Skills */}
        {(required_skills?.trim() || preferred_skills?.trim()) && (
          <div className="border-t border-[var(--border-default)] pt-4 space-y-3">
            {required_skills?.trim() && (
              <SkillChips raw={required_skills} label="Kỹ năng bắt buộc" />
            )}
            {preferred_skills?.trim() && (
              <SkillChips raw={preferred_skills} label="Kỹ năng ưu tiên" />
            )}
          </div>
        )}

        {/* Eligibility summary */}
        {eligibilitySummary && (
          <div className="border-t border-[var(--border-default)] pt-4">
            <PreviewSection title="Điều kiện ứng viên">
              <p className="text-sm text-[var(--text-secondary)]">{eligibilitySummary}</p>
            </PreviewSection>
          </div>
        )}
      </div>

      {/* Footer: deadline */}
      {deadlineDisplay && (
        <div className="border-t border-[var(--border-default)] px-5 py-3">
          <div className="flex flex-wrap items-center gap-4 text-xs text-[var(--text-muted)]">
            <span>
              <span className="font-semibold text-[var(--text-secondary)]">Hạn nộp:</span>{" "}
              {deadlineDisplay}
            </span>
          </div>
        </div>
      )}

      {/* Preview disclaimer */}
      <div className="rounded-b-2xl border-t border-[var(--border-default)] bg-[var(--bg-subtle)] px-5 py-2.5">
        <p className="text-[11px] text-[var(--text-muted)]">
          Đây là bản xem trước — nội dung cập nhật theo form.
        </p>
      </div>
    </article>
  );
}
