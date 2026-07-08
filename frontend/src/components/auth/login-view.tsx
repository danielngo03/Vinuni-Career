"use client";

import { useTranslations } from "next-intl";
import { AuthShell } from "./auth-shell";
import { LoginForm } from "./login-form";

export function LoginView({
  returnTo,
  email,
}: {
  returnTo?: string;
  email?: string;
}) {
  const t = useTranslations("auth");
  return (
    <AuthShell title={t("loginTitle")}>
      <LoginForm returnTo={returnTo} email={email} />
    </AuthShell>
  );
}
