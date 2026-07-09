"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import Image from "next/image";
import {
  ChevronDown,
  ClipboardList,
  CreditCard,
  LayoutGrid,
  LifeBuoy,
  LogOut,
  MailOpen,
  Settings,
  UserRound,
} from "lucide-react";
import { Link, useRouter, usePathname } from "@/i18n/navigation";
import { useAuthStore } from "@/stores/auth-store";
import { cn } from "@/lib/utils";
import { FeedbackModal } from "./feedback-modal";
import { HelpSupportModal } from "./help-support-modal";

/**
 * Authenticated account dropdown for the marketplace-style header (student
 * top-nav shell). Avatar trigger opens a small menu with identity, settings,
 * and sign-out — replacing the sidebar's footer block without an admin shell.
 *
 * A11y: trigger exposes `aria-haspopup="menu"`/`aria-expanded`; the panel is a
 * `role="menu"`; Escape closes and returns focus to the trigger; an outside
 * click or route change also closes it. Color is never the only signal — every
 * item carries an icon + label.
 */
export function AccountMenu({
  settingsHref,
  billingHref,
  dashboardHref,
  profileHref,
  applicationsHref,
  invitationsHref,
  showFeedback = false,
  showHelpSupport = false,
  showName = false,
}: {
  settingsHref: string;
  billingHref?: string;
  /** When set, an "Overview / Tổng quan" shortcut is shown at the top. */
  dashboardHref?: string;
  /** When set, a "Profile / Hồ sơ" shortcut is shown. */
  profileHref?: string;
  /** When set, an "Applications / Đơn ứng tuyển" shortcut is shown. */
  applicationsHref?: string;
  /** When set, an "Invitations / Lời mời ứng tuyển" shortcut is shown. */
  invitationsHref?: string;
  /** When true, a "Feedback & support" item opens the feedback modal. */
  showFeedback?: boolean;
  /** When true, a "Help & support" item opens the workspace support panel. */
  showHelpSupport?: boolean;
  /** Workspace topbar form: avatar + name + caret in a quiet pill. */
  showName?: boolean;
}) {
  const tNav = useTranslations("nav");
  const tRail = useTranslations("rail");
  const user = useAuthStore((s) => s.user);
  const signOut = useAuthStore((s) => s.signOut);
  const router = useRouter();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  const initial = user?.name?.charAt(0)?.toUpperCase() ?? "?";

  // Close on outside click + Escape (restoring focus to the trigger).
  useEffect(() => {
    if (!open) return;
    function onPointer(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    }
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // Close when the route changes (e.g. after picking Settings).
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  async function handleSignOut() {
    setOpen(false);
    await signOut();
    router.replace("/");
  }

  const menuItemClass = cn(
    "flex w-full items-center gap-2 rounded-lg px-2.5 py-[0.4375rem] text-left text-[0.8125rem] font-medium text-[var(--text-secondary)] outline-none transition-colors",
    "hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus-visible:bg-[var(--bg-subtle)] focus-visible:text-[var(--text-primary)]",
  );
  const dangerMenuItemClass = cn(
    "flex w-full items-center gap-2 rounded-lg px-2.5 py-[0.4375rem] text-left text-[0.8125rem] font-medium text-[var(--text-secondary)] outline-none transition-colors",
    "hover:bg-[var(--bg-subtle)] hover:text-[var(--brand-red)] focus-visible:bg-[var(--bg-subtle)] focus-visible:text-[var(--brand-red)]",
  );
  const menuIconClass = "size-4 shrink-0";

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={user?.name ?? tNav("userMenu")}
        title={user?.name ?? undefined}
        className={cn(
          "outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40",
          showName
            ? "flex items-center gap-2 rounded-full py-0.5 pl-0.5 pr-2 hover:bg-[var(--bg-subtle)]"
            : "flex size-9 items-center justify-center rounded-full bg-[var(--text-primary)] text-sm font-bold text-[var(--text-inverted)] focus-visible:ring-offset-2",
        )}
      >
        {showName ? (
          <>
            <span
              aria-hidden
              className="relative flex size-7 shrink-0 items-center justify-center overflow-hidden rounded-full bg-[var(--bg-muted)] text-[0.8125rem] font-bold text-[var(--text-primary)]"
            >
              {user?.avatarUrl ? (
                <Image src={user.avatarUrl} alt="" fill sizes="28px" className="object-cover" aria-hidden />
              ) : (
                initial
              )}
            </span>
            <span className="hidden max-w-[140px] truncate text-[0.78rem] font-semibold text-[var(--text-primary)] lg:inline">
              {user?.name}
            </span>
            <ChevronDown
              aria-hidden
              strokeWidth={2}
              className={cn(
                "hidden size-3.5 shrink-0 text-[var(--text-muted)] transition-transform lg:inline",
                open && "rotate-180",
              )}
            />
          </>
        ) : (
          <span aria-hidden>{initial}</span>
        )}
      </button>

      {open && (
        <div
          role="menu"
          aria-label={tNav("userMenu")}
          className="absolute right-0 top-[calc(100%+8px)] z-40 w-56 overflow-hidden rounded-xl border border-[var(--border-default)] bg-[var(--surface-dropdown)] p-1 shadow-[var(--shadow-lg)]"
        >
          <div className="px-2.5 py-1.5">
            <p className="truncate text-[0.8125rem] font-semibold text-[var(--text-primary)]">
              {user?.name ?? tNav("userMenu")}
            </p>
            {user?.email && (
              <p className="truncate text-[0.6875rem] text-[var(--text-muted)]">
                {user.email}
              </p>
            )}
          </div>

          <div className="my-1 border-t border-[var(--border-subtle)]" />

          {dashboardHref && (
            <Link
              href={dashboardHref}
              role="menuitem"
              onClick={() => setOpen(false)}
              className={menuItemClass}
            >
              <LayoutGrid aria-hidden strokeWidth={1.8} className={menuIconClass} />
              {tNav("dashboard")}
            </Link>
          )}

          {profileHref && (
            <Link
              href={profileHref}
              role="menuitem"
              onClick={() => setOpen(false)}
              className={menuItemClass}
            >
              <UserRound aria-hidden strokeWidth={1.8} className={menuIconClass} />
              {tNav("profile")}
            </Link>
          )}

          {applicationsHref && (
            <Link
              href={applicationsHref}
              role="menuitem"
              onClick={() => setOpen(false)}
              className={menuItemClass}
            >
              <ClipboardList aria-hidden strokeWidth={1.8} className={menuIconClass} />
              {tNav("applications")}
            </Link>
          )}

          {invitationsHref && (
            <Link
              href={invitationsHref}
              role="menuitem"
              onClick={() => setOpen(false)}
              className={menuItemClass}
            >
              <MailOpen aria-hidden strokeWidth={1.8} className={menuIconClass} />
              {tNav("invitations")}
            </Link>
          )}

          {(dashboardHref || profileHref || applicationsHref || invitationsHref) && (
            <div className="my-1 border-t border-[var(--border-subtle)]" />
          )}

          {billingHref && (
            <Link
              href={billingHref}
              role="menuitem"
              onClick={() => setOpen(false)}
              className={menuItemClass}
            >
              <CreditCard aria-hidden strokeWidth={1.8} className={menuIconClass} />
              {tNav("billing")}
            </Link>
          )}

          <Link
            href={settingsHref}
            role="menuitem"
            onClick={() => setOpen(false)}
            className={menuItemClass}
          >
            <Settings aria-hidden strokeWidth={1.8} className={menuIconClass} />
            {tNav("settings")}
          </Link>

          {showFeedback && (
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                setFeedbackOpen(true);
              }}
              className={menuItemClass}
            >
              <LifeBuoy aria-hidden strokeWidth={1.8} className={menuIconClass} />
              {tRail("feedbackLabel")}
            </button>
          )}

          {showHelpSupport && (
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                setHelpOpen(true);
              }}
              className={menuItemClass}
            >
              <LifeBuoy aria-hidden strokeWidth={1.8} className={menuIconClass} />
              {tNav("help")}
            </button>
          )}

          <button
            type="button"
            role="menuitem"
            onClick={handleSignOut}
            className={dangerMenuItemClass}
          >
            <LogOut aria-hidden strokeWidth={1.8} className={menuIconClass} />
            {tNav("logout")}
          </button>
        </div>
      )}

      {(showFeedback || showHelpSupport) && (
        <FeedbackModal open={feedbackOpen} onClose={() => setFeedbackOpen(false)} />
      )}
      {showHelpSupport && (
        <HelpSupportModal
          open={helpOpen}
          onClose={() => setHelpOpen(false)}
          onOpenFeedback={() => setFeedbackOpen(true)}
        />
      )}
    </div>
  );
}
