"use client";

import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { SignIn, WarningCircle } from "@phosphor-icons/react";
import { Button, EmptyState, Skeleton } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { ApiError, profileApi } from "@/lib/api";
import { ProfileHeroCard } from "./profile-hero-card";
import { ContactInfoCard } from "./contact-info-card";
import { PrivacyCard } from "./privacy-card";
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
        <div className="mx-auto max-w-3xl space-y-6">
          <Skeleton className="h-40 w-full rounded-2xl" />
          <Skeleton className="h-56 w-full rounded-2xl" />
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
        <div className="mx-auto max-w-3xl space-y-6">
          <p className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-subtle)] px-4 py-3 text-sm text-[var(--text-secondary)]">
            {t("cvHint")}
          </p>
          <ProfileHeroCard profile={query.data} />
          <ContactInfoCard profile={query.data} />
          <PrivacyCard profile={query.data} />
        </div>
      )}
    </>
  );
}
