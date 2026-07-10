"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslations } from "next-intl";
import { CheckCircle, XCircle } from "@phosphor-icons/react";
import { Button, Input } from "@/components/ui";
import { Link } from "@/i18n/navigation";
import { authApi } from "@/lib/api";
import { zodResolver } from "@/lib/validation/resolver";
import { registerSchema, type RegisterValues } from "@/lib/validation/auth";
import { useApiErrorMessage, applyFieldErrors } from "@/lib/auth/use-api-error";
import { AuthShell } from "./auth-shell";
import { FormBanner } from "./form-banner";
import { SocialAuthButtons } from "./social-auth-buttons";
import { VerifyEmailView } from "./verify-email-view";
import { cn } from "@/lib/utils";

export function RegisterView({
  returnTo,
  email: initialEmail,
}: {
  returnTo?: string;
  email?: string;
} = {}) {
  const t = useTranslations("auth");
  const tv = useTranslations("auth.validation");
  const getMessage = useApiErrorMessage();

  // Preserve the guest's original intent when they switch to the login screen.
  const loginHref = returnTo
    ? `/auth/login?returnTo=${encodeURIComponent(returnTo)}${
        initialEmail ? `&email=${encodeURIComponent(initialEmail)}` : ""
      }`
    : "/auth/login";

  const [formError, setFormError] = useState<string | null>(null);
  const [doneEmail, setDoneEmail] = useState<string | null>(null);
  const [passwordFocused, setPasswordFocused] = useState(false);

  const {
    register,
    handleSubmit,
    reset,
    setError,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema(tv)),
    defaultValues: {
      email: initialEmail ?? "",
      password: "",
      confirm_password: "",
      accept_terms: false as unknown as true,
    },
  });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      const result = await authApi.register({
        email: values.email,
        password: values.password,
      });
      setDoneEmail(result.email ?? values.email);
    } catch (err) {
      if (applyFieldErrors(err, setError)) return;
      setFormError(getMessage(err, { context: "register" }));
    }
  });

  const footer = (
    <>
      {t("haveAccount")}{" "}
      <Link
        href={loginHref}
        className="font-semibold text-[var(--brand-primary)] hover:underline"
      >
        {t("loginTitle")}
      </Link>
    </>
  );

  if (doneEmail) {
    return (
      <VerifyEmailView
        email={doneEmail}
        onBack={() => {
          reset({
            email: doneEmail,
            password: "",
            confirm_password: "",
            accept_terms: false as unknown as true,
          });
          setPasswordFocused(false);
          setFormError(null);
          setDoneEmail(null);
        }}
      />
    );
  }

  const password = watch("password") ?? "";
  const showPasswordRules = passwordFocused || password.length > 0;
  const passwordRules = [
    {
      key: "min",
      label: t("passwordRuleMin"),
      valid: password.length >= 8,
    },
    {
      key: "letter",
      label: t("passwordRuleLetter"),
      valid: /[A-Za-z]/.test(password),
    },
    {
      key: "number",
      label: t("passwordRuleNumber"),
      valid: /[0-9]/.test(password),
    },
  ];
  const passwordField = register("password");

  return (
    <AuthShell title={t("registerTitle")} footer={footer}>
      <form className="space-y-4" onSubmit={onSubmit} noValidate>
        <SocialAuthButtons mode="register" returnTo="/onboarding/role" />

        {formError && <FormBanner>{formError}</FormBanner>}

        <Input
          type="email"
          label={t("email")}
          placeholder={t("emailPlaceholder")}
          autoComplete="email"
          required
          error={errors.email?.message}
          {...register("email")}
        />
        <Input
          type="password"
          label={t("password")}
          placeholder={t("passwordPlaceholder")}
          autoComplete="new-password"
          required
          error={errors.password?.message}
          {...passwordField}
          onFocus={() => {
            setPasswordFocused(true);
          }}
          onBlur={(event) => {
            setPasswordFocused(false);
            passwordField.onBlur(event);
          }}
        />
        {showPasswordRules && (
          <div className="-mt-2 flex flex-wrap items-center gap-x-5 gap-y-1 px-1">
            {passwordRules.map((rule) => {
              const Icon = rule.valid ? CheckCircle : XCircle;
              return (
                <div
                  key={rule.key}
                  className={cn(
                    "flex items-center gap-1.5 text-xs font-semibold transition-colors",
                    rule.valid
                      ? "text-[var(--text-primary)]"
                      : "text-[var(--text-muted)]",
                  )}
                >
                  <Icon
                    aria-hidden
                    weight={rule.valid ? "fill" : "regular"}
                    className="size-4 shrink-0"
                  />
                  <span>{rule.label}</span>
                </div>
              );
            })}
          </div>
        )}
        <Input
          type="password"
          label={t("confirmPassword")}
          placeholder={t("passwordPlaceholder")}
          autoComplete="new-password"
          required
          error={errors.confirm_password?.message}
          {...register("confirm_password")}
        />

        <label className="flex items-start gap-2.5 text-sm text-[var(--text-secondary)]">
          <input
            type="checkbox"
            className="mt-0.5 size-4 rounded border-[var(--border-default)] text-[var(--brand-primary)] outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
            {...register("accept_terms")}
          />
          <span>{t("acceptTermsLabel")}</span>
        </label>
        {errors.accept_terms?.message && (
          <p className="text-xs font-medium text-[var(--brand-red)]">
            {errors.accept_terms.message}
          </p>
        )}

        <Button
          type="submit"
          variant="primary"
          fullWidth
          size="lg"
          loading={isSubmitting}
        >
          {t("registerSubmit")}
        </Button>
      </form>
    </AuthShell>
  );
}
