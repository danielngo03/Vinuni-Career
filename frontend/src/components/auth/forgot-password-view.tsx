"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslations } from "next-intl";
import { ArrowLeft, CheckCircle } from "@phosphor-icons/react";
import { Button, Input } from "@/components/ui";
import { Link } from "@/i18n/navigation";
import { authApi } from "@/lib/api";
import {
  useApiErrorMessage,
  applyFieldErrors,
  getRetryAfterSeconds,
} from "@/lib/auth/use-api-error";
import { useCooldown } from "@/lib/auth/use-cooldown";
import {
  forgotPasswordSchema,
  resetPasswordSchema,
  type ForgotPasswordValues,
  type ResetPasswordValues,
} from "@/lib/validation/auth";
import { zodResolver } from "@/lib/validation/resolver";
import { AuthShell } from "./auth-shell";
import { FormBanner } from "./form-banner";
import { OtpInput } from "./verify-email-view";

export function ForgotPasswordView({ email }: { email?: string }) {
  const t = useTranslations("auth");
  const tv = useTranslations("auth.validation");
  const getMessage = useApiErrorMessage();

  const [formError, setFormError] = useState<string | null>(null);
  const [resetError, setResetError] = useState<string | null>(null);
  const [resetErrorTone, setResetErrorTone] = useState<"error" | "info">("error");
  const [sentEmail, setSentEmail] = useState<string | null>(null);
  const [otp, setOtp] = useState("");
  const [resent, setResent] = useState(false);
  const [done, setDone] = useState(false);
  const [resending, setResending] = useState(false);
  const cooldown = useCooldown();

  const requestForm = useForm<ForgotPasswordValues>({
    resolver: zodResolver(forgotPasswordSchema(tv)),
    defaultValues: { email: email ?? "" },
  });

  const resetForm = useForm<ResetPasswordValues>({
    resolver: zodResolver(resetPasswordSchema(tv)),
    defaultValues: { password: "", confirm_password: "" },
  });

  // Preserve whatever email the user already typed (or confirmed) when they
  // navigate back to login, so they don't have to retype it.
  const typedEmail = requestForm.watch("email");
  const knownEmail = sentEmail ?? typedEmail;
  const backToLoginHref = knownEmail
    ? `/auth/login?email=${encodeURIComponent(knownEmail)}`
    : "/auth/login";
  const footer = (
    <Link
      href={backToLoginHref}
      className="font-semibold text-[var(--brand-primary)] hover:underline"
    >
      {t("backToLogin")}
    </Link>
  );

  const requestReset = requestForm.handleSubmit(async (values) => {
    setFormError(null);
    setResent(false);
    try {
      await authApi.forgotPassword({ email: values.email });
      setSentEmail(values.email);
      setOtp("");
      resetForm.reset({ password: "", confirm_password: "" });
    } catch (err) {
      setFormError(getMessage(err));
    }
  });

  const resendCode = async () => {
    if (!sentEmail) return;
    setResending(true);
    setResetError(null);
    setResent(false);
    try {
      await authApi.forgotPassword({ email: sentEmail });
      setOtp("");
      setResent(true);
      setResetErrorTone("error");
    } catch (err) {
      const retryAfter = getRetryAfterSeconds(err);
      if (retryAfter) {
        cooldown.start(retryAfter);
        setResetErrorTone("info");
      } else {
        setResetErrorTone("error");
      }
      setResetError(getMessage(err));
    } finally {
      setResending(false);
    }
  };

  const submitOtpReset = resetForm.handleSubmit(async (values) => {
    if (!sentEmail) return;
    if (otp.length !== 6) {
      setResetError(t("otpRequired"));
      return;
    }
    setResetError(null);
    try {
      await authApi.resetPasswordOtp({
        email: sentEmail,
        otp_code: otp,
        password: values.password,
      });
      setDone(true);
    } catch (err) {
      if (applyFieldErrors(err, resetForm.setError)) return;
      setResetError(getMessage(err));
    }
  });

  if (done) {
    return (
      <AuthShell title={t("resetDoneTitle")} footer={footer}>
        <div className="space-y-5 text-center">
          <span className="mx-auto flex size-12 items-center justify-center rounded-2xl bg-[var(--ink)] text-white">
            <CheckCircle aria-hidden weight="bold" className="size-6" />
          </span>
          <p className="text-sm text-[var(--text-secondary)]">
            {t("resetDoneBody")}
          </p>
          <Link
            href="/auth/login"
            className="inline-flex h-11 w-full items-center justify-center rounded-full bg-[var(--ink)] px-5 text-sm font-semibold text-white shadow-[0_14px_32px_rgba(0,0,0,0.16)] outline-none transition-colors hover:bg-[var(--ink-soft)]"
          >
            {t("submit")}
          </Link>
        </div>
      </AuthShell>
    );
  }

  if (sentEmail) {
    const backControl = (
      <button
        type="button"
        onClick={() => {
          setSentEmail(null);
          setOtp("");
          setResetError(null);
          setResent(false);
          requestForm.setValue("email", sentEmail);
        }}
        className="inline-flex items-center gap-2 text-sm font-semibold text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--field-focus-ring)]"
      >
        <ArrowLeft aria-hidden className="size-4" />
        {t("back")}
      </button>
    );

    return (
      <AuthShell
        title={t("resetTitle")}
        subtitle={t("forgotOtpSubtitle", { email: sentEmail })}
        beforeTitle={backControl}
        footer={footer}
      >
        <form className="space-y-5" onSubmit={submitOtpReset} noValidate>
          {resetError && (
            <FormBanner tone={resetErrorTone}>{resetError}</FormBanner>
          )}
          {resent && (
            <FormBanner tone="success">{t("forgotResent")}</FormBanner>
          )}

          <div className="space-y-2">
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                {t("otpCode")}
              </p>
              <button
                type="button"
                onClick={resendCode}
                disabled={resending || cooldown.active}
                className="text-xs font-semibold text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {resending
                  ? t("sending")
                  : cooldown.active
                    ? `${t("forgotResend")} (${cooldown.seconds}s)`
                    : t("forgotResend")}
              </button>
            </div>
            <OtpInput
              value={otp}
              onChange={(value) => {
                setOtp(value);
                if (resetError) setResetError(null);
              }}
              disabled={resetForm.formState.isSubmitting}
            />
          </div>

          <Input
            type="password"
            label={t("newPassword")}
            placeholder={t("passwordPlaceholder")}
            autoComplete="new-password"
            required
            error={resetForm.formState.errors.password?.message}
            {...resetForm.register("password")}
          />
          <Input
            type="password"
            label={t("confirmPassword")}
            placeholder={t("passwordPlaceholder")}
            autoComplete="new-password"
            required
            error={resetForm.formState.errors.confirm_password?.message}
            {...resetForm.register("confirm_password")}
          />

          <Button
            type="submit"
            variant="primary"
            fullWidth
            size="lg"
            loading={resetForm.formState.isSubmitting}
          >
            {t("resetSubmit")}
          </Button>
        </form>
      </AuthShell>
    );
  }

  return (
    <AuthShell title={t("forgotTitle")} footer={footer}>
      <form className="space-y-5" onSubmit={requestReset} noValidate>
        {formError && <FormBanner>{formError}</FormBanner>}
        <Input
          type="email"
          label={t("email")}
          placeholder={t("emailPlaceholder")}
          autoComplete="email"
          required
          error={requestForm.formState.errors.email?.message}
          {...requestForm.register("email")}
        />
        <Button
          type="submit"
          variant="primary"
          fullWidth
          size="lg"
          loading={requestForm.formState.isSubmitting}
        >
          {t("forgotSubmit")}
        </Button>
      </form>
    </AuthShell>
  );
}
