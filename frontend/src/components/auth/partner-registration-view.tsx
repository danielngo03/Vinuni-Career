"use client";

import { useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslations } from "next-intl";
import { Buildings, CheckCircle } from "@phosphor-icons/react";
import { Button, Input, Select } from "@/components/ui";
import { Link } from "@/i18n/navigation";
import { ApiError, partnerApi } from "@/lib/api";
import { zodResolver } from "@/lib/validation/resolver";
import {
  partnerRegistrationSchema,
  type PartnerRegistrationValues,
} from "@/lib/validation/partner";
import { COMPANY_SIZES } from "@/lib/validation/organization";
import { useApiErrorMessage, applyFieldErrors } from "@/lib/auth/use-api-error";
import { FormBanner } from "./form-banner";

function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `pk-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function PartnerRegistrationView() {
  const t = useTranslations("partnerReg");
  const tv = useTranslations("partnerReg.validation");
  const getMessage = useApiErrorMessage();

  const idempotencyKey = useRef<string>(newIdempotencyKey());
  const [formError, setFormError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<PartnerRegistrationValues>({
    resolver: zodResolver(partnerRegistrationSchema(tv)),
    defaultValues: {
      company_name: "",
      tax_code: "",
      company_website: "",
      company_size: "",
      industry: "",
      contact_name: "",
      contact_title: "",
      email: "",
      phone: "",
      description: "",
    },
  });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      await partnerApi.register(
        {
          company_name: values.company_name,
          tax_code: values.tax_code || null,
          company_website: values.company_website || null,
          company_size: values.company_size || null,
          industry: values.industry || null,
          contact_name: values.contact_name,
          contact_title: values.contact_title || null,
          email: values.email,
          phone: values.phone || null,
          description: values.description || null,
        },
        idempotencyKey.current,
      );
      setDone(values.email);
    } catch (err) {
      if (applyFieldErrors(err, setError)) return;
      if (err instanceof ApiError && err.code === "CONFLICT") {
        setFormError(t("duplicateError"));
        return;
      }
      setFormError(getMessage(err));
    }
  });

  if (done) {
    return (
      <Shell title={t("successTitle")}>
        <div className="space-y-5 text-center">
          <span className="mx-auto flex size-14 items-center justify-center rounded-2xl icon-chip-success shadow-[0_4px_16px_rgba(20,184,166,0.35)]">
            <CheckCircle
              aria-hidden
              weight="duotone"
              className="size-7 text-white"
            />
          </span>
          <p className="text-sm text-[var(--text-secondary)]">
            {t("successBody", { email: done })}
          </p>
          <ol className="mx-auto max-w-md space-y-2 text-left text-sm text-[var(--text-secondary)]">
            <li>1. {t("step1")}</li>
            <li>2. {t("step2")}</li>
            <li>3. {t("step3")}</li>
          </ol>
          <Link
            href="/"
            className="inline-flex h-10 items-center justify-center rounded-lg border-2 border-[var(--brand-primary)] px-5 text-sm font-semibold text-[var(--brand-primary)] outline-none transition-colors hover:bg-[var(--blue-50)]"
          >
            {t("backHome")}
          </Link>
        </div>
      </Shell>
    );
  }

  return (
    <Shell title={t("title")} subtitle={t("subtitle")}>
      <form className="space-y-5" onSubmit={onSubmit} noValidate>
        {formError && <FormBanner>{formError}</FormBanner>}

        <fieldset className="space-y-4">
          <legend className="text-sm font-bold text-[var(--text-primary)]">
            {t("companySection")}
          </legend>
          <Input
            label={t("companyName")}
            required
            error={errors.company_name?.message}
            {...register("company_name")}
          />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Input
              label={t("taxCode")}
              help={t("taxCodeHelp")}
              error={errors.tax_code?.message}
              {...register("tax_code")}
            />
            <Input
              type="url"
              label={t("website")}
              placeholder="https://"
              error={errors.company_website?.message}
              {...register("company_website")}
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
              label={t("industry")}
              error={errors.industry?.message}
              {...register("industry")}
            />
          </div>
          <div>
            <label
              htmlFor="partner-desc"
              className="mb-1.5 block text-sm font-semibold text-[var(--text-primary)]"
            >
              {t("description")}
            </label>
            <textarea
              id="partner-desc"
              rows={3}
              className="w-full rounded-xl border border-[var(--border-default)] bg-white px-3.5 py-2.5 text-sm font-medium text-[var(--text-primary)] outline-none transition-colors placeholder:text-[var(--text-muted)] focus:border-[var(--brand-primary)]/50 focus:bg-white focus:ring-2 focus:ring-[var(--brand-primary)]/30"
              {...register("description")}
            />
          </div>
        </fieldset>

        <fieldset className="space-y-4">
          <legend className="text-sm font-bold text-[var(--text-primary)]">
            {t("contactSection")}
          </legend>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Input
              label={t("contactName")}
              required
              autoComplete="name"
              error={errors.contact_name?.message}
              {...register("contact_name")}
            />
            <Input
              label={t("contactTitle")}
              error={errors.contact_title?.message}
              {...register("contact_title")}
            />
            <Input
              type="email"
              label={t("email")}
              required
              autoComplete="email"
              error={errors.email?.message}
              {...register("email")}
            />
            <Input
              type="tel"
              label={t("phone")}
              autoComplete="tel"
              error={errors.phone?.message}
              {...register("phone")}
            />
          </div>
        </fieldset>

        <p className="text-xs text-[var(--text-muted)]">{t("privacyNote")}</p>

        <Button type="submit" variant="primary" fullWidth size="lg" loading={isSubmitting}>
          {t("submit")}
        </Button>
        <p className="text-center text-sm text-[var(--text-secondary)]">
          {t("haveAccount")}{" "}
          <Link
            href="/auth/login"
            className="font-semibold text-[var(--brand-primary)] hover:underline"
          >
            {t("loginLink")}
          </Link>
        </p>
      </form>
    </Shell>
  );
}

function Shell({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-[calc(100dvh-60px)] w-full flex-col items-center justify-center bg-[var(--bg-subtle)] px-4 py-10">
      <div className="w-full max-w-2xl">
        <div className="rounded-2xl border border-[var(--border-default)] bg-white p-6 shadow-[0_4px_20px_rgba(11,34,57,0.08)] sm:p-8">
          <div className="mb-6 flex items-center gap-3">
            <span className="flex size-11 items-center justify-center rounded-2xl icon-chip-primary shadow-[0_4px_16px_rgba(45,95,166,0.35)]">
              <Buildings
                aria-hidden
                weight="duotone"
                className="size-6 text-white"
              />
            </span>
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-[var(--text-primary)]">
                {title}
              </h1>
              {subtitle && (
                <p className="mt-0.5 text-sm text-[var(--text-secondary)]">
                  {subtitle}
                </p>
              )}
            </div>
          </div>
          {children}
        </div>
      </div>
    </div>
  );
}
