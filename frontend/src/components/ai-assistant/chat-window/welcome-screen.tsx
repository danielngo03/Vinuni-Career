"use client";

import { Loader2, Sparkles } from "lucide-react";
import { Link } from "@/i18n/navigation";
import {
  QUICK_PROMPTS_BY_PERSONA,
  SUGGESTION_ITEMS_BY_PERSONA,
  type ChatPersona,
} from "./constants";

/** Small AI-identity marker tile — one restrained `--content-ai` accent, not a
 * decorative gradient blob (v10 §1.1.2). */
function AiMarker({ className = "" }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={
        "flex size-10 shrink-0 items-center justify-center rounded-xl bg-[var(--content-ai-soft)] " +
        className
      }
    >
      <Sparkles strokeWidth={1.9} className="size-5 text-[var(--content-ai)]" />
    </span>
  );
}

export function WelcomeScreen({
  t,
  onPrompt,
  persona = "student",
}: {
  t: (k: string) => string;
  onPrompt: (prompt: string) => void;
  persona?: ChatPersona;
}) {
  const isPartner = persona === "partner";
  const prompts = QUICK_PROMPTS_BY_PERSONA[persona] ?? QUICK_PROMPTS_BY_PERSONA.student;
  const links = SUGGESTION_ITEMS_BY_PERSONA[persona] ?? SUGGESTION_ITEMS_BY_PERSONA.student;
  return (
    <div className="flex flex-col items-center gap-4 py-2 text-center">
      <AiMarker />

      <div>
        <p className="type-h2 text-[var(--text-primary)]">
          {t(isPartner ? "welcomeTitlePartner" : "welcomeTitle")}
        </p>
        <p className="type-small mt-1 text-[var(--text-secondary)]">
          {t(isPartner ? "welcomeBodyPartner" : "welcomeBody")}
        </p>
      </div>

      {/* Quick-prompt chips */}
      <div className="flex w-full flex-wrap justify-center gap-1.5">
        {prompts.map((prompt) => (
          <button
            key={prompt}
            type="button"
            onClick={() => onPrompt(prompt)}
            className="type-caption rounded-full border border-[var(--border-default)] bg-[var(--surface-card)] px-3 py-1 font-medium text-[var(--text-secondary)] outline-none transition-colors hover:border-[var(--field-focus-border)] hover:bg-[var(--bg-muted)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
          >
            {prompt}
          </button>
        ))}
      </div>

      {/* Link shortcuts */}
      <div className="grid w-full grid-cols-2 gap-2">
        {links.slice(0, 4).map(({ icon: Icon, key, href }) => (
          <Link
            key={key}
            href={href as Parameters<typeof Link>[0]["href"]}
            className="type-small flex items-center gap-2 rounded-lg border border-[var(--border-default)] bg-[var(--surface-card)] px-3 py-2 text-left font-medium text-[var(--text-secondary)] outline-none transition-colors hover:border-[var(--field-focus-border)] hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
          >
            <Icon aria-hidden strokeWidth={1.9} className="size-4 shrink-0 text-[var(--content-ai)]" />
            <span className="min-w-0 truncate">{t(key)}</span>
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
        aria-hidden
        className="flex size-10 items-center justify-center rounded-xl bg-[var(--content-ai-soft)]"
      >
        <Loader2 className="size-5 animate-spin text-[var(--content-ai)]" />
      </span>
      <span className="h-3 w-28 rounded-full bg-[var(--bg-muted)]" />
      <span className="h-2 w-40 rounded-full bg-[var(--bg-muted)]" />
    </div>
  );
}

export function GuestPrompt({ t }: { t: (k: string) => string }) {
  return (
    <div className="flex flex-col items-center gap-3 py-6 text-center">
      <span
        aria-hidden
        className="flex size-10 items-center justify-center rounded-xl bg-[var(--content-ai-soft)]"
      >
        <Sparkles strokeWidth={1.9} className="size-5 text-[var(--content-ai)]" />
      </span>
      <p className="type-h3 text-[var(--text-primary)]">{t("guestTitle")}</p>
      <p className="type-small text-[var(--text-secondary)]">{t("guestBody")}</p>
      <Link
        href="/auth/login"
        className="type-body inline-flex items-center justify-center rounded-full bg-[var(--btn-primary-bg)] px-5 py-2 font-semibold text-[var(--btn-primary-fg)] shadow-[var(--shadow-sm)] outline-none transition-colors hover:opacity-90 focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
      >
        {t("signIn")}
      </Link>
    </div>
  );
}
