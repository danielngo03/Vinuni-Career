"use client";

import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Buildings,
  ShieldWarning,
  SignIn,
  SealCheck,
  Sparkle,
  LightbulbFilament,
  ChartLineUp,
  UsersThree,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import {
  Button,
  Input,
  Select,
  StatusBadge,
  EmptyState,
  Skeleton,
  useToast,
} from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { SectionCard } from "@/components/settings/section-card";
import { CompanyLogoSection } from "@/components/organization/company-logo-section";
import { ApiError, organizationApi, type Organization } from "@/lib/api";
import { useApiErrorMessage, applyFieldErrors } from "@/lib/auth/use-api-error";
import { zodResolver } from "@/lib/validation/resolver";
import {
  orgProfileSchema,
  type OrgProfileValues,
  COMPANY_SIZES,
} from "@/lib/validation/organization";

export function CompanyProfileScreen() {
  const t = useTranslations("companyProfile");
  const tNav = useTranslations("nav");
  const tv = useTranslations("partnerReg.validation");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const toast = useToast();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();

  const [org, setOrg] = useState<Organization | null>(null);

  const query = useQuery({
    queryKey: ["org", "profile"],
    queryFn: () => organizationApi.get(),
    retry: false,
  });

  const qualityQuery = useQuery({
    queryKey: ["org", query.data?.id, "profile-quality"],
    queryFn: () => organizationApi.getProfileQuality(query.data!.id),
    enabled: Boolean(query.data?.id),
    retry: false,
  });
  const seatsQuery = useQuery({
    queryKey: ["org", query.data?.id, "recruiter-seats"],
    queryFn: () => organizationApi.getRecruiterSeats(query.data!.id),
    enabled: Boolean(query.data?.id),
    retry: false,
  });

  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<OrgProfileValues>({
    resolver: zodResolver(orgProfileSchema(tv)),
    defaultValues: {
      display_name: "",
      website_url: "",
      industry: "",
      company_size: "",
      headquarters_city: "",
      founded_year: "",
      description: "",
    },
  });

  useEffect(() => {
    if (query.data) {
      setOrg(query.data);
      reset({
        display_name: query.data.display_name ?? "",
        website_url: query.data.website_url ?? "",
        industry: query.data.industry ?? "",
        company_size: query.data.company_size ?? "",
        headquarters_city: query.data.headquarters_city ?? "",
        founded_year: query.data.founded_year ? String(query.data.founded_year) : "",
        description: query.data.description ?? "",
      });
    }
  }, [query.data, reset]);

  const save = useMutation({
    mutationFn: (values: OrgProfileValues) =>
      organizationApi.update({
        display_name: values.display_name,
        website_url: values.website_url || null,
        industry: values.industry || null,
        company_size: values.company_size || null,
        headquarters_city: values.headquarters_city || null,
        founded_year: values.founded_year ? Number(values.founded_year) : null,
        description: values.description || null,
        version: org?.version,
      }),
    onSuccess: (updated) => {
      setOrg(updated);
      qc.setQueryData(["org", "profile"], updated);
      toast.show({ tone: "success", title: t("savedToast") });
    },
    onError: (e) => {
      if (applyFieldErrors(e, setError)) return;
      const reason =
        e instanceof ApiError && typeof e.details?.reason === "string"
          ? e.details.reason
          : undefined;
      if (reason === "version_conflict" || (e instanceof ApiError && e.code === "CONFLICT")) {
        toast.show({ tone: "error", title: t("conflictToast"), description: t("conflictBody") });
        void query.refetch();
        return;
      }
      toast.show({ tone: "error", title: getMessage(e) });
    },
  });

  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    return (
      <>
        <PageHeader eyebrow={tNav("group.organization")} title={t("title")} description={t("subtitle")} />
        <EmptyState
          kind={err.isPermissionError ? "permission" : err.isAuthError ? "auth" : "error"}
          icon={err.isAuthError ? SignIn : ShieldWarning}
          title={
            err.isPermissionError
              ? tStates("permissionTitle")
              : err.isAuthError
                ? tStates("authTitle")
                : tStates("errorTitle")
          }
          description={
            err.isPermissionError
              ? t("permissionBody")
              : err.isAuthError
                ? tStates("authBody")
                : tStates("errorBody")
          }
          action={
            !err.isPermissionError && !err.isAuthError ? (
              <Button variant="secondary" onClick={() => query.refetch()}>
                {tc("retry")}
              </Button>
            ) : undefined
          }
        />
      </>
    );
  }

  return (
    <>
      <PageHeader
        eyebrow={tNav("group.organization")}
        title={t("title")}
        description={t("subtitle")}
        actions={
          org?.is_verified ? (
            <StatusBadge tone="verified">
              <SealCheck aria-hidden weight="fill" className="size-3.5" />
              {t("verified")}
            </StatusBadge>
          ) : undefined
        }
      />

      {org && (
        <CompanyLogoSection
          org={org}
          onUpdated={(updated) => {
            setOrg(updated);
            qc.setQueryData(["org", "profile"], updated);
          }}
          onStale={() => void query.refetch()}
        />
      )}

      {/* Backend profile-quality rubric + recruiter seats (real data, not a
          decorative/fabricated score). */}
      {org && (
        <div className="mb-6 grid gap-5 sm:grid-cols-2">
          <SectionCard
            title={t("profileQuality.title")}
            icon={ChartLineUp}
            iconGradient="icon-chip-primary"
          >
            {qualityQuery.isPending ? (
              <Skeleton className="h-16 w-full" />
            ) : qualityQuery.data ? (
              <div className="space-y-2.5">
                <p className="text-2xl font-black text-[var(--text-primary)]">
                  {t("profileQuality.score", { score: qualityQuery.data.score })}
                </p>
                {qualityQuery.data.missing.length > 0 && (
                  <div>
                    <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                      {t("profileQuality.missingTitle")}
                    </p>
                    <ul className="flex flex-wrap gap-1.5">
                      {qualityQuery.data.missing.map((check) => (
                        <li
                          key={check}
                          className="rounded-md bg-[var(--amber-100)] px-2 py-1 text-xs font-medium text-[var(--amber-800)]"
                        >
                          {t.has(`profileQuality.check.${check}`)
                            ? t(`profileQuality.check.${check}` as never)
                            : check}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ) : null}
          </SectionCard>

          <SectionCard title={t("seats.title")} icon={UsersThree} iconGradient="icon-chip-info">
            {seatsQuery.isPending ? (
              <Skeleton className="h-10 w-full" />
            ) : seatsQuery.data ? (
              <div>
                <p className="text-sm font-semibold text-[var(--text-primary)]">
                  {seatsQuery.data.unlimited
                    ? t("seats.unlimited", { used: seatsQuery.data.used })
                    : t("seats.usage", {
                        used: seatsQuery.data.used,
                        max: seatsQuery.data.limit ?? 0,
                      })}
                </p>
                {seatsQuery.data.at_capacity && (
                  <p className="mt-1 text-xs font-medium text-[var(--amber-700)]">
                    {t("seats.atCapacity")}
                  </p>
                )}
              </div>
            ) : null}
          </SectionCard>
        </div>
      )}

      {/* AI Company Profile Strength */}
      {org && (() => {
        const insights: string[] = [];
        if (!org.logo_url) insights.push(t("aiInsightNoLogo"));
        if (!org.description) insights.push(t("aiInsightNoDescription"));
        if (!org.website_url) insights.push(t("aiInsightNoWebsite"));
        if (!org.industry) insights.push(t("aiInsightNoIndustry"));
        if (insights.length === 0) insights.push(t("aiInsightComplete"));
        return (
          <div className={cn(
            "mb-6 rounded-2xl border p-4",
            "border-[var(--ai-accent)]/25 bg-gradient-to-br from-[var(--ai-accent-soft)] to-white/60 backdrop-blur-xl",
          )}>
            <p className="mb-3 flex items-center gap-2 text-sm font-bold text-[var(--text-primary)]">
              <span className="flex size-6 shrink-0 items-center justify-center rounded-lg icon-chip-info shadow-sm">
                <Sparkle aria-hidden weight="duotone" className="size-3.5 text-white" />
              </span>
              {t("aiInsightsTitle")}
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

      <SectionCard
        title={t("sectionTitle")}
        description={t("sectionIntro")}
        icon={Buildings}
        iconGradient="icon-chip-primary"
      >
        {query.isPending ? (
          <div className="space-y-4">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : (
          <form
            className="space-y-5"
            onSubmit={handleSubmit((v) => save.mutate(v))}
            noValidate
          >
            <Input
              label={t("companyName")}
              required
              error={errors.display_name?.message}
              {...register("display_name")}
            />
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
              <Input
                type="url"
                label={t("website")}
                placeholder="https://"
                error={errors.website_url?.message}
                {...register("website_url")}
              />
              <Input
                label={t("industry")}
                error={errors.industry?.message}
                {...register("industry")}
              />
              <Select
                label={t("companySize")}
                error={errors.company_size?.message}
                options={[
                  { value: "", label: t("selectPlaceholder") },
                  ...COMPANY_SIZES.map((s) => ({ value: s, label: s })),
                ]}
                {...register("company_size")}
              />
              <Input
                label={t("city")}
                error={errors.headquarters_city?.message}
                {...register("headquarters_city")}
              />
              <Input
                label={t("founded")}
                inputMode="numeric"
                placeholder="2015"
                error={errors.founded_year?.message}
                {...register("founded_year")}
              />
            </div>
            <div>
              <label
                htmlFor="org-desc"
                className="mb-1.5 block text-sm font-semibold text-[var(--text-primary)]"
              >
                {t("description")}
              </label>
              <textarea
                id="org-desc"
                rows={4}
                className="w-full rounded-xl border border-white/60 bg-white/80 backdrop-blur-sm px-3.5 py-2.5 text-sm text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--brand-primary)]/50 focus:bg-white/95 focus:ring-2 focus:ring-[var(--brand-primary)]/30"
                {...register("description")}
              />
            </div>

            <div className="flex items-center justify-between gap-3">
              <p className="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
                <Buildings aria-hidden weight="duotone" className="size-4" />
                {t("slugNote", { slug: org?.slug ?? "" })}
              </p>
              <Button
                type="submit"
                variant="primary"
                loading={isSubmitting || save.isPending}
              >
                {tc("save")}
              </Button>
            </div>
          </form>
        )}
      </SectionCard>
    </>
  );
}
