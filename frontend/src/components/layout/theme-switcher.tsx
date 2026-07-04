"use client";

import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, Monitor, Moon, Sun } from "lucide-react";
import { useTranslations } from "next-intl";
import { useTheme, type ThemePref } from "@/lib/theme";
import { cn } from "@/lib/utils";

const THEME_OPTIONS: Array<{
  value: ThemePref;
  labelKey: "themeLight" | "themeDark" | "themeSystem";
  icon: typeof Sun;
}> = [
  { value: "light", labelKey: "themeLight", icon: Sun },
  { value: "dark", labelKey: "themeDark", icon: Moon },
  { value: "system", labelKey: "themeSystem", icon: Monitor },
];

type ThemeSwitcherProps = {
  hoverCompact?: boolean;
  forceLabel?: boolean;
};

export function ThemeSwitcher({
  hoverCompact = false,
  forceLabel = false,
}: ThemeSwitcherProps) {
  const tNav = useTranslations("nav");
  const { theme, setTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;

    function onMouseDown(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    }

    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    }

    document.addEventListener("mousedown", onMouseDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onMouseDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const current = THEME_OPTIONS.find((option) => option.value === theme) ?? THEME_OPTIONS[0]!;
  const CurrentIcon = current.icon;

  function chooseTheme(next: ThemePref) {
    setTheme(next);
    setOpen(false);
  }

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={tNav("theme")}
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "group inline-flex h-9 items-center rounded-full border text-[0.8125rem] font-semibold outline-none transition-all duration-200 focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40",
          hoverCompact
            ? "w-9 justify-center gap-0 overflow-hidden px-0 hover:w-[118px] hover:justify-start hover:gap-2 hover:px-3.5 focus:w-[118px] focus:justify-start focus:gap-2 focus:px-3.5"
            : "gap-2 px-3.5",
          open
            ? cn(
                "border-[var(--text-primary)] bg-[var(--text-primary)] text-white shadow-[0_8px_18px_rgba(0,0,0,0.12)]",
                hoverCompact && "w-[118px] justify-start gap-2 px-3.5",
              )
            : "border-[var(--border-default)] bg-[var(--surface-card)] text-[var(--text-primary)] hover:border-[var(--border-strong)] hover:bg-[var(--bg-subtle)]",
        )}
      >
        <CurrentIcon
          aria-hidden
          strokeWidth={1.8}
          className={cn("size-4", open ? "text-white" : "text-[var(--text-secondary)]")}
        />
        <span
          className={cn(
            "whitespace-nowrap transition-all duration-200",
            hoverCompact
              ? "max-w-0 overflow-hidden opacity-0 group-hover:max-w-[66px] group-hover:opacity-100 group-focus-within:max-w-[66px] group-focus-within:opacity-100"
              : forceLabel
                ? ""
                : "hidden lg:inline",
            open && hoverCompact && "max-w-[66px] opacity-100",
          )}
        >
          {tNav(current.labelKey)}
        </span>
        <ChevronDown
          aria-hidden
          strokeWidth={2}
          className={cn(
            "size-3.5 shrink-0 text-[var(--text-muted)] transition-all",
            hoverCompact
              ? "max-w-0 opacity-0 group-hover:max-w-3.5 group-hover:opacity-100 group-focus-within:max-w-3.5 group-focus-within:opacity-100"
              : forceLabel
                ? ""
                : "hidden lg:inline",
            open && "rotate-180 text-white/80",
            open && hoverCompact && "max-w-3.5 opacity-100",
          )}
        />
      </button>

      {open && (
        <div
          role="listbox"
          aria-label={tNav("theme")}
          className="absolute right-0 top-[calc(100%+8px)] z-50 w-48 overflow-hidden rounded-xl border border-[var(--border-default)] bg-[var(--surface-dropdown)] p-1.5 shadow-[var(--shadow-lg)]"
        >
          {THEME_OPTIONS.map((option) => {
            const selected = option.value === theme;
            const Icon = option.icon;
            return (
              <button
                key={option.value}
                type="button"
                role="option"
                aria-selected={selected}
                onClick={() => chooseTheme(option.value)}
                className={cn(
                  "flex w-full cursor-pointer items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm outline-none transition-colors",
                  "hover:bg-[var(--bg-subtle)] focus-visible:bg-[var(--bg-subtle)]",
                  selected
                    ? "font-semibold text-[var(--text-primary)]"
                    : "font-medium text-[var(--text-secondary)]",
                )}
              >
                <Icon
                  aria-hidden
                  strokeWidth={1.8}
                  className="size-[18px] shrink-0 text-[var(--text-muted)]"
                />
                <span className="flex-1 text-left">{tNav(option.labelKey)}</span>
                {selected && (
                  <Check
                    aria-hidden
                    strokeWidth={2.2}
                    className="size-3.5 shrink-0 text-[var(--text-primary)]"
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
