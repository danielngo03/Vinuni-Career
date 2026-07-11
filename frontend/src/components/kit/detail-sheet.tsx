"use client";

import * as React from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * DetailSheet — the right-edge detail/edit drawer of the v10 system. Every
 * record surface (job, candidate, campaign, partner…) opens one: a sticky
 * header (avatar/title/subtitle + status + actions), a scrollable sectioned
 * body, and an optional sticky footer for primary actions. Escape + overlay
 * click close; body scroll is locked while open.
 *
 * Compose the body from {@link DetailSheetSection} blocks.
 */
export function DetailSheet({
  open,
  onClose,
  title,
  subtitle,
  status,
  avatar,
  headerActions,
  footer,
  width = "md",
  closeLabel = "Close",
  ariaLabel,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  /** Status chip / badges rendered under the title. */
  status?: React.ReactNode;
  /** Leading avatar / logo block. */
  avatar?: React.ReactNode;
  /** Icon buttons / menu rendered top-right of the header. */
  headerActions?: React.ReactNode;
  /** Sticky footer (primary/secondary actions). */
  footer?: React.ReactNode;
  width?: "md" | "lg";
  closeLabel?: string;
  ariaLabel?: string;
  children: React.ReactNode;
}) {
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";
    const id = window.setTimeout(() => ref.current?.focus(), 0);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      window.clearTimeout(id);
    };
  }, [open, onClose]);

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div className="fixed inset-0 z-50">
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-[2px] animate-in fade-in-0"
        onClick={onClose}
        aria-hidden
      />
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label={ariaLabel ?? (typeof title === "string" ? title : undefined)}
        tabIndex={-1}
        className={cn(
          "absolute flex flex-col bg-card shadow-[var(--shadow-xl)] outline-none",
          // mobile: bottom sheet
          "inset-x-0 bottom-0 max-h-[88vh] rounded-t-2xl animate-in slide-in-from-bottom-4",
          // desktop: right drawer — reset the mobile `inset-x-0` left:0 so the
          // panel pins to the RIGHT edge (left:0 + right:0 + width would pin left)
          "sm:inset-y-0 sm:bottom-auto sm:left-auto sm:right-0 sm:top-0 sm:h-full sm:max-h-none sm:rounded-none sm:border-l sm:border-border sm:animate-in sm:slide-in-from-right-8",
          width === "lg" ? "sm:w-[600px]" : "sm:w-[480px]",
        )}
      >
        {/* Header */}
        <div className="flex shrink-0 items-start gap-3 border-b border-border px-5 py-4">
          {avatar && <div className="shrink-0">{avatar}</div>}
          <div className="min-w-0 flex-1">
            <div className="type-h3 truncate text-foreground">{title}</div>
            {subtitle && (
              <div className="type-small mt-0.5 truncate text-muted-foreground">{subtitle}</div>
            )}
            {status && <div className="mt-2 flex flex-wrap items-center gap-1.5">{status}</div>}
          </div>
          <div className="flex shrink-0 items-center gap-1">
            {headerActions}
            <button
              type="button"
              onClick={onClose}
              aria-label={closeLabel}
              className="rounded-lg p-1.5 text-muted-foreground outline-none transition-colors hover:bg-[var(--bg-subtle)] hover:text-foreground focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
            >
              <X aria-hidden className="size-5" strokeWidth={1.8} />
            </button>
          </div>
        </div>

        {/* Scroll body */}
        <div className="scrollbar-thin min-h-0 flex-1 overflow-y-auto">{children}</div>

        {/* Footer */}
        {footer && (
          <div className="flex shrink-0 items-center justify-end gap-2 border-t border-border bg-card px-5 py-3">
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}

/** A titled section inside a {@link DetailSheet} body. */
export function DetailSheetSection({
  title,
  action,
  className,
  children,
}: {
  title?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section className={cn("border-b border-border px-5 py-4 last:border-b-0", className)}>
      {(title || action) && (
        <div className="mb-2.5 flex items-center justify-between gap-2">
          {title && (
            <h3 className="text-[0.6875rem] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
              {title}
            </h3>
          )}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

/** Label/value row for detail sheets. */
export function DetailRow({
  label,
  children,
  className,
}: {
  label: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex items-baseline justify-between gap-4 py-1.5", className)}>
      <dt className="type-small shrink-0 text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-right text-[0.8125rem] font-medium text-foreground">{children}</dd>
    </div>
  );
}
