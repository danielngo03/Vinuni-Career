"use client";

import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { X } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";

export interface SheetProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  /** Right drawer on desktop; bottom sheet on mobile (DESIGN.md §10). */
  side?: "right" | "left";
  closeLabel?: string;
  /**
   * Desktop drawer width. `md` (default, 380px) suits nav/quick panels; `lg`
   * (up to ~460px) suits denser analysis dashboards.
   */
  size?: "md" | "lg";
  /**
   * When `false`, the dim overlay does NOT blur what's behind it — so the page
   * (e.g. a job description beside a right drawer) stays readable while the
   * drawer is open. Defaults to `true` for the frosted full-attention pattern.
   */
  overlayBlur?: boolean;
  /** Optional extra classes for the panel surface (theme-aware overrides). */
  panelClassName?: string;
}

const SIZE_CLASS: Record<NonNullable<SheetProps["size"]>, string> = {
  md: "sm:w-[380px]",
  lg: "sm:w-[420px] lg:w-[460px]",
};

const FOCUSABLE =
  'a[href],area[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

/**
 * Slide-in panel with Escape, scroll lock, click-outside, a focus trap, and
 * focus restoration. On mobile it presents as a bottom sheet (per DESIGN.md
 * mobile pattern). Glass is intentional here — slide-in panels are one of the
 * two surfaces where translucency is allowed (DESIGN.md §1.1.1) — but the tokens
 * are theme-aware so it works in dark mode too.
 */
export function Sheet({
  open,
  onClose,
  title,
  children,
  side = "right",
  closeLabel = "Close",
  size = "md",
  overlayBlur = true,
  panelClassName,
}: SheetProps) {
  const ref = useRef<HTMLDivElement>(null);
  // Keep the latest onClose without re-running the trap/scroll effect (which
  // would re-capture focus on every parent render for inline handlers).
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!open) return;
    // Restore focus to whatever was focused before the sheet opened.
    const previouslyFocused =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onCloseRef.current();
        return;
      }
      if (e.key !== "Tab") return;
      // Trap focus inside the panel.
      const panel = ref.current;
      if (!panel) return;
      const focusable = Array.from(
        panel.querySelectorAll<HTMLElement>(FOCUSABLE),
      ).filter((el) => el.offsetParent !== null || el === panel);
      if (focusable.length === 0) {
        e.preventDefault();
        panel.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (!first || !last) return;
      const active = document.activeElement;
      if (e.shiftKey) {
        if (active === first || active === panel) {
          e.preventDefault();
          last.focus();
        }
      } else if (active === last) {
        e.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKey);
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";
    const id = window.setTimeout(() => ref.current?.focus(), 0);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      window.clearTimeout(id);
      previouslyFocused?.focus?.();
    };
  }, [open]);

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div className="fixed inset-0 z-50">
      <div
        className={cn(
          "absolute inset-0 bg-black/40",
          overlayBlur && "backdrop-blur-sm",
        )}
        onClick={onClose}
        aria-hidden
      />
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className={cn(
          "absolute flex flex-col border border-[var(--glass-border-strong)] bg-[var(--glass-surface-heavy)] shadow-[0_20px_60px_rgba(11,34,57,0.16)] backdrop-blur-xl outline-none",
          // Mobile: bottom sheet
          "inset-x-0 bottom-0 max-h-[85vh] rounded-t-2xl",
          // Desktop: side drawer
          "sm:inset-y-0 sm:bottom-auto sm:top-0 sm:h-full sm:max-h-none sm:rounded-none",
          SIZE_CLASS[size],
          side === "right" ? "sm:right-0" : "sm:left-0",
          panelClassName,
        )}
      >
        <div className="flex items-center justify-between border-b border-[var(--glass-border)] px-5 py-4">
          {title && (
            <h2 className="text-base font-bold text-[var(--text-primary)]">
              {title}
            </h2>
          )}
          <button
            type="button"
            onClick={onClose}
            aria-label={closeLabel}
            className="ml-auto rounded-lg p-1.5 text-[var(--text-muted)] outline-none transition-colors hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
          >
            <X aria-hidden weight="bold" className="size-5" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
