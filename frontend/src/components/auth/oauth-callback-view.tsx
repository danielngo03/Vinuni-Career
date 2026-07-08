"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CircleNotch } from "@phosphor-icons/react";
import { Link, useRouter } from "@/i18n/navigation";
import { useTranslations } from "next-intl";
import { authApi, type AuthIdentity, type LoginResult } from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { AuthShell } from "./auth-shell";
import { FormBanner } from "./form-banner";
import { OauthIdentityPicker } from "./oauth-identity-picker";

/**
 * Lands here after a successful OAuth provider round-trip
 * (`{frontend}/auth/oauth/callback?ticket=...`). Exchanges the one-time
 * ticket for a session and continues exactly like a normal login success.
 */
export function OauthCallbackView({ ticket }: { ticket?: string }) {
  const t = useTranslations("auth");
  const router = useRouter();
  const queryClient = useQueryClient();
  const applyLoginResult = useAuthStore((s) => s.applyLoginResult);
  const getMessage = useApiErrorMessage();
  const started = useRef(false);

  const [identities, setIdentities] = useState<AuthIdentity[] | null>(null);

  const exchange = useMutation({
    mutationFn: (tok: string) => authApi.oauthExchange({ ticket: tok }),
    onSuccess: async (result: LoginResult) => {
      await applyLoginResult(result);
      if (result.requires_identity_selection && result.identities?.length) {
        setIdentities(result.identities);
        return;
      }
      finish();
    },
  });

  useEffect(() => {
    if (ticket && !started.current) {
      started.current = true;
      exchange.mutate(ticket);
    }
  }, [ticket]); // eslint-disable-line react-hooks/exhaustive-deps

  function finish() {
    queryClient.invalidateQueries();
    const persona = useAuthStore.getState().user?.persona ?? "student";
    router.replace(`/${persona}/dashboard`);
  }

  const backToLogin = (
    <Link
      href="/auth/login"
      className="font-semibold text-[var(--brand-primary)] hover:underline"
    >
      {t("backToLogin")}
    </Link>
  );

  // Identity chooser step (one email, multiple personas).
  if (identities) {
    return (
      <AuthShell title={t("loginTitle")}>
        <OauthIdentityPicker identities={identities} onDone={finish} />
      </AuthShell>
    );
  }

  // Missing ticket — nothing to exchange.
  if (!ticket) {
    return (
      <AuthShell title={t("oauth.failedTitle")} footer={backToLogin}>
        <FormBanner>{t("oauth.missingTicket")}</FormBanner>
      </AuthShell>
    );
  }

  if (exchange.isError) {
    return (
      <AuthShell title={t("oauth.failedTitle")} footer={backToLogin}>
        <FormBanner>{getMessage(exchange.error)}</FormBanner>
      </AuthShell>
    );
  }

  // Pending / idle — always show the spinner until the mutation settles.
  return (
    <AuthShell title={t("oauth.completingTitle")}>
      <div className="flex flex-col items-center gap-3 py-4 text-center">
        <CircleNotch
          aria-hidden
          weight="bold"
          className="size-8 animate-spin text-[var(--ink)]"
        />
        <p className="text-sm text-[var(--text-secondary)]">
          {t("oauth.completingBody")}
        </p>
      </div>
    </AuthShell>
  );
}
