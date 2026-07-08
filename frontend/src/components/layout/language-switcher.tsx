"use client";

import { useEffect, useRef, useState, useTransition } from "react";
import { useLocale, useTranslations } from "next-intl";
import { CaretDown, Check } from "@phosphor-icons/react";
import VN from "country-flag-icons/react/3x2/VN";
import GB from "country-flag-icons/react/3x2/GB";
import { usePathname, useRouter } from "@/i18n/navigation";
import { routing } from "@/i18n/routing";
import { cn } from "@/lib/utils";

type LocaleFlagComponent = typeof VN;

const FLAG_MAP: Record<string, LocaleFlagComponent> = { vi: VN, en: GB };
const LABEL_MAP: Record<string, string> = {
  vi: "Tiếng Việt",
  en: "English",
};

type LanguageSwitcherProps = {
  compact?: boolean;
  hoverCompact?: boolean;
};

export function LanguageSwitcher({
  compact = false,
  hoverCompact = false,
}: LanguageSwitcherProps) {
  const t = useTranslations("common");
  const locale = useLocale();
  const pathname = usePathname();
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  function switchTo(next: string) {
    if (next === locale) { setOpen(false); return; }
    setOpen(false);
    startTransition(() => {
      router.replace(pathname, { locale: next });
    });
  }

  useEffect(() => {
    if (!open) return;
    function onMouseDown(e: MouseEvent) {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onMouseDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onMouseDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const CurrentFlag = FLAG_MAP[locale] ?? VN;
  const currentLabel =
    locale === "vi" ? t("vietnamese") : locale === "en" ? "English" : (LABEL_MAP[locale] ?? locale);

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={t("language")}
        disabled={isPending}
        className={cn(
          "group inline-flex h-9 items-center rounded-full border text-[0.8125rem] font-semibold outline-none transition-all duration-200",
          "border-[var(--border-default)] bg-[var(--surface-card)] text-[var(--text-primary)]",
          "hover:border-[var(--border-strong)] hover:bg-[var(--bg-subtle)]",
          "focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40",
          hoverCompact
            ? "w-9 justify-center gap-0 overflow-hidden px-0 hover:w-[132px] hover:justify-start hover:gap-2 hover:px-3.5 focus:w-[132px] focus:justify-start focus:gap-2 focus:px-3.5"
            : "gap-2 px-3.5",
          open && "border-[var(--text-primary)] bg-[var(--text-primary)] text-white shadow-[0_8px_18px_rgba(0,0,0,0.12)]",
          open && hoverCompact && "w-[132px] justify-start gap-2 px-3.5",
          isPending && "opacity-50",
        )}
      >
        <CurrentFlag
          aria-hidden
          className="h-3.5 w-[18px] shrink-0 rounded-[2px] shadow-[0_0_0_0.5px_rgba(0,0,0,0.12)]"
        />
        <span
          className={cn(
            "whitespace-nowrap transition-all duration-200",
            hoverCompact
              ? "max-w-0 overflow-hidden opacity-0 group-hover:max-w-[84px] group-hover:opacity-100 group-focus-within:max-w-[84px] group-focus-within:opacity-100"
              : compact && "hidden xl:inline",
            open && hoverCompact && "max-w-[84px] opacity-100",
          )}
        >
          {compact ? currentLabel : LABEL_MAP[locale]}
        </span>
        <CaretDown
          aria-hidden
          weight="bold"
          className={cn(
            "size-3 shrink-0 text-[var(--text-muted)] transition-all duration-150",
            hoverCompact &&
              "max-w-0 opacity-0 group-hover:max-w-3 group-hover:opacity-100 group-focus-within:max-w-3 group-focus-within:opacity-100",
            open && "rotate-180 text-white/80",
            open && hoverCompact && "max-w-3 opacity-100",
          )}
        />
      </button>

      {open && (
        <div
          role="listbox"
          aria-label={t("language")}
          className="absolute right-0 top-[calc(100%+8px)] z-50 min-w-[176px] overflow-hidden rounded-xl border border-[var(--border-default)] bg-[var(--surface-dropdown)] p-1.5 shadow-[var(--shadow-lg)]"
        >
          {routing.locales.map((loc) => {
            const Flag = FLAG_MAP[loc] ?? VN;
            const active = loc === locale;
            return (
              <button
                key={loc}
                role="option"
                aria-selected={active}
                type="button"
                lang={loc}
                onClick={() => switchTo(loc)}
                className={cn(
                  "flex w-full cursor-pointer items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm outline-none transition-colors",
                  "hover:bg-[var(--bg-subtle)] focus-visible:bg-[var(--bg-subtle)]",
                  active
                    ? "font-semibold text-[var(--text-primary)]"
                    : "font-medium text-[var(--text-secondary)]",
                )}
              >
                <Flag
                  aria-hidden
                  className="h-4 w-[21px] shrink-0 rounded-[2px] shadow-[0_0_0_0.5px_rgba(0,0,0,0.12)]"
                />
                <span className="flex-1 text-left">{LABEL_MAP[loc] ?? loc}</span>
                {active && (
                  <Check
                    aria-hidden
                    weight="bold"
                    className="size-3.5 shrink-0 text-[var(--brand-primary)]"
                  />
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
