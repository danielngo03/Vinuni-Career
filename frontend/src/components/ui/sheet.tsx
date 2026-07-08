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
}

/**
 * Slide-in panel with Escape, scroll lock, and click-outside. On mobile it
 * presents as a bottom sheet (per DESIGN.md mobile pattern).
 */
export function Sheet({
  open,
  onClose,
  title,
  children,
  side = "right",
  closeLabel = "Close",
}: SheetProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
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
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
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
          "absolute flex flex-col border border-white/60 bg-white/92 shadow-[0_20px_60px_rgba(11,34,57,0.16)] backdrop-blur-xl outline-none",
          // Mobile: bottom sheet
          "inset-x-0 bottom-0 max-h-[85vh] rounded-t-2xl",
          // Desktop: side drawer
          "sm:inset-y-0 sm:bottom-auto sm:top-0 sm:h-full sm:w-[380px] sm:max-h-none sm:rounded-none",
          side === "right" ? "sm:right-0" : "sm:left-0",
        )}
      >
        <div className="flex items-center justify-between border-b border-white/40 px-5 py-4">
          {title && (
            <h2 className="text-base font-bold text-[var(--text-primary)]">
              {title}
            </h2>
          )}
          <button
            type="button"
            onClick={onClose}
            aria-label={closeLabel}
            className="ml-auto rounded-lg p-1.5 text-[var(--text-muted)] outline-none transition-colors hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)]"
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
