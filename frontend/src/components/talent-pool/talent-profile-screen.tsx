"use client";

import * as React from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Briefcase, Mail, MapPin, Phone, Send, FileText } from "lucide-react";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Card, CardContent, EmptyState, StatusChip } from "@/components/kit";
import { ApiError, profileApi, type PublicStudentProfile } from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";
import { JobInviteModal } from "@/components/recruitment/job-invite-modal";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase();
  return (parts[0]![0]! + parts[parts.length - 1]![0]!).toUpperCase();
}

function ProfileSkeleton() {
  return (
    <div className="space-y-4">
      <div className="h-44 animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
      <div className="h-16 animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
    </div>
  );
}

/**
 * Recruiter-facing identity card. Career content (experience, education, skills,
 * summary) is not on the profile — recruiters review the student's CVs via the
 * reason-gated outreach/reveal flow. This surface shows identity, location,
 * open-to-work, and privacy-gated contact only.
 */
function ProfileHeaderCard({ profile }: { profile: PublicStudentProfile }) {
  const t = useTranslations("talentPool");
  const location = [profile.location_city, profile.location_country].filter(Boolean).join(", ");

  return (
    <Card>
      <CardContent className="pt-5">
        <div className="flex flex-wrap items-start gap-4">
          <Avatar size="lg" className="size-16 ring-1 ring-border">
            {profile.avatar_url && <AvatarImage src={profile.avatar_url} alt="" />}
            <AvatarFallback className="bg-[var(--viz-indigo-soft)] text-base font-semibold text-[var(--viz-indigo)]">
              {initials(profile.display_name)}
            </AvatarFallback>
          </Avatar>

          <div className="min-w-0 flex-1">
            <h1 className="type-h2 text-foreground">{profile.display_name}</h1>
            {location && (
              <p className="mt-1.5 flex items-center gap-1.5 type-small text-muted-foreground">
                <MapPin aria-hidden className="size-4 shrink-0" strokeWidth={1.8} />
                {location}
              </p>
            )}
            {profile.is_open_to_work && (
              <div className="mt-2.5">
                <StatusChip tone="success" dot>
                  <Briefcase aria-hidden className="size-3.5" strokeWidth={1.9} />
                  {t("openToWork")}
                </StatusChip>
              </div>
            )}
          </div>
        </div>

        {/* Contact — rendered only when the student's per-field gate exposes it. */}
        {(profile.email || profile.phone) && (
          <div className="mt-4 flex flex-wrap gap-4 border-t border-border pt-4">
            {profile.email && (
              <a
                href={`mailto:${profile.email}`}
                className="flex items-center gap-1.5 type-small font-medium text-[var(--brand-primary)] hover:underline"
              >
                <Mail aria-hidden className="size-4" strokeWidth={1.8} />
                {profile.email}
              </a>
            )}
            {profile.phone && (
              <a
                href={`tel:${profile.phone}`}
                className="flex items-center gap-1.5 type-small font-medium text-[var(--brand-primary)] hover:underline"
              >
                <Phone aria-hidden className="size-4" strokeWidth={1.8} />
                {profile.phone}
              </a>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function TalentProfileScreen({ profileId }: { profileId: string }) {
  const t = useTranslations("talentPool");
  const tInvite = useTranslations("jobInvitations");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const isPartner = useAuthStore((s) => s.user?.persona === "partner");

  const [inviteOpen, setInviteOpen] = React.useState(false);

  const query = useQuery({
    queryKey: ["talent-profile", profileId],
    queryFn: () => profileApi.getPublic(profileId),
    retry: false,
  });

  return (
    <>
      <div className="mb-4">
        <Link
          href="/partner/talent-pool"
          className="inline-flex items-center gap-1.5 type-small font-medium text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:text-foreground"
        >
          <ArrowLeft aria-hidden className="size-4" strokeWidth={2} />
          {t("backToList")}
        </Link>
      </div>

      {query.isPending ? (
        <ProfileSkeleton />
      ) : query.isError ? (
        query.error instanceof ApiError && query.error.isAuthError ? (
          <EmptyState kind="auth" title={tStates("authTitle")} description={tStates("authBody")} />
        ) : query.error instanceof ApiError && (query.error.isPermissionError || query.error.isNotFound) ? (
          <EmptyState
            kind={query.error.isPermissionError ? "permission" : "empty"}
            title={t("profileNotVisible")}
            description={t("profileNotVisibleBody")}
          />
        ) : (
          <EmptyState
            kind="error"
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
        <div className="space-y-4">
          <ProfileHeaderCard profile={query.data} />

          {/* CV review + outreach: career detail lives in the student's CVs. */}
          <Card>
            <CardContent className="flex flex-col gap-3 pt-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-start gap-3">
                <span
                  className="flex size-8 shrink-0 items-center justify-center rounded-lg"
                  style={{ background: "var(--content-info-soft)" }}
                >
                  <FileText className="size-4" strokeWidth={1.9} style={{ color: "var(--content-info)" }} />
                </span>
                <p className="type-small text-muted-foreground">{t("cvReviewHint")}</p>
              </div>
              {isPartner && (
                <Button variant="primary" size="sm" onClick={() => setInviteOpen(true)} className="shrink-0">
                  <Send aria-hidden className="size-4" strokeWidth={1.9} />
                  {tInvite("inviteLabel")}
                </Button>
              )}
            </CardContent>
          </Card>
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
