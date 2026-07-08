"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowRight, CaretDown } from "@phosphor-icons/react";
import { Link, usePathname } from "@/i18n/navigation";
import { cn } from "@/lib/utils";

export function usePublicMegaMenuState() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [hasOpened, setHasOpened] = useState(false);
  const triggerRef = useRef<HTMLAnchorElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  function openMenu() {
    if (closeTimer.current) clearTimeout(closeTimer.current);
    setHasOpened(true);
    setOpen(true);
  }

  function scheduleClose() {
    closeTimer.current = setTimeout(() => setOpen(false), 200);
  }

  function cancelClose() {
    if (closeTimer.current) clearTimeout(closeTimer.current);
  }

  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  function onPanelKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (e.key !== "Tab") return;
    const focusables = panelRef.current?.querySelectorAll<HTMLElement>(
      "a[href], button:not([disabled])",
    );
    const first = focusables?.[0];
    const last = focusables?.[focusables.length - 1];
    if (!first || !last) return;
    const active = document.activeElement;
    if (e.shiftKey && (active === first || active === triggerRef.current)) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && active === last) {
      e.preventDefault();
      triggerRef.current?.focus();
    }
  }

  return {
    open,
    hasOpened,
    triggerRef,
    panelRef,
    openMenu,
    scheduleClose,
    cancelClose,
    onPanelKeyDown,
  };
}

export function PublicMegaMenuFrame({
  menu,
  href,
  label,
  panelId,
  panelLabel,
  isActive,
  children,
}: {
  menu: ReturnType<typeof usePublicMegaMenuState>;
  href: string;
  label: string;
  panelId: string;
  panelLabel: string;
  isActive: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="relative h-full">
      <Link
        ref={menu.triggerRef}
        href={href}
        onMouseEnter={menu.openMenu}
        onMouseLeave={menu.scheduleClose}
        onFocus={menu.openMenu}
        aria-haspopup="true"
        aria-expanded={menu.open}
        aria-current={isActive ? "page" : undefined}
        aria-controls={panelId}
        className={cn(
          "relative inline-flex h-full shrink-0 items-center gap-1 whitespace-nowrap px-0 text-sm font-semibold outline-none transition-colors",
          "focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40",
          "after:pointer-events-none after:absolute after:inset-x-0 after:bottom-0 after:h-[2px] after:origin-center after:rounded-full after:bg-[var(--brand-primary)] after:transition-transform after:duration-200",
          menu.open || isActive
            ? "text-[var(--brand-primary)] after:scale-x-100"
            : "text-[var(--text-secondary)] after:scale-x-0 hover:text-[var(--brand-navy)] hover:after:scale-x-100",
        )}
      >
        {label}
        <CaretDown
          aria-hidden
          weight="bold"
          className={cn(
            "size-3.5 transition-transform duration-200",
            menu.open && "rotate-180",
          )}
        />
      </Link>

      {menu.open && (
        <div
          ref={menu.panelRef}
          id={panelId}
          role="region"
          aria-label={panelLabel}
          onKeyDown={menu.onPanelKeyDown}
          onMouseEnter={menu.cancelClose}
          onMouseLeave={menu.scheduleClose}
          className="fixed left-1/2 top-[68px] z-40 w-[min(calc(100vw-32px),1120px)] -translate-x-1/2"
        >
          <div className="h-2" />
          <div className="overflow-hidden rounded-[18px] border border-[var(--border-default)] bg-[var(--surface-card)] shadow-[0_18px_50px_rgba(11,34,57,0.13),0_4px_14px_rgba(11,34,57,0.05)]">
            {children}
          </div>
        </div>
      )}
    </div>
  );
}

export function MegaHeading({
  id,
  className,
  children,
}: {
  id: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <h3
      id={id}
      className={cn(
        "text-[11px] font-bold uppercase tracking-wide text-[var(--text-muted)]",
        className,
      )}
    >
      {children}
    </h3>
  );
}

export function FooterLink({ href, label }: { href: string; label: string }) {
  return (
    <Link
      href={href}
      className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-[var(--brand-primary)] outline-none hover:underline focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
    >
      {label}
      <ArrowRight aria-hidden weight="bold" className="size-3.5" />
    </Link>
  );
}

export function InlineArrow({ children }: { children: React.ReactNode }) {
  return (
    <span className="mt-auto inline-flex items-center gap-1 text-sm font-semibold text-[var(--brand-primary)]">
      {children}
      <ArrowRight aria-hidden weight="bold" className="size-3.5" />
    </span>
  );
}

export const listLinkClass =
  "group flex items-center gap-2.5 rounded-xl px-2.5 py-2 text-sm font-medium text-[var(--text-secondary)] outline-none transition-colors hover:bg-[var(--surface-secondary)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40";

export const pillLinkClass =
  "inline-flex min-h-9 items-center rounded-full border border-[var(--border-default)] bg-[var(--surface-card)] px-3 text-sm font-semibold text-[var(--text-secondary)] outline-none transition-colors hover:border-[var(--brand-primary)]/50 hover:text-[var(--brand-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40";

export const spotlightCardClass =
  "group mt-3 flex min-h-[180px] flex-col gap-2 rounded-2xl border border-[var(--border-default)] bg-[var(--surface-secondary)] p-4 outline-none transition-colors hover:border-[var(--brand-primary)]/60 hover:bg-[var(--surface-card)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]";
