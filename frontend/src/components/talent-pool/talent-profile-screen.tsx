"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  Briefcase,
  EnvelopeSimple,
  MapPin,
  PaperPlaneTilt,
  Phone,
  ShieldWarning,
  SignIn,
  WarningCircle,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { Button, EmptyState, Skeleton, StatusBadge } from "@/components/ui";
import { ApiError, profileApi, type PublicStudentProfile } from "@/lib/api";
import { CompanyAvatar } from "@/components/companies/company-avatar";
import { useAuthStore } from "@/stores/auth-store";
import { JobInviteModal } from "@/components/recruitment/job-invite-modal";

function ProfileSkeleton() {
  return (
    <div className="space-y-5">
      <Skeleton className="h-48 w-full rounded-2xl" />
      <Skeleton className="h-12 w-40 rounded-xl" />
    </div>
  );
}

/**
 * Recruiter-facing identity card. Career content (experience, education,
 * skills, summary) is no longer on the profile — recruiters review the
 * student's CVs. This surface shows identity, location, open-to-work, and
 * privacy-gated contact only.
 */
function ProfileHeader({ profile }: { profile: PublicStudentProfile }) {
  const t = useTranslations("talentPool");
  const location = [profile.location_city, profile.location_country]
    .filter(Boolean)
    .join(", ");

  return (
    <div className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-6 shadow-[var(--shadow-sm)]">
      <div className="flex flex-wrap items-start gap-5">
        {/* Avatar */}
        <div className="shrink-0">
          {profile.avatar_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={profile.avatar_url}
              alt=""
              className="h-20 w-20 rounded-full object-cover ring-2 ring-[var(--border-default)]"
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

          {location && (
            <p className="mt-2 flex items-center gap-1.5 text-sm text-[var(--text-secondary)]">
              <MapPin aria-hidden weight="duotone" className="size-4 shrink-0" />
              {location}
            </p>
          )}

          {profile.is_open_to_work && (
            <div className="mt-3">
              <StatusBadge tone="active">
                <Briefcase aria-hidden weight="duotone" className="mr-1 inline size-3.5" />
                {t("openToWork")}
              </StatusBadge>
            </div>
          )}
        </div>
      </div>

      {/* Contact info if exposed */}
      {(profile.email || profile.phone) && (
        <div className="mt-5 flex flex-wrap gap-4 border-t border-[var(--border-default)] pt-4">
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
  const tc = useTranslations("common");
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
          className="inline-flex items-center gap-1.5 text-sm font-medium text-[var(--text-secondary)] transition-colors hover:text-[var(--brand-primary)]"
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
                {tc("retry")}
              </Button>
            }
          />
        )
      ) : (
        <div className="space-y-5">
          <ProfileHeader profile={query.data} />

          {/* Recruiters review CVs for career content. */}
          <p className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-subtle)] px-4 py-3 text-sm text-[var(--text-secondary)]">
            {t("cvReviewHint")}
          </p>

          {/* Partner-only: invite CTA */}
          {isPartner && (
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
