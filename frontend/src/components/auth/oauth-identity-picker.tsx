"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { CaretRight, UserCircle } from "@phosphor-icons/react";
import { useAuthStore } from "@/stores/auth-store";
import type { AuthIdentity } from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { FormBanner } from "./form-banner";
import { cn } from "@/lib/utils";

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

/**
 * Shared identity-chooser step for flows that can complete a login with one
 * email mapped to several personas (mirrors `LoginForm`'s inline chooser),
 * reused by the OAuth callback and link-confirm screens.
 */
export function OauthIdentityPicker({
  identities,
  onDone,
}: {
  identities: AuthIdentity[];
  onDone: () => void;
}) {
  const t = useTranslations("auth");
  const selectIdentity = useAuthStore((s) => s.selectIdentity);
  const getMessage = useApiErrorMessage();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function pick(id: string) {
    setBusy(true);
    setError(null);
    try {
      await selectIdentity(id);
      onDone();
    } catch (err) {
      setError(getMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-[var(--text-secondary)]">
        {t("chooseIdentity")}
      </p>
      {error && <FormBanner>{error}</FormBanner>}
      <ul className="space-y-2">
        {identities.map((identity) => (
          <li key={identity.id}>
            <button
              type="button"
              disabled={busy}
              onClick={() => pick(identity.id)}
              className="flex w-full items-center gap-3 rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] px-4 py-3 text-left outline-none transition-all hover:border-[var(--brand-primary)]/60 focus-visible:border-[var(--brand-primary)] disabled:cursor-not-allowed disabled:opacity-60"
            >
              <span
                className={cn(
                  "flex size-9 shrink-0 items-center justify-center rounded-xl shadow-sm",
                  identity.persona === "partner"
                    ? "icon-chip-success"
                    : identity.persona === "university_staff"
                      ? "icon-chip-info"
                      : "icon-chip-primary",
                )}
              >
                <UserCircle
                  aria-hidden
                  weight="duotone"
                  className="size-5 text-white"
                />
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
