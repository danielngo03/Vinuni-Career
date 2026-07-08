"use client";

import { useCallback, useEffect, useRef } from "react";
import { X } from "@phosphor-icons/react";

const FOCUSABLE =
  'a[href],button:not([disabled]),textarea,input,select,[tabindex]:not([tabindex="-1"])';

/**
 * In-panel slide-in overlay that surfaces the conversation-history list on
 * layouts without the persistent desktop rail (mobile, tablet, and the
 * collapsed/default chat panel). It is anchored inside the chat window body
 * (not a full-page portal) so the assistant header stays visible.
 *
 * Behaves like a modal drawer: focus is trapped inside, Escape closes it, and
 * focus returns to the trigger on close.
 */
export function SessionHistorySheet({
  open,
  title,
  closeLabel,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  closeLabel: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key === "Tab" && panelRef.current) {
        const nodes = Array.from(
          panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE),
        ).filter((n) => n.offsetParent !== null);
        if (nodes.length === 0) return;
        const first = nodes[0]!;
        const last = nodes[nodes.length - 1]!;
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    },
    [onClose],
  );

  useEffect(() => {
    if (!open) return;
    previouslyFocused.current = document.activeElement as HTMLElement | null;
    document.addEventListener("keydown", handleKeyDown);
    const id = window.setTimeout(() => {
      const target =
        panelRef.current?.querySelector<HTMLElement>(FOCUSABLE) ??
        panelRef.current;
      target?.focus();
    }, 0);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      window.clearTimeout(id);
      previouslyFocused.current?.focus?.();
    };
  }, [open, handleKeyDown]);

  if (!open) return null;

  return (
    <div className="absolute inset-0 z-20 flex">
      <div
        className="absolute inset-0 bg-black/25 backdrop-blur-[2px]"
        onClick={onClose}
        aria-hidden
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className="relative flex h-full w-[min(88%,300px)] flex-col border-r border-[var(--glass-border)] bg-[var(--glass-surface-heavy)] shadow-[0_8px_40px_rgba(11,34,57,0.18)] outline-none animate-in slide-in-from-left-2 duration-200"
      >
        <div className="flex items-center gap-2 border-b border-[var(--glass-border)] px-3 py-2.5">
          <span className="min-w-0 flex-1 truncate text-sm font-bold text-[var(--text-primary)]">
            {title}
          </span>
          <button
            type="button"
            onClick={onClose}
            aria-label={closeLabel}
            className="shrink-0 rounded-lg p-1 text-[var(--text-muted)] outline-none transition-colors hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
          >
            <X aria-hidden weight="bold" className="size-4" />
          </button>
        </div>
        <div className="flex min-h-0 flex-1 flex-col overflow-y-auto p-3">
          {children}
        </div>
      </div>
    </div>
  );
}
