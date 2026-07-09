"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Mail } from "lucide-react";
import { Link, usePathname } from "@/i18n/navigation";
import { useAuthStore } from "@/stores/auth-store";
import { messagingApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import { MESSAGING_UNREAD_KEY } from "./query-keys";
import { MessagingCenter } from "./messaging-center";
import { useMessagingRealtime } from "./use-messaging-socket";

/**
 * Shared topbar messaging entry: an envelope icon + a polled unread badge,
 * mirroring the notification bell. The badge polls `GET /messaging/unread-count`
 * every ~45s, on window focus, and refreshes when the center opens. It shares
 * the `MESSAGING_UNREAD_KEY` cache with mark-read/mute mutations so the count
 * stays in sync. Available to student, partner, and university topbars.
 *
 * `variant="labeled"` renders the workspace pill (icon + label + dark count
 * chip); the default `icon` form stays for compact/marketplace headers.
 */
export function MessagingBell({
  variant = "icon",
  href,
}: {
  variant?: "icon" | "labeled";
  href?: string;
}) {
  const t = useTranslations("messaging");
  const tNav = useTranslations("nav");
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const authed = useAuthStore((s) => s.status === "authenticated");

  // One app-level realtime connection (ref-counted) that keeps the badge + open
  // lists live; polling stays as the resilient fallback.
  useMessagingRealtime();

  const { data: unreadCount = 0, refetch } = useQuery({
    queryKey: MESSAGING_UNREAD_KEY,
    queryFn: () => messagingApi.unreadCount(),
    enabled: authed,
    refetchInterval: 45_000,
    refetchOnWindowFocus: true,
    staleTime: 30_000,
  });

  const hasUnread = unreadCount > 0;
  const display = unreadCount > 99 ? "99+" : String(unreadCount);
  const active = href
    ? pathname === href || pathname.startsWith(`${href}/`)
    : open;
  const ariaLabel = hasUnread
    ? `${t("title")} — ${t("badgeLabel", { count: unreadCount })}`
    : t("title");

  function onOpen() {
    setOpen(true);
    void refetch();
  }

  function onNavigate() {
    void refetch();
  }

  const labeledClassName = cn(
    "inline-flex h-9 items-center gap-2 rounded-full border px-3.5 text-[0.8125rem] font-semibold outline-none transition-colors duration-200 focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40",
    active
      ? "border-[var(--text-primary)] bg-[var(--text-primary)] text-white shadow-[0_8px_18px_rgba(0,0,0,0.12)] hover:bg-black"
      : "border-[var(--border-default)] bg-[var(--surface-card)] text-[var(--text-primary)] hover:border-[var(--border-strong)] hover:bg-[var(--bg-subtle)]",
  );
  const iconClassName = cn(
    "relative rounded-lg p-2 outline-none transition-colors duration-200 focus-visible:ring-2 focus-visible:ring-[var(--brand-mid-blue)]",
    active
      ? "bg-[var(--text-primary)] text-white"
      : "text-[var(--text-secondary)] hover:bg-[var(--bg-subtle)]",
  );

  const content = (
    <>
      <Mail
        aria-hidden
        strokeWidth={1.8}
        className={cn(
          variant === "labeled" ? "size-4" : "size-5",
          active ? "text-white" : "text-[var(--text-secondary)]",
        )}
      />
      {variant === "labeled" && (
        <span className="hidden lg:inline">{tNav("messages")}</span>
      )}
      {hasUnread && (
        <span
          aria-hidden
          className={
            variant === "labeled"
              ? cn(
                  "flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-[11px] font-bold leading-none",
                  active
                    ? "bg-white text-[var(--text-primary)]"
                    : "bg-[var(--text-primary)] text-[var(--text-inverted)]",
                )
              : "absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-[var(--brand-red)] px-1 text-[10px] font-bold leading-none text-white"
          }
        >
          {display}
        </span>
      )}
    </>
  );

  if (href) {
    return (
      <Link
        href={href}
        aria-label={ariaLabel}
        onClick={onNavigate}
        className={variant === "labeled" ? labeledClassName : iconClassName}
      >
        {content}
      </Link>
    );
  }

  return (
    <>
      {variant === "labeled" ? (
        <button
          type="button"
          aria-label={ariaLabel}
          aria-haspopup="dialog"
          aria-expanded={open}
          onClick={onOpen}
          className={labeledClassName}
        >
          {content}
        </button>
      ) : (
        <button
          type="button"
          aria-label={ariaLabel}
          aria-haspopup="dialog"
          aria-expanded={open}
          onClick={onOpen}
          className={iconClassName}
        >
          {content}
        </button>
      )}

      <MessagingCenter open={open} onClose={() => setOpen(false)} />
    </>
  );
}
