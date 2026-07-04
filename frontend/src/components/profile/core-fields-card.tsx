"use client";

import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslations } from "next-intl";
import { useMutation } from "@tanstack/react-query";
import { IdentificationCard, Sparkle, Warning } from "@phosphor-icons/react";
import { Button, Input, Select, Textarea, useToast } from "@/components/ui";
import { SectionCard } from "@/components/settings/section-card";
import { zodResolver } from "@/lib/validation/resolver";
import {
  coreProfileSchema,
  type CoreProfileValues,
} from "@/lib/validation/profile";
import { useProfileLabels } from "@/lib/profile/labels";
import {
  DEGREE_LEVELS,
  profileApi,
  type StudentProfile,
  type UpdateProfileBody,
} from "@/lib/api";
import { applyFieldErrors } from "@/lib/auth/use-api-error";
import { useProfileMutations } from "./use-profile-mutations";

function nullable(value: string | undefined): string | null {
  const v = (value ?? "").trim();
  return v === "" ? null : v;
}

function toDefaults(p: StudentProfile): CoreProfileValues {
  return {
    headline: p.headline ?? "",
    summary: p.summary ?? "",
    phone: p.phone ?? "",
    location_city: p.location_city ?? "",
    location_country: p.location_country ?? "",
    major: p.major ?? "",
    degree_level: p.degree_level ?? "",
    graduation_year: p.graduation_year ? String(p.graduation_year) : "",
  };
}

export function CoreFieldsCard({ profile }: { profile: StudentProfile }) {
  const t = useTranslations("profile.core");
  const tv = useTranslations("profile.validation");
  const tc = useTranslations("common");
  const labels = useProfileLabels();
  const toast = useToast();
  const { setProfile, handleError, notifySaved } = useProfileMutations();

  const [summaryAiLoading, setSummaryAiLoading] = useState(false);
  const [summaryAiFallback, setSummaryAiFallback] = useState(false);
  const [summaryAiApplied, setSummaryAiApplied] = useState(false);

  const {
    register,
    handleSubmit,
    reset,
    setError,
    setValue,
    formState: { errors, isDirty },
  } = useForm<CoreProfileValues>({
    resolver: zodResolver(coreProfileSchema(tv)),
    defaultValues: toDefaults(profile),
  });

  async function generateSummaryDraft() {
    setSummaryAiLoading(true);
    setSummaryAiFallback(false);
    setSummaryAiApplied(false);
    try {
      const result = await profileApi.getAiSummaryDraft();
      setValue("summary", result.draft, { shouldDirty: true });
      setSummaryAiFallback(result.is_fallback);
      setSummaryAiApplied(true);
    } catch {
      toast.show({ tone: "error", title: t("summaryAiError") });
    } finally {
      setSummaryAiLoading(false);
    }
  }

  // Keep the form in sync when the profile is refetched (e.g. after reload).
  useEffect(() => {
    reset(toDefaults(profile));
  }, [profile, reset]);

  const years = useMemo(() => {
    const now = new Date().getFullYear();
    const list: number[] = [];
    for (let y = now + 8; y >= now - 12; y--) list.push(y);
    return list;
  }, []);

  const save = useMutation({
    mutationFn: (values: CoreProfileValues) => {
      const gradStr = (values.graduation_year ?? "").trim();
      const body: UpdateProfileBody = {
        headline: nullable(values.headline),
        summary: nullable(values.summary),
        phone: nullable(values.phone),
        location_city: nullable(values.location_city),
        location_country: nullable(values.location_country),
        major: nullable(values.major),
        degree_level: nullable(values.degree_level),
        graduation_year: gradStr === "" ? null : Number(gradStr),
        expected_version: profile.version,
      };
      return profileApi.updateMine(body);
    },
    onSuccess: (updated) => {
      setProfile(updated);
      reset(toDefaults(updated));
      notifySaved();
    },
    onError: (error) => {
      if (!applyFieldErrors(error, setError)) handleError(error);
    },
  });

  return (
    <SectionCard
      title={t("title")}
      description={t("intro")}
      icon={IdentificationCard}
      iconGradient="icon-chip-primary"
    >
      <form
        noValidate
        onSubmit={handleSubmit((v) => save.mutate(v))}
        className="space-y-5"
      >
        <Input
          label={t("headline")}
          help={t("headlineHelp")}
          error={errors.headline?.message}
          {...register("headline")}
        />
        <div className="space-y-1.5">
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm font-medium text-[var(--text-primary)]">
              {t("summary")}
            </span>
            <button
              type="button"
              onClick={generateSummaryDraft}
              disabled={summaryAiLoading}
              className="inline-flex items-center gap-1.5 rounded-full border border-[var(--ai-accent)]/40 bg-[var(--ai-accent-soft)] px-3 py-1 text-xs font-semibold text-[var(--ai-accent)] outline-none transition-colors hover:bg-[var(--ai-accent)]/15 focus-visible:ring-2 focus-visible:ring-[var(--ai-accent)]/40 disabled:opacity-60"
            >
              {summaryAiLoading ? (
                <span className="size-3.5 animate-spin rounded-full border-2 border-[var(--ai-accent)]/30 border-t-[var(--ai-accent)]" />
              ) : (
                <Sparkle aria-hidden weight="fill" className="size-3.5" />
              )}
              {t("summaryAiDraft")}
            </button>
          </div>
          <Textarea
            help={t("summaryHelp")}
            rows={5}
            error={errors.summary?.message}
            {...register("summary")}
          />
          {summaryAiApplied && (
            <p className="flex items-start gap-1.5 text-xs text-[var(--text-muted)]">
              <Warning aria-hidden weight="fill" className="mt-0.5 size-3.5 shrink-0 text-[var(--amber-500)]" />
              {summaryAiFallback ? t("summaryAiDisclaimerFallback") : t("summaryAiDisclaimer")}
            </p>
          )}
        </div>

        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          <Input
            label={t("phone")}
            type="tel"
            error={errors.phone?.message}
            {...register("phone")}
          />
          <Input
            label={t("locationCity")}
            error={errors.location_city?.message}
            {...register("location_city")}
          />
          <Input
            label={t("locationCountry")}
            error={errors.location_country?.message}
            {...register("location_country")}
          />
          <Input
            label={t("major")}
            error={errors.major?.message}
            {...register("major")}
          />
          <Select
            label={t("degreeLevel")}
            error={errors.degree_level?.message}
            options={[
              { value: "", label: t("notSet") },
              ...DEGREE_LEVELS.map((d) => ({
                value: d,
                label: labels.degree(d),
              })),
            ]}
            {...register("degree_level")}
          />
          <Select
            label={t("graduationYear")}
            error={errors.graduation_year?.message}
            options={[
              { value: "", label: t("notSet") },
              ...years.map((y) => ({ value: String(y), label: String(y) })),
            ]}
            {...register("graduation_year")}
          />
        </div>

        <div className="flex justify-end">
          <Button
            type="submit"
            variant="primary"
            loading={save.isPending}
            disabled={!isDirty || save.isPending}
          >
            {save.isPending ? tc("saving") : tc("save")}
          </Button>
        </div>
      </form>
    </SectionCard>
  );
}
