"use client";

import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { SignIn, WarningCircle } from "@phosphor-icons/react";
import { Button, EmptyState, Skeleton } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { ApiError, profileApi } from "@/lib/api";
import { ProfileHeroCard } from "./profile-hero-card";
import { CoreFieldsCard } from "./core-fields-card";
import { PrivacyCard } from "./privacy-card";
import { EducationSection } from "./education-section";
import { ExperienceSection } from "./experience-section";
import { SkillsSection } from "./skills-section";
import { LinksSection } from "./links-section";
import { PROFILE_QUERY_KEY } from "./use-profile-mutations";

export function ProfileScreen() {
  const t = useTranslations("profile");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");

  const query = useQuery({
    queryKey: PROFILE_QUERY_KEY,
    queryFn: () => profileApi.getMine(),
    retry: false,
  });

  if (
    query.isError &&
    query.error instanceof ApiError &&
    query.error.isAuthError
  ) {
    return (
      <>
        <PageHeader title={t("title")} description={t("subtitle")} />
        <EmptyState
          kind="auth"
          icon={SignIn}
          title={tStates("authTitle")}
          description={tStates("authBody")}
        />
      </>
    );
  }

  return (
    <>
      <PageHeader title={t("title")} description={t("subtitle")} />

      {query.isPending ? (
        <div className="space-y-6">
          <Skeleton className="h-32 w-full rounded-2xl" />
          <Skeleton className="h-80 w-full rounded-2xl" />
          <Skeleton className="h-64 w-full rounded-2xl" />
        </div>
      ) : query.isError ? (
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
      ) : (
        <div className="space-y-6">
          <ProfileHeroCard profile={query.data} />
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            <div className="space-y-6 lg:col-span-2">
              <CoreFieldsCard profile={query.data} />
              <EducationSection items={query.data.education} />
              <ExperienceSection items={query.data.experience} />
              <SkillsSection items={query.data.skills} />
              <LinksSection items={query.data.links} />
            </div>
            <aside className="space-y-6 lg:col-span-1">
              <div className="lg:sticky lg:top-6">
                <PrivacyCard profile={query.data} />
              </div>
            </aside>
          </div>
        </div>
      )}
    </>
  );
}
