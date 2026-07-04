"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  Briefcase,
  Certificate,
  EnvelopeSimple,
  FileText,
  GlobeSimple,
  GraduationCap,
  Lightning,
  LightbulbFilament,
  Link as LinkIcon,
  LinkSimple,
  MapPin,
  PaperPlaneTilt,
  Phone,
  ShieldWarning,
  SignIn,
  Sparkle,
  Star,
  WarningCircle,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { Link } from "@/i18n/navigation";
import { Button, EmptyState, Skeleton, StatusBadge } from "@/components/ui";
import { formatMonthYear } from "@/lib/format";
import {
  ApiError,
  profileApi,
  type PublicStudentProfile,
  type EducationItem,
  type ExperienceItem,
  type SkillItem,
} from "@/lib/api";
import { CompanyAvatar } from "@/components/companies/company-avatar";
import { useAuthStore } from "@/stores/auth-store";
import { JobInviteModal } from "@/components/recruitment/job-invite-modal";

const WORK_TYPE_CHIP: Record<string, string> = {
  full_time: "bg-blue-100 text-blue-700",
  internship: "bg-violet-100 text-violet-700",
  part_time: "bg-amber-100 text-amber-700",
  contract: "bg-emerald-100 text-emerald-700",
};

function ProfileSkeleton() {
  return (
    <div className="space-y-5">
      <Skeleton className="h-44 w-full rounded-2xl" />
      <Skeleton className="h-32 w-full rounded-2xl" />
      <Skeleton className="h-64 w-full rounded-2xl" />
    </div>
  );
}

function SectionCard({
  title,
  icon: Icon,
  iconGradient,
  children,
}: {
  title: string;
  icon?: React.ElementType;
  iconGradient?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-[var(--border-default)] bg-white p-5 ">
      <h2 className="mb-4 flex items-center gap-2.5 text-sm font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        {Icon && iconGradient && (
          <span className={cn("flex size-7 shrink-0 items-center justify-center rounded-lg shadow-sm", iconGradient)}>
            <Icon aria-hidden weight="duotone" className="size-4 text-white" />
          </span>
        )}
        {title}
      </h2>
      {children}
    </section>
  );
}

function EducationCard({ item, locale }: { item: EducationItem; locale: string }) {
  const from = formatMonthYear(item.start_date, locale);
  const to = item.is_current ? "Present" : formatMonthYear(item.end_date, locale);
  const range = from || to ? `${from}${from && to ? " – " : ""}${to}` : null;

  return (
    <div className="flex gap-3">
      <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg icon-chip-primary shadow-sm">
        <GraduationCap aria-hidden weight="duotone" className="size-4 text-white" />
      </span>
      <div className="min-w-0">
        <p className="font-semibold text-[var(--text-primary)]">
          {item.institution ?? "—"}
        </p>
        {item.degree && (
          <p className="text-sm text-[var(--text-secondary)]">
            {item.degree}
            {item.field_of_study ? ` · ${item.field_of_study}` : ""}
          </p>
        )}
        {range && <p className="mt-0.5 text-xs text-[var(--text-muted)]">{range}</p>}
        {item.gpa != null && (
          <p className="mt-0.5 flex items-center gap-1 text-xs text-[var(--text-muted)]">
            <Star aria-hidden weight="fill" className="size-3" />
            GPA {item.gpa.toFixed(1)}
          </p>
        )}
      </div>
    </div>
  );
}

function ExperienceCard({ item, locale }: { item: ExperienceItem; locale: string }) {
  const from = formatMonthYear(item.start_date, locale);
  const to = item.is_current ? "Present" : formatMonthYear(item.end_date, locale);
  const range = from || to ? `${from}${from && to ? " – " : ""}${to}` : null;

  return (
    <div className="flex gap-3">
      <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg icon-chip-success shadow-sm">
        <Briefcase aria-hidden weight="duotone" className="size-4 text-white" />
      </span>
      <div className="min-w-0">
        <p className="font-semibold text-[var(--text-primary)]">{item.title ?? "—"}</p>
        {item.company_name && (
          <p className="text-sm text-[var(--text-secondary)]">
            {item.company_name}
            {item.location ? ` · ${item.location}` : ""}
          </p>
        )}
        {range && <p className="mt-0.5 text-xs text-[var(--text-muted)]">{range}</p>}
        {item.description && (
          <p className="mt-1.5 text-sm leading-relaxed text-[var(--text-secondary)] line-clamp-3">
            {item.description}
          </p>
        )}
        {item.skills_used.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {item.skills_used.map((s) => (
              <span
                key={s}
                className="rounded-full border border-[var(--border-default)] bg-white/60 px-2 py-0.5 text-[11px] font-medium text-[var(--text-secondary)]"
              >
                {s}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function SkillChip({ item }: { item: SkillItem }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-[var(--border-default)] bg-white px-3 py-1 text-sm font-medium text-[var(--text-primary)]">
      <Certificate aria-hidden weight="duotone" className="size-3.5 text-[var(--brand-primary)]" />
      {item.name}
      {item.proficiency != null && (
        <span className="ml-1 text-xs text-[var(--text-muted)]">
          {"★".repeat(Math.round(item.proficiency / 25))}
        </span>
      )}
    </span>
  );
}

function ProfileHeader({ profile }: { profile: PublicStudentProfile }) {
  const t = useTranslations("talentPool");
  const location = [profile.location_city, profile.location_country]
    .filter(Boolean)
    .join(", ");

  return (
    <div className="rounded-2xl border border-[var(--border-default)] bg-white p-6 ">
      <div className="flex flex-wrap items-start gap-5">
        {/* Avatar */}
        <div className="shrink-0">
          {profile.avatar_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={profile.avatar_url}
              alt=""
              className="h-20 w-20 rounded-full object-cover ring-2 ring-white/60"
            />
          ) : (
            <CompanyAvatar name={profile.display_name} size="lg" />
          )}
        </div>

        {/* Identity */}
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-bold text-[var(--text-primary)]">
            {profile.display_name}
          </h1>
          {profile.headline && (
            <p className="mt-0.5 text-base text-[var(--text-secondary)]">
              {profile.headline}
            </p>
          )}

          <div className="mt-3 flex flex-wrap items-center gap-3 text-sm text-[var(--text-muted)]">
            {profile.major && (
              <span className="flex items-center gap-1.5">
                <GraduationCap aria-hidden weight="duotone" className="size-4" />
                {profile.major}
                {profile.graduation_year ? ` · ${profile.graduation_year}` : ""}
                {profile.degree_level_label ? ` · ${profile.degree_level_label}` : ""}
              </span>
            )}
            {location && (
              <span className="flex items-center gap-1.5">
                <MapPin aria-hidden weight="duotone" className="size-4" />
                {location}
              </span>
            )}
          </div>

          {profile.is_open_to_work && profile.open_to_work_type_labels.length > 0 && (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <StatusBadge tone="active">{t("openToWork")}</StatusBadge>
              {profile.open_to_work_type_labels.map((label, i) => {
                const type = profile.open_to_work_types[i] ?? "";
                return (
                  <span
                    key={type}
                    className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                      WORK_TYPE_CHIP[type] ?? "bg-slate-100 text-slate-600"
                    }`}
                  >
                    <Briefcase aria-hidden weight="duotone" className="size-3" />
                    {label}
                  </span>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Contact info if exposed */}
      {(profile.email || profile.phone) && (
        <div className="mt-4 flex flex-wrap gap-4 border-t border-[var(--border-default)] pt-4">
          {profile.email && (
            <a
              href={`mailto:${profile.email}`}
              className="flex items-center gap-1.5 text-sm text-[var(--brand-primary)] hover:underline"
            >
              <EnvelopeSimple aria-hidden weight="duotone" className="size-4" />
              {profile.email}
            </a>
          )}
          {profile.phone && (
            <a
              href={`tel:${profile.phone}`}
              className="flex items-center gap-1.5 text-sm text-[var(--brand-primary)] hover:underline"
            >
              <Phone aria-hidden weight="duotone" className="size-4" />
              {profile.phone}
            </a>
          )}
        </div>
      )}
    </div>
  );
}

export function TalentProfileScreen({ profileId }: { profileId: string }) {
  const t = useTranslations("talentPool");
  const tInvite = useTranslations("jobInvitations");
  const tStates = useTranslations("states");
  const locale = useLocale();
  const isPartner = useAuthStore((s) => s.user?.persona === "partner");

  const [inviteOpen, setInviteOpen] = useState(false);

  const query = useQuery({
    queryKey: ["talent-profile", profileId],
    queryFn: () => profileApi.getPublic(profileId),
    retry: false,
  });

  return (
    <>
      {/* Back nav */}
      <div className="mb-5">
        <Link
          href="/partner/talent-pool"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-[var(--text-secondary)] hover:text-[var(--brand-primary)] transition-colors"
        >
          <ArrowLeft aria-hidden weight="bold" className="size-4" />
          {t("backToList")}
        </Link>
      </div>

      {query.isPending ? (
        <ProfileSkeleton />
      ) : query.isError ? (
        query.error instanceof ApiError && query.error.isAuthError ? (
          <EmptyState
            kind="auth"
            icon={SignIn}
            title={tStates("authTitle")}
            description={tStates("authBody")}
          />
        ) : query.error instanceof ApiError && query.error.isPermissionError ? (
          <EmptyState
            kind="permission"
            icon={ShieldWarning}
            title={t("profileNotVisible")}
            description={t("profileNotVisibleBody")}
          />
        ) : query.error instanceof ApiError && query.error.isNotFound ? (
          <EmptyState
            kind="empty"
            icon={WarningCircle}
            title={t("profileNotVisible")}
            description={t("profileNotVisibleBody")}
          />
        ) : (
          <EmptyState
            kind="error"
            icon={WarningCircle}
            title={tStates("errorTitle")}
            description={tStates("errorBody")}
            action={
              <Button variant="secondary" onClick={() => query.refetch()}>
                Retry
              </Button>
            }
          />
        )
      ) : (
        <div className="space-y-5">
          <ProfileHeader profile={query.data} />

          {/* Partner-only: invite CTA + AI candidate snapshot */}
          {isPartner && (
            <>
              <div className="flex justify-end">
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => setInviteOpen(true)}
                  className="flex items-center gap-1.5"
                >
                  <PaperPlaneTilt aria-hidden weight="duotone" className="size-4" />
                  {tInvite("inviteLabel")}
                </Button>
              </div>

              {/* AI Candidate Snapshot */}
              {(() => {
                const p = query.data;
                const insights: string[] = [];
                if (p.is_open_to_work && p.open_to_work_type_labels.length > 0) {
                  insights.push(t("aiInsightOpenWork", { types: p.open_to_work_type_labels.join(", ") }));
                }
                if (p.skills.length > 0) {
                  insights.push(t("aiInsightSkills", { count: p.skills.length }));
                }
                if (p.experience.length > 0) {
                  insights.push(t("aiInsightExperience", { count: p.experience.length }));
                }
                const currentYear = new Date().getFullYear();
                if (p.graduation_year && p.graduation_year >= currentYear) {
                  insights.push(t("aiInsightRecentGrad", { year: p.graduation_year }));
                }
                if (insights.length === 0) return null;
                return (
                  <div className={cn(
                    "rounded-2xl border p-4",
                    "border-[var(--ai-accent)]/25 bg-gradient-to-br from-[var(--ai-accent-soft)] to-white/60 ",
                  )}>
                    <p className="mb-3 flex items-center gap-2 text-sm font-bold text-[var(--text-primary)]">
                      <span className="flex size-6 shrink-0 items-center justify-center rounded-lg icon-chip-info shadow-sm">
                        <Sparkle aria-hidden weight="duotone" className="size-3.5 text-white" />
                      </span>
                      {t("aiCandidateTitle")}
                    </p>
                    <ul className="space-y-1.5">
                      {insights.map((s, i) => (
                        <li key={i} className="flex items-start gap-2 text-sm text-[var(--text-secondary)]">
                          <LightbulbFilament aria-hidden weight="duotone" className="mt-0.5 size-4 shrink-0 text-[var(--ai-accent)]" />
                          {s}
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })()}
            </>
          )}

          {/* Summary */}
          {query.data.summary && (
            <SectionCard
              title={t("sectionSummary")}
              icon={FileText}
              iconGradient="icon-chip-success"
            >
              <p className="text-sm leading-relaxed text-[var(--text-secondary)]">
                {query.data.summary}
              </p>
            </SectionCard>
          )}

          {/* Experience */}
          {query.data.experience.length > 0 && (
            <SectionCard
              title={t("sectionExperience")}
              icon={Briefcase}
              iconGradient="icon-chip-primary"
            >
              <div className="space-y-4">
                {query.data.experience.map((item) => (
                  <ExperienceCard key={item.id} item={item} locale={locale} />
                ))}
              </div>
            </SectionCard>
          )}

          {/* Education */}
          {query.data.education.length > 0 && (
            <SectionCard
              title={t("sectionEducation")}
              icon={GraduationCap}
              iconGradient="icon-chip-primary"
            >
              <div className="space-y-4">
                {query.data.education.map((item) => (
                  <EducationCard key={item.id} item={item} locale={locale} />
                ))}
              </div>
            </SectionCard>
          )}

          {/* Skills */}
          {query.data.skills.length > 0 && (
            <SectionCard
              title={t("sectionSkills")}
              icon={Lightning}
              iconGradient="icon-chip-warning"
            >
              <div className="flex flex-wrap gap-2">
                {query.data.skills.map((item) => (
                  <SkillChip key={item.id} item={item} />
                ))}
              </div>
            </SectionCard>
          )}

          {/* Links */}
          {query.data.links.length > 0 && (
            <SectionCard
              title={t("sectionLinks")}
              icon={LinkSimple}
              iconGradient="icon-chip-success"
            >
              <ul className="space-y-2">
                {query.data.links.map((item) => (
                  <li key={item.id}>
                    <a
                      href={item.url ?? "#"}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 text-sm text-[var(--brand-primary)] hover:underline"
                    >
                      {item.url?.startsWith("http") ? (
                        <GlobeSimple aria-hidden weight="duotone" className="size-4" />
                      ) : (
                        <LinkIcon aria-hidden weight="duotone" className="size-4" />
                      )}
                      {item.label ?? item.url}
                    </a>
                  </li>
                ))}
              </ul>
            </SectionCard>
          )}
        </div>
      )}

      {isPartner && query.data && (
        <JobInviteModal
          open={inviteOpen}
          onClose={() => setInviteOpen(false)}
          studentId={query.data.user_id}
          studentName={query.data.display_name}
        />
      )}
    </>
  );
}
