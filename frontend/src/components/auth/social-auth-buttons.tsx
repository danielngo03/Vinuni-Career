"use client";

import type { ComponentType } from "react";
import { useTranslations } from "next-intl";
import { authApi } from "@/lib/api";
import { cn } from "@/lib/utils";

type SocialAuthMode = "login" | "register";
type SocialProvider = "google" | "facebook";

interface SocialAuthButtonsProps {
  mode: SocialAuthMode;
  returnTo?: string;
}

const PROVIDERS: Array<{
  key: SocialProvider;
  icon: ComponentType<{ className?: string }>;
  labelKey:
    | "loginWithGoogle"
    | "loginWithFacebook"
    | "registerWithGoogle"
    | "registerWithFacebook";
}> = [
  {
    key: "google",
    icon: GoogleBrandIcon,
    labelKey: "loginWithGoogle",
  },
  {
    key: "facebook",
    icon: FacebookBrandIcon,
    labelKey: "loginWithFacebook",
  },
];

function GoogleBrandIcon({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      className={className}
      focusable="false"
    >
      <path
        fill="#4285F4"
        d="M23.49 12.27c0-.79-.07-1.53-.19-2.27H12v4.32h6.47c-.29 1.39-1.12 2.57-2.39 3.36v2.8h3.63c2.12-1.96 3.78-4.85 3.78-8.21Z"
      />
      <path
        fill="#34A853"
        d="M12 24c3.24 0 5.96-1.07 7.94-2.91l-3.63-2.8c-1.01.68-2.3 1.08-4.31 1.08-3.13 0-5.78-2.11-6.73-4.95H1.52v2.89C3.49 21.24 7.45 24 12 24Z"
      />
      <path
        fill="#FBBC05"
        d="M5.27 14.42A7.2 7.2 0 0 1 4.89 12c0-.84.14-1.65.38-2.42V6.69H1.52A11.96 11.96 0 0 0 0 12c0 1.93.46 3.75 1.52 5.31l3.75-2.89Z"
      />
      <path
        fill="#EA4335"
        d="M12 4.63c1.76 0 3.34.61 4.58 1.8l3.24-3.24C17.95 1.45 15.23 0 12 0 7.45 0 3.49 2.76 1.52 6.69l3.75 2.89C6.22 6.74 8.87 4.63 12 4.63Z"
      />
    </svg>
  );
}

function FacebookBrandIcon({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      className={className}
      focusable="false"
    >
      <circle cx="12" cy="12" r="12" fill="#1877F2" />
      <path
        fill="#fff"
        d="M16.67 15.47 17.2 12h-3.33V9.75c0-.95.46-1.88 1.95-1.88h1.51V4.91s-1.37-.24-2.69-.24c-2.74 0-4.53 1.66-4.53 4.67V12H7.07v3.47h3.04v8.39a12.15 12.15 0 0 0 3.76 0v-8.39h2.8Z"
      />
    </svg>
  );
}

export function SocialAuthButtons({ mode, returnTo }: SocialAuthButtonsProps) {
  const t = useTranslations("auth");

  function start(provider: SocialProvider) {
    window.location.assign(authApi.oauthStartUrl(provider, { mode, returnTo }));
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-2 sm:grid-cols-2">
        {PROVIDERS.map((provider) => {
          const Icon = provider.icon;
          const labelKey =
            mode === "login"
              ? provider.labelKey
              : provider.key === "google"
                ? "registerWithGoogle"
                : "registerWithFacebook";
          return (
            <button
              key={provider.key}
              type="button"
              onClick={() => start(provider.key)}
              className={cn(
                "inline-flex h-11 w-full cursor-pointer items-center justify-center gap-2 rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] px-3 text-[0.8125rem] font-semibold text-[var(--text-primary)] outline-none transition-all duration-200",
                "hover:border-[var(--border-strong)] hover:bg-[var(--bg-subtle)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40",
              )}
            >
              <Icon className="size-5 shrink-0" />
              <span className="min-w-0 truncate">{t(labelKey)}</span>
            </button>
          );
        })}
      </div>

      <div className="flex items-center gap-3" aria-hidden>
        <span className="h-px flex-1 bg-[var(--border-default)]" />
        <span className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
          {t("or")}
        </span>
        <span className="h-px flex-1 bg-[var(--border-default)]" />
      </div>
    </div>
  );
}
