"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { ArrowLeft } from "@phosphor-icons/react";
import { Button, Input } from "@/components/ui";
import { Link, useRouter } from "@/i18n/navigation";
import { authApi, ApiError, type AuthIdentity, type LoginResult } from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { AuthShell } from "./auth-shell";
import { FormBanner } from "./form-banner";
import { OauthIdentityPicker } from "./oauth-identity-picker";

/**
 * Lands here when the OAuth email matches an existing password account
 * (`{frontend}/auth/oauth/link-conflict?ticket=...&email=...`). The user must
 * confirm ownership with their existing password before the accounts link.
 */
export function OauthLinkConflictView({
  ticket,
  email,
}: {
  ticket?: string;
  email?: string;
}) {
  const t = useTranslations("auth");
  const router = useRouter();
  const queryClient = useQueryClient();
  const applyLoginResult = useAuthStore((s) => s.applyLoginResult);
  const getMessage = useApiErrorMessage();

  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [identities, setIdentities] = useState<AuthIdentity[] | null>(null);

  const confirm = useMutation({
    mutationFn: () => authApi.oauthLinkConfirm({ ticket: ticket!, password }),
    onSuccess: async (result: LoginResult) => {
      await applyLoginResult(result);
      if (result.requires_identity_selection && result.identities?.length) {
        setIdentities(result.identities);
        return;
      }
      finish();
    },
    onError: (err) => {
      const invalid = err instanceof ApiError && err.status === 401;
      setError(invalid ? t("oauth.linkConflictInvalidPassword") : getMessage(err));
    },
  });

  function finish() {
    queryClient.invalidateQueries();
    const persona = useAuthStore.getState().user?.persona ?? "student";
    router.replace(`/${persona}/dashboard`);
  }

  function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!ticket || !password) return;
    setError(null);
    confirm.mutate();
  }

  const backControl = (
    <Link
      href="/auth/login"
      className="inline-flex items-center gap-2 text-sm font-semibold text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--field-focus-ring)]"
    >
      <ArrowLeft aria-hidden className="size-4" />
      {t("back")}
    </Link>
  );

  if (identities) {
    return (
      <AuthShell title={t("loginTitle")} beforeTitle={backControl}>
        <OauthIdentityPicker identities={identities} onDone={finish} />
      </AuthShell>
    );
  }

  if (!ticket || !email) {
    return (
      <AuthShell title={t("oauth.failedTitle")} beforeTitle={backControl}>
        <FormBanner>{t("oauth.missingTicket")}</FormBanner>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title={t("oauth.linkConflictTitle")}
      subtitle={t("oauth.linkConflictSubtitle", { email })}
      beforeTitle={backControl}
    >
      <form className="space-y-5" onSubmit={onSubmit} noValidate>
        {error && <FormBanner>{error}</FormBanner>}
        <Input
          type="password"
          label={t("oauth.linkConflictPassword")}
          placeholder={t("passwordPlaceholder")}
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => {
            setPassword(e.target.value);
            if (error) setError(null);
          }}
        />
        <Button
          type="submit"
          variant="primary"
          fullWidth
          size="lg"
          loading={confirm.isPending}
          disabled={!password}
        >
          {t("oauth.linkConflictSubmit")}
        </Button>
      </form>
    </AuthShell>
  );
}
