"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslations } from "next-intl";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CaretRight, ShieldCheck, UserCircle } from "@phosphor-icons/react";
import { Button, Input } from "@/components/ui";
import { Link, useRouter } from "@/i18n/navigation";
import { useAuthStore } from "@/stores/auth-store";
import { ApiError, type AuthIdentity } from "@/lib/api";
import { zodResolver } from "@/lib/validation/resolver";
import { loginSchema, type LoginValues } from "@/lib/validation/auth";
import { useApiErrorMessage, applyFieldErrors } from "@/lib/auth/use-api-error";
import { FormBanner } from "./form-banner";
import { SocialAuthButtons } from "./social-auth-buttons";
import { cn } from "@/lib/utils";

export interface LoginFormProps {
  /** Where to go after a successful login (locale-less path). */
  returnTo?: string;
  /** Called after success instead of default navigation (used by the modal). */
  onSuccess?: () => void;
  /** Tighter spacing + links suited to the modal. */
  compact?: boolean;
  /** Pre-fills the email field (e.g. carried back from forgot-password). */
  email?: string;
}

const TOTP_LENGTH = 6;

function personaLabelKey(persona: AuthIdentity["persona"]) {
  switch (persona) {
    case "partner_member":
    case "partner":
      return "partner";
    case "university_staff":
    case "university":
      return "university";
    default:
      return "student";
  }
}

export function LoginForm({ returnTo, onSuccess, compact, email }: LoginFormProps) {
  const t = useTranslations("auth");
  const tv = useTranslations("auth.validation");
  const router = useRouter();
  const queryClient = useQueryClient();
  const signIn = useAuthStore((s) => s.signIn);
  const completeTotp = useAuthStore((s) => s.completeTotp);
  const selectIdentity = useAuthStore((s) => s.selectIdentity);
  const getMessage = useApiErrorMessage();

  const [formError, setFormError] = useState<string | null>(null);
  const [unverifiedEmail, setUnverifiedEmail] = useState<string | null>(null);
  const [identities, setIdentities] = useState<AuthIdentity[] | null>(null);
  const [busy, setBusy] = useState(false);

  // TOTP second-factor step state.
  const [totpChallenge, setTotpChallenge] = useState<string | null>(null);
  const [totpCode, setTotpCode] = useState("");
  const [totpError, setTotpError] = useState<string | null>(null);
  const [totpBusy, setTotpBusy] = useState(false);

  const {
    register,
    handleSubmit,
    getValues,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({
    resolver: zodResolver(loginSchema(tv)),
    defaultValues: { email: email ?? "", password: "" },
  });

  function finish() {
    queryClient.invalidateQueries();
    if (onSuccess) {
      onSuccess();
      return;
    }
    const persona = useAuthStore.getState().user?.persona ?? "student";
    router.replace(returnTo || `/${persona}/dashboard`);
  }

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    setUnverifiedEmail(null);
    try {
      const result = await signIn(values.email, values.password);
      // Account has TOTP enabled: transition to the second-factor step.
      if (result.totp_required && result.challenge_token) {
        setTotpChallenge(result.challenge_token);
        setTotpCode("");
        setTotpError(null);
        return;
      }
      if (result.requires_identity_selection && result.identities?.length) {
        setIdentities(result.identities);
        return;
      }
      finish();
    } catch (err) {
      if (applyFieldErrors(err, setError)) return;
      const message = getMessage(err, { context: "login" });
      // Surface the resend-verification affordance when relevant.
      const reason =
        err && typeof err === "object" && "details" in err
          ? (err as { details?: { reason?: string } }).details?.reason
          : undefined;
      if (reason === "email_not_verified") setUnverifiedEmail(values.email);
      setFormError(message);
    }
  });

  async function submitTotp(event: React.FormEvent) {
    event.preventDefault();
    if (!totpChallenge || totpCode.length !== TOTP_LENGTH) return;
    setTotpBusy(true);
    setTotpError(null);
    try {
      const result = await completeTotp(totpChallenge, totpCode);
      if (result.requires_identity_selection && result.identities?.length) {
        setTotpChallenge(null);
        setIdentities(result.identities);
        return;
      }
      finish();
    } catch (err) {
      // Wrong/expired code → friendly invalid-code copy; keep the step for retry.
      const invalid =
        err instanceof ApiError &&
        (err.status === 401 || err.code === "VALIDATION_FAILED");
      setTotpError(invalid ? t("totpInvalid") : getMessage(err));
      setTotpCode("");
    } finally {
      setTotpBusy(false);
    }
  }

  function cancelTotp() {
    setTotpChallenge(null);
    setTotpCode("");
    setTotpError(null);
  }

  async function pickIdentity(id: string) {
    setBusy(true);
    setFormError(null);
    try {
      await selectIdentity(id);
      finish();
    } catch (err) {
      setFormError(getMessage(err));
    } finally {
      setBusy(false);
    }
  }

  // TOTP second-factor step.
  if (totpChallenge) {
    return (
      <form
        className={compact ? "space-y-4" : "space-y-5"}
        onSubmit={submitTotp}
        noValidate
      >
        <div className="flex flex-col items-center gap-2 text-center">
          <span className="mb-1 flex size-14 items-center justify-center rounded-2xl icon-chip-primary shadow-[0_4px_24px_rgba(11,103,255,0.25)]">
            <ShieldCheck
              aria-hidden
              weight="duotone"
              className="size-8 text-white"
            />
          </span>
          <h2 className="text-base font-semibold text-[var(--text-primary)]">
            {t("totpTitle")}
          </h2>
          <p className="text-sm text-[var(--text-secondary)]">
            {t("totpSubtitle")}
          </p>
        </div>

        {totpError && <FormBanner>{totpError}</FormBanner>}

        <Input
          type="text"
          label={t("totpLabel")}
          placeholder={t("totpPlaceholder")}
          help={t("totpHelp")}
          inputMode="numeric"
          autoComplete="one-time-code"
          autoFocus
          required
          maxLength={TOTP_LENGTH}
          pattern="[0-9]*"
          value={totpCode}
          onChange={(e) =>
            setTotpCode(e.target.value.replace(/\D/g, "").slice(0, TOTP_LENGTH))
          }
          className="text-center text-lg tracking-[0.5em]"
        />

        <Button
          type="submit"
          variant="primary"
          fullWidth
          size="lg"
          loading={totpBusy}
          disabled={totpCode.length !== TOTP_LENGTH}
        >
          {t("totpSubmit")}
        </Button>

        <button
          type="button"
          onClick={cancelTotp}
          className="mx-auto flex items-center gap-1.5 text-sm font-semibold text-[var(--brand-primary)] outline-none hover:underline"
        >
          <ArrowLeft aria-hidden weight="bold" className="size-4" />
          {t("backToLogin")}
        </button>
      </form>
    );
  }

  // Identity chooser step (one email, multiple personas).
  if (identities) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-[var(--text-secondary)]">
          {t("chooseIdentity")}
        </p>
        {formError && <FormBanner>{formError}</FormBanner>}
        <ul className="space-y-2">
          {identities.map((identity) => (
            <li key={identity.id}>
              <button
                type="button"
                disabled={busy}
                onClick={() => pickIdentity(identity.id)}
                className="flex w-full items-center gap-3 rounded-xl border border-white/60 bg-white/75 px-4 py-3 text-left outline-none backdrop-blur-sm transition-all hover:border-[var(--brand-primary)]/60 hover:bg-white/90 focus-visible:border-[var(--brand-primary)] disabled:cursor-not-allowed disabled:opacity-60"
              >
                <span className={cn(
                  "flex size-9 shrink-0 items-center justify-center rounded-xl shadow-sm",
                  identity.persona === "partner"
                    ? "icon-chip-success"
                    : identity.persona === "university_staff"
                      ? "icon-chip-info"
                      : "icon-chip-primary",
                )}>
                  <UserCircle aria-hidden weight="duotone" className="size-5 text-white" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-semibold text-[var(--text-primary)]">
                    {identity.display_name ?? identity.org_name ?? identity.persona}
                  </span>
                  <span className="block text-xs text-[var(--text-secondary)]">
                    {t(`personaLabel.${personaLabelKey(identity.persona)}`)}
                  </span>
                </span>
                <CaretRight
                  aria-hidden
                  weight="bold"
                  className="size-4 text-[var(--text-muted)]"
                />
              </button>
            </li>
          ))}
        </ul>
      </div>
    );
  }

  return (
    <form className={compact ? "space-y-4" : "space-y-5"} onSubmit={onSubmit} noValidate>
      {!compact && <SocialAuthButtons mode="login" returnTo={returnTo} />}

      {formError && (
        <FormBanner>
          {formError}
          {unverifiedEmail && (
            <>
              {" "}
              <Link
                href={`/auth/verify-email?email=${encodeURIComponent(unverifiedEmail)}`}
                className="font-semibold underline"
              >
                {t("resendVerificationLink")}
              </Link>
            </>
          )}
        </FormBanner>
      )}

      <Input
        type="email"
        label={t("email")}
        placeholder={t("emailPlaceholder")}
        autoComplete="email"
        required
        error={errors.email?.message}
        {...register("email")}
      />
      <div>
        <Input
          type="password"
          label={t("password")}
          placeholder={t("passwordPlaceholder")}
          autoComplete="current-password"
          required
          error={errors.password?.message}
          {...register("password")}
        />
        <div className="mt-1.5 text-right">
          <Link
            href={`/auth/forgot-password?email=${encodeURIComponent(getValues("email"))}`}
            className="text-xs font-semibold text-[var(--brand-primary)] outline-none hover:underline"
          >
            {t("forgotPasswordLink")}
          </Link>
        </div>
      </div>

      <Button
        type="submit"
        variant="primary"
        fullWidth
        size="lg"
        loading={isSubmitting}
      >
        {t("submit")}
      </Button>

      <p className="text-center text-sm text-[var(--text-secondary)]">
        {t("noAccount")}{" "}
        <Link
          href="/auth/register"
          className="font-semibold text-[var(--brand-primary)] outline-none hover:underline"
        >
          {t("registerLink")}
        </Link>
      </p>
    </form>
  );
}
