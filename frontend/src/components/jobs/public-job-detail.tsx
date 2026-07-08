"use client";

import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  Briefcase,
  Buildings,
  MapPin,
  CurrencyCircleDollar,
  Clock,
  Users,
  GraduationCap,
  SealCheck,
  Star,
  WarningCircle,
  MagnifyingGlass,
  CaretRight,
  ShareNetwork,
} from "@phosphor-icons/react";
import { useEffect, useId, useState } from "react";
import { Link } from "@/i18n/navigation";
import {
  Button,
  EmptyState,
  Skeleton,
  StatusBadge,
  SponsoredLabel,
  useToast,
} from "@/components/ui";
import { useUiStore } from "@/stores/ui-store";
import { useAuthStore } from "@/stores/auth-store";
import { useJobLabels } from "@/lib/jobs/labels";
import { formatSalary, formatLocation } from "@/lib/jobs/format";
import { deriveApplyCta } from "@/lib/jobs/job-intelligence";
import { ApiError, jobsApi, type JobTranslation } from "@/lib/api";
import { CompanyAvatar } from "@/components/companies/company-avatar";
import { ApplyModal } from "@/components/applications/apply-modal";
import { SaveJobButton } from "@/components/jobs/save-job-button";
import { CompetitionBadge } from "@/components/jobs/competition-badge";
import { StudentJobIntelligencePanel } from "@/components/jobs/student-job-intelligence-panel";
import { SimilarJobsRail } from "@/components/discovery/similar-jobs-rail";
import { TrackedItem } from "@/components/discovery/tracked-item";
import { TranslateJobBanner } from "@/components/jobs/translate-job-banner";
import { ReportButton } from "@/components/report/report-button";
import { recordDiscoveryEvent } from "@/lib/discovery/analytics";
import { jobSignalTags } from "@/lib/discovery/signal-tags";
import { recordJobEngagement } from "@/lib/analytics/job-engagement";


export function PublicJobDetail({ jobId }: { jobId: string }) {
  const t = useTranslations("jobs");
  const tNav = useTranslations("nav");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const labels = useJobLabels();
  const openLoginModal = useUiStore((s) => s.openLoginModal);
  const status = useAuthStore((s) => s.status);
  const user = useAuthStore((s) => s.user);
  const toast = useToast();
  const [applyOpen, setApplyOpen] = useState(false);
  const [translation, setTranslation] = useState<JobTranslation | null>(null);
  const renderId = useId();

  // Job-fit is owner-scoped (the student's own CVs). Only students see it.
  const isStudent = status === "authenticated" && user?.persona === "student";

  const query = useQuery({
    queryKey: ["jobs", "detail", jobId],
    queryFn: () => jobsApi.getPublic(jobId),
    retry: false,
  });

  // Apply-readiness comes from the same student-intelligence read the fit panel
  // uses (shared query key → one fetch, one cache). Only students call it; it
  // surfaces the server's own apply guard (`already_applied` / `deadline_passed`)
  // so the primary CTA never invites a duplicate the backend would 409.
  const intel = useQuery({
    queryKey: ["jobs", "student-intelligence", jobId],
    queryFn: () => jobsApi.studentIntelligence(jobId),
    enabled: isStudent,
    retry: false,
    staleTime: 60_000,
  });

  const job = query.data;

  // Record a privacy-safe `view` discovery event once the real job loads. This
  // is what feeds the coarse-signal ranker: a guest reading many JDs now
  // registers company/work-mode/city affinity (and role_family/industry once the
  // public job projection stamps them). Fire-and-forget + deduped by key.
  useEffect(() => {
    if (!job) return;
    recordDiscoveryEvent({
      event_type: "view",
      source_surface: "job_detail",
      target_type: "job",
      target_id: job.id,
      idempotency_key: `${renderId}:${job.id}:view`,
      signal_tags: jobSignalTags(job),
    });
  }, [job, renderId]);

  const salary = job ? formatSalary(job.salary, locale) : null;
  const isHydratingAuth = status === "unknown";
  const isGuest = status === "guest";
  const canApply = isStudent;
  const applyReadiness = intel.data?.apply_readiness;
  const applyCta = deriveApplyCta({
    isHydrating: isHydratingAuth,
    isGuest,
    canApply,
    alreadyApplied: applyReadiness?.already_applied ?? false,
    deadlinePassed: applyReadiness?.deadline_passed ?? false,
  });
  function handleApply() {
    if (isHydratingAuth) return;
    // The apply button is this page's primary CTA — record it against the
    // partner job-performance funnel regardless of which branch handles it.
    recordJobEngagement(jobId, "cta_click", "organic");
    if (isGuest) {
      // Record the apply intent before the gate so guest conversion is measured.
      recordDiscoveryEvent({
        event_type: "apply_start",
        source_surface: "job_detail",
        target_type: "job",
        target_id: jobId,
        idempotency_key: `${renderId}:${jobId}:apply_start_guest`,
      });
      openLoginModal({
        label: t("applyIntent"),
        returnTo: `/jobs/${jobId}`,
      });
      return;
    }
    if (!canApply) return;
    recordDiscoveryEvent({
      event_type: "apply_start",
      source_surface: "job_detail",
      target_type: "job",
      target_id: jobId,
      idempotency_key: `${renderId}:${jobId}:apply_start`,
    });
    setApplyOpen(true);
  }

  async function handleShare() {
    recordJobEngagement(jobId, "share_click", "organic");
    const url =
      typeof window !== "undefined" ? window.location.href : `/jobs/${jobId}`;
    try {
      if (typeof navigator !== "undefined" && navigator.share) {
        await navigator.share({ title: job?.title ?? undefined, url });
        return;
      }
      if (typeof navigator !== "undefined" && navigator.clipboard) {
        await navigator.clipboard.writeText(url);
        toast.show({ tone: "success", title: t("shareLinkCopied") });
      }
    } catch {
      // User cancelled the native share sheet, or clipboard write failed —
      // no error toast; sharing is a best-effort convenience action.
    }
  }

  return (
    <div className="career-container py-8 lg:py-10">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <nav
          aria-label="Breadcrumb"
          className="flex min-w-0 items-center gap-2 text-sm font-medium text-[var(--text-muted)]"
        >
          <Link
            href="/"
            className="rounded-md outline-none transition-colors hover:text-[var(--brand-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
          >
            VinUni Career
          </Link>
          <CaretRight aria-hidden weight="bold" className="size-3.5 shrink-0" />
          <Link
            href="/jobs"
            className="rounded-md outline-none transition-colors hover:text-[var(--brand-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
          >
            {tNav("jobs")}
          </Link>
          {job && (
            <>
              <CaretRight aria-hidden weight="bold" className="size-3.5 shrink-0" />
              <span className="max-w-[48vw] truncate text-[var(--text-secondary)] sm:max-w-[420px]">
                {job.title}
              </span>
            </>
          )}
        </nav>
      </div>

      {query.isError ? (
        query.error instanceof ApiError && query.error.isNotFound ? (
          <EmptyState
            kind="empty"
            icon={MagnifyingGlass}
            title={t("notFoundTitle")}
            description={t("notFoundBody")}
            action={
              <Link href="/jobs">
                <Button variant="secondary">{t("backToBoard")}</Button>
              </Link>
            }
          />
        ) : (
          <EmptyState
            kind="error"
            icon={WarningCircle}
            title={tStates("errorTitle")}
            description={tStates("errorBody")}
            action={
              <Button variant="secondary" onClick={() => query.refetch()}>
                {tc("retry")}
              </Button>
            }
          />
        )
      ) : query.isPending ? (
        <div className="space-y-4">
          <Skeleton className="h-8 w-2/3" />
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="mt-6 h-40 w-full" />
        </div>
      ) : job ? (
        <>
        <div className="grid grid-cols-1 gap-7 lg:grid-cols-[minmax(0,1fr)_360px]">
          {/* Main content */}
          <article className="marketplace-card min-w-0 overflow-hidden rounded-[20px]">
            <header className="border-b border-[var(--border-default)] bg-[var(--surface-card)] p-5 sm:p-7">
              <div className="flex flex-wrap items-center justify-between gap-3">
                {/* Company attribution chip */}
                {job.company && (
                  <Link
                    href={`/companies/${job.company.slug}`}
                    className="inline-flex items-center gap-2.5 rounded-full border border-[var(--border-default)] bg-[var(--surface-secondary)] px-3.5 py-2 text-sm font-semibold text-[var(--text-primary)] outline-none transition-all hover:border-[var(--brand-primary)]/40 hover:bg-[var(--surface-card)] hover:text-[var(--brand-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
                    title={t("viewCompany")}
                  >
                    <CompanyAvatar
                      name={job.company.display_name}
                      logoUrl={job.company.logo_url}
                      size="sm"
                    />
                    <span>{job.company.display_name}</span>
                    {job.company.is_verified && (
                      <SealCheck
                        aria-label={t("verifiedPartner")}
                        weight="fill"
                        className="size-4 text-[var(--brand-teal)]"
                      />
                    )}
                  </Link>
                )}
                <div className="flex items-center gap-2">
                  {job.is_sponsored && <SponsoredLabel label={t("sponsored")} />}
                  {job.is_featured && (
                    <StatusBadge tone="featured">
                      <Star aria-hidden weight="fill" className="size-3" />
                      {t("featured")}
                    </StatusBadge>
                  )}
                  <SaveJobButton
                    jobId={job.id}
                    returnTo={`/jobs/${jobId}`}
                    initialSaved={job.is_saved ?? false}
                  />
                  <button
                    type="button"
                    onClick={handleShare}
                    aria-label={t("shareJob")}
                    title={t("shareJob")}
                    className="flex size-8 shrink-0 items-center justify-center rounded-full border border-[var(--border-default)] bg-[var(--surface-card)] text-[var(--text-secondary)] outline-none transition-colors hover:border-[var(--border-strong)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
                  >
                    <ShareNetwork aria-hidden weight="duotone" className="size-4" />
                  </button>
                  <ReportButton entityType="job" entityId={job.id} entityLabel={job.title} variant="icon" />
                </div>
              </div>

              <h1 className="mt-5 max-w-[900px] text-[2rem] font-extrabold leading-[1.1] tracking-tight text-[var(--text-primary)] sm:text-[2.5rem]">
                {job.title}
              </h1>

              <dl className="mt-6 grid grid-cols-1 overflow-hidden rounded-[16px] border border-[var(--border-default)] sm:grid-cols-2 xl:grid-cols-3">
                <Meta icon={Briefcase} label={t("employmentType")}>
                  {labels.employmentType(job.employment_type, job.employment_type_label)}
                  {" · "}
                  {labels.locationType(job.location_type, job.location_type_label)}
                </Meta>
                <Meta icon={MapPin} label={t("location")}>
                  {formatLocation(job.location_city, job.location_country)}
                </Meta>
                <Meta icon={CurrencyCircleDollar} label={t("salary")}>
                  {salary ?? t("salaryUndisclosed")}
                </Meta>
                <Meta icon={Users} label={t("headcount")}>
                  {job.headcount}
                </Meta>
                {job.experience_display && (
                  <Meta icon={Clock} label={t("experience")}>
                    {job.experience_display.label}
                  </Meta>
                )}
                {job.degree_required && (
                  <Meta icon={GraduationCap} label={t("degree")}>
                    {job.degree_required}
                  </Meta>
                )}
              </dl>
            </header>

            <div className="p-5 sm:p-7">
              {/* Translation banner — shown when JD language ≠ UI locale */}
              {job.language_code && job.language_code !== "unknown" && (
                <TranslateJobBanner
                  jobId={job.id}
                  jobLanguageCode={job.language_code}
                  onTranslated={setTranslation}
                  translated={translation !== null}
                  className="mb-6"
                />
              )}

              <Section title={t("description")}>
                {translation?.description ?? job.description}
              </Section>
              {(translation?.requirements ?? job.requirements) && (
                <Section title={t("requirements")}>
                  {translation?.requirements ?? job.requirements}
                </Section>
              )}
              {(translation?.benefits ?? job.benefits) && (
                <Section title={t("benefits")}>
                  {translation?.benefits ?? job.benefits}
                </Section>
              )}

              {job.required_skills.length > 0 && (
                <SkillBlock title={t("requiredSkills")} skills={job.required_skills} />
              )}
              {job.preferred_skills.length > 0 && (
                <SkillBlock title={t("preferredSkills")} skills={job.preferred_skills} />
              )}
            </div>
          </article>

          {/* Apply sidebar */}
          <aside className="lg:sticky lg:top-24 lg:self-start">
            <div className="marketplace-card rounded-[16px] p-5">
              {job.application_deadline && (
                <p className="mb-3 flex items-center gap-1.5 text-sm text-[var(--text-secondary)]">
                  <Clock aria-hidden weight="duotone" className="size-4 text-[var(--text-muted)]" />
                  {t("deadline")}:{" "}
                  {new Date(job.application_deadline).toLocaleDateString(
                    locale === "vi" ? "vi-VN" : "en-US",
                  )}
                </p>
              )}
              <Button
                variant="primary"
                fullWidth
                disabled={applyCta.disabled}
                onClick={handleApply}
              >
                {applyCta.label === "loading"
                  ? tc("loading")
                  : applyCta.label === "signIn"
                    ? t("signInToApply")
                    : applyCta.label === "studentsOnly"
                      ? t("studentsOnlyApply")
                      : applyCta.label === "alreadyApplied"
                        ? t("alreadyApplied")
                        : applyCta.label === "deadlinePassed"
                          ? t("deadlinePassed")
                          : t("apply")}
              </Button>
              {applyCta.showViewApplications && (
                <Link
                  href="/student/applications"
                  className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-lg border border-[var(--border-default)] px-3 py-2 text-sm font-semibold text-[var(--text-primary)] outline-none transition-colors hover:bg-[var(--surface-hover)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
                >
                  {t("viewMyApplication")}
                </Link>
              )}
              <p className="mt-3 text-xs text-[var(--text-muted)]">
                {applyCta.label === "signIn"
                  ? t("guestApplyHint")
                  : applyCta.label === "studentsOnly"
                    ? t("studentsOnlyApplyHint")
                    : applyCta.label === "alreadyApplied"
                      ? t("alreadyAppliedHint")
                      : applyCta.label === "deadlinePassed"
                        ? t("deadlinePassedHint")
                        : t("applyHint")}
              </p>
            </div>

            {/* Company card in sidebar */}
            {job.company && (
              <Link
                href={`/companies/${job.company.slug}`}
                className="marketplace-card marketplace-card-hover mt-4 flex items-center gap-3 rounded-[16px] p-4 outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
                title={t("viewCompany")}
              >
                <CompanyAvatar
                  name={job.company.display_name}
                  logoUrl={job.company.logo_url}
                  size="md"
                />
                <div className="min-w-0">
                  <p className="text-xs font-medium text-[var(--text-muted)]">
                    {t("postedBy")}
                  </p>
                  <div className="flex items-center gap-1.5">
                    <span className="truncate text-sm font-semibold text-[var(--text-primary)]">
                      {job.company.display_name}
                    </span>
                    {job.company.is_verified && (
                      <SealCheck
                        aria-hidden
                        weight="fill"
                        className="size-3.5 shrink-0 text-[var(--brand-teal)]"
                      />
                    )}
                  </div>
                </div>
                <Buildings
                  aria-hidden
                  weight="duotone"
                  className="ml-auto size-5 shrink-0 text-[var(--text-muted)]"
                />
              </Link>
            )}

            {/* Competition signal — public, non-personalized. Students see the
                bucketed, login-only version inside StudentJobIntelligencePanel
                instead (docs/API_CONTRACTS.md prefers the combined endpoint for
                signed-in job detail). */}
            {!isStudent && (
              <div className="mt-4">
                <CompetitionBadge jobId={job.id} />
              </div>
            )}


            {isStudent && (
              <TrackedItem
                surface="job_detail_recommended_cv"
                targetType="job"
                targetId={job.id}
                renderId={renderId}
                clickEvent="view"
                className="mt-4"
              >
                <StudentJobIntelligencePanel jobId={job.id} />
              </TrackedItem>
            )}
          </aside>
        </div>

        {/* Similar jobs (deterministic overlap; hidden when none). */}
        <SimilarJobsRail jobId={job.id} />

        {!isGuest && (
          <ApplyModal
            open={applyOpen}
            onClose={() => setApplyOpen(false)}
            jobId={job.id}
            jobTitle={job.title}
            cvLanguageRequired={job.cv_language_required}
          />
        )}
        </>
      ) : null}
    </div>
  );
}

function Meta({
  icon: Icon,
  label,
  children,
}: {
  icon: React.ElementType;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-[76px] items-start gap-2.5 border-b border-r border-[var(--border-default)] bg-[var(--surface-secondary)] px-4 py-3 last:border-r-0 sm:[&:nth-child(2n)]:border-r-0 xl:[&:nth-child(2n)]:border-r xl:[&:nth-child(3n)]:border-r-0">
      <Icon aria-hidden weight="duotone" className="mt-0.5 size-4 shrink-0 text-[var(--brand-primary)]" />
      <div className="min-w-0">
        <dt className="text-xs font-medium text-[var(--text-muted)]">{label}</dt>
        <dd className="text-sm font-semibold text-[var(--text-primary)]">{children}</dd>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-7 border-t border-[var(--border-default)]/70 pt-6">
      <h2 className="mb-3 text-lg font-extrabold tracking-tight text-[var(--text-primary)]">
        {title}
      </h2>
      <p className="whitespace-pre-wrap text-[0.95rem] leading-7 text-[var(--text-secondary)]">
        {children}
      </p>
    </section>
  );
}

function SkillBlock({ title, skills }: { title: string; skills: string[] }) {
  return (
    <section className="mt-6">
      <h2 className="mb-2 text-sm font-semibold text-[var(--text-primary)]">{title}</h2>
      <ul className="flex flex-wrap gap-1.5">
        {skills.map((s) => (
          <li
            key={s}
            className="rounded-full border border-[var(--border-default)] bg-[var(--surface-secondary)] px-3 py-1 text-xs font-medium text-[var(--text-secondary)]"
          >
            {s}
          </li>
        ))}
      </ul>
    </section>
  );
}
