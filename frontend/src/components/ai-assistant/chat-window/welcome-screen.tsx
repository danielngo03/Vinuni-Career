"use client";

import { Robot, Sparkle, Spinner } from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { QUICK_PROMPTS, SUGGESTION_ITEMS } from "./constants";

export function WelcomeScreen({
  t,
  onPrompt,
}: {
  t: (k: string) => string;
  onPrompt: (prompt: string) => void;
}) {
  return (
    <div className="flex flex-col items-center gap-4 py-2 text-center">
      {/* Glowing avatar */}
      <span
        className="flex size-14 items-center justify-center rounded-2xl bg-gradient-to-br from-[var(--brand-primary)] to-[var(--brand-teal)]"
        style={{ boxShadow: "0 4px 20px rgba(45,95,166,0.30), 0 0 0 1px rgba(45,95,166,0.12)" }}
      >
        <Sparkle aria-hidden weight="fill" className="size-7 text-white" />
      </span>

      <div>
        <p className="text-sm font-bold text-[var(--text-primary)]">
          {t("welcomeTitle")}
        </p>
        <p className="mt-1 text-xs text-[var(--text-secondary)]">
          {t("welcomeBody")}
        </p>
      </div>

      {/* Quick-prompt chips */}
      <div className="flex w-full flex-wrap gap-1.5 justify-center">
        {QUICK_PROMPTS.map((prompt) => (
          <button
            key={prompt}
            type="button"
            onClick={() => onPrompt(prompt)}
            className="rounded-full border border-[var(--brand-primary)]/20 bg-[var(--brand-primary)]/5 px-3 py-1 text-[11px] font-medium text-[var(--brand-primary)] outline-none transition hover:bg-[var(--brand-primary)]/10 hover:border-[var(--brand-primary)]/40 focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
          >
            {prompt}
          </button>
        ))}
      </div>

      {/* Link shortcuts */}
      <div className="grid w-full grid-cols-2 gap-2">
        {SUGGESTION_ITEMS.slice(0, 4).map(({ icon: Icon, key, href }) => (
          <Link
            key={key}
            href={href as Parameters<typeof Link>[0]["href"]}
            className="flex items-center gap-2 rounded-xl border border-[var(--glass-border)] bg-[var(--glass-surface-light)] px-3 py-2 text-left text-xs font-medium text-[var(--text-secondary)] outline-none transition hover:border-[var(--brand-primary)]/40 hover:bg-[var(--glass-surface-heavy)] hover:text-[var(--brand-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
          >
            <Icon aria-hidden weight="duotone" className="size-4 shrink-0 text-[var(--brand-primary)]" />
            {t(key)}
          </Link>
        ))}
      </div>
    </div>
  );
}

export function AuthLoadingPrompt() {
  return (
    <div className="flex flex-col items-center gap-3 py-6 text-center">
      <span
        className="flex size-14 items-center justify-center rounded-2xl bg-gradient-to-br from-[var(--brand-primary)] to-[var(--brand-teal)]"
        style={{ boxShadow: "0 4px 20px rgba(45,95,166,0.25)" }}
      >
        <Spinner aria-hidden className="size-7 animate-spin text-white" />
      </span>
      <span className="h-3 w-28 rounded-full bg-[var(--bg-subtle)]" />
      <span className="h-2 w-40 rounded-full bg-[var(--bg-subtle)]" />
    </div>
  );
}

export function GuestPrompt({ t }: { t: (k: string) => string }) {
  return (
    <div className="flex flex-col items-center gap-3 py-6 text-center">
      <span
        className="flex size-14 items-center justify-center rounded-2xl bg-gradient-to-br from-[var(--brand-primary)] to-[var(--brand-teal)]"
        style={{ boxShadow: "0 4px 20px rgba(45,95,166,0.25)" }}
      >
        <Robot aria-hidden weight="fill" className="size-7 text-white" />
      </span>
      <p className="text-sm font-bold text-[var(--text-primary)]">{t("guestTitle")}</p>
      <p className="text-xs text-[var(--text-secondary)]">{t("guestBody")}</p>
      <Link
        href="/auth/login"
        className="rounded-xl icon-chip-primary px-5 py-2 text-sm font-semibold text-white shadow-[0_2px_8px_rgba(45,95,166,0.25)] outline-none transition hover:shadow-[0_4px_12px_rgba(45,95,166,0.35)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
      >
        {t("signIn")}
      </Link>
    </div>
  );
}
