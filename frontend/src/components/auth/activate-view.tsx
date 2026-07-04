"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslations } from "next-intl";
import { CheckCircle } from "@phosphor-icons/react";
import { Button, Input } from "@/components/ui";
import { Link } from "@/i18n/navigation";
import { authApi } from "@/lib/api";
import { zodResolver } from "@/lib/validation/resolver";
import {
  resetPasswordSchema,
  type ResetPasswordValues,
} from "@/lib/validation/auth";
import { useApiErrorMessage, applyFieldErrors } from "@/lib/auth/use-api-error";
import { AuthShell } from "./auth-shell";
import { FormBanner } from "./form-banner";

export function ActivateView({ token }: { token?: string }) {
  const t = useTranslations("activate");
  const tAuth = useTranslations("auth");
  const tv = useTranslations("auth.validation");
  const getMessage = useApiErrorMessage();

  const [formError, setFormError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<ResetPasswordValues>({
    resolver: zodResolver(resetPasswordSchema(tv)),
    defaultValues: { password: "", confirm_password: "" },
  });

  const onSubmit = handleSubmit(async (values) => {
    if (!token) return;
    setFormError(null);
    try {
      await authApi.activate({ token, password: values.password });
      setDone(true);
    } catch (err) {
      if (applyFieldErrors(err, setError)) return;
      setFormError(getMessage(err));
    }
  });

  const footer = (
    <Link
      href="/auth/login"
      className="font-semibold text-[var(--brand-primary)] hover:underline"
    >
      {tAuth("backToLogin")}
    </Link>
  );

  if (!token) {
    return (
      <AuthShell title={t("invalidTitle")} footer={footer}>
        <FormBanner title={t("invalidTitle")}>{t("invalidBody")}</FormBanner>
      </AuthShell>
    );
  }

  if (done) {
    return (
      <AuthShell title={t("doneTitle")} footer={footer}>
        <div className="space-y-5 text-center">
          <span className="mx-auto flex size-14 items-center justify-center rounded-2xl icon-chip-success shadow-[0_4px_16px_rgba(20,184,166,0.35)]">
            <CheckCircle
              aria-hidden
              weight="duotone"
              className="size-7 text-white"
            />
          </span>
          <p className="text-sm text-[var(--text-secondary)]">{t("doneBody")}</p>
          <Link
            href="/auth/login"
            className="inline-flex h-10 w-full items-center justify-center rounded-lg bg-[var(--brand-primary)] px-5 text-sm font-semibold text-white shadow-[var(--shadow-brand)] outline-none transition-colors hover:bg-[var(--blue-700)]"
          >
            {tAuth("submit")}
          </Link>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell title={t("title")} subtitle={t("subtitle")} footer={footer}>
      <form className="space-y-5" onSubmit={onSubmit} noValidate>
        {formError && <FormBanner>{formError}</FormBanner>}
        <Input
          type="password"
          label={tAuth("newPassword")}
          placeholder={tAuth("passwordPlaceholder")}
          autoComplete="new-password"
          required
          help={tAuth("passwordHelp")}
          error={errors.password?.message}
          {...register("password")}
        />
        <Input
          type="password"
          label={tAuth("confirmPassword")}
          placeholder={tAuth("passwordPlaceholder")}
          autoComplete="new-password"
          required
          error={errors.confirm_password?.message}
          {...register("confirm_password")}
        />
        <Button type="submit" variant="primary" fullWidth size="lg" loading={isSubmitting}>
          {t("submit")}
        </Button>
      </form>
    </AuthShell>
  );
}
