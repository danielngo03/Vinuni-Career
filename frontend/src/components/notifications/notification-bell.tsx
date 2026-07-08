"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { Link, usePathname } from "@/i18n/navigation";
import { useAuthStore } from "@/stores/auth-store";
import { notificationsApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import { UNREAD_COUNT_KEY } from "./query-keys";
import { NotificationCenter } from "./notification-center";

/**
 * Topbar notifications trigger + unread badge + the notification center panel.
 *
 * The badge polls `unread-count` every ~45s (and refetches on window focus) and
 * shares its cache with the popover so optimistic mark-read updates both at once.
 * The badge is hidden at zero. The panel is anchored under the trigger.
 *
 * `variant="labeled"` renders the workspace pill (icon + label + dark count
 * chip); the default `icon` form stays for compact/marketplace headers.
 */
export function NotificationBell({
  variant = "icon",
  href,
}: {
  variant?: "icon" | "labeled";
  href?: string;
}) {
  const t = useTranslations("notifications");
  const tNav = useTranslations("nav");
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const authed = useAuthStore((s) => s.status === "authenticated");

  const { data: unreadCount = 0 } = useQuery({
    queryKey: UNREAD_COUNT_KEY,
    queryFn: () => notificationsApi.unreadCount(),
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
    ? `${tNav("notifications")} — ${t("badgeLabel", { count: unreadCount })}`
    : tNav("notifications");

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
      <Bell
        aria-hidden
        strokeWidth={1.8}
        className={cn(
          variant === "labeled" ? "size-4" : "size-5",
          active ? "text-white" : "text-[var(--text-secondary)]",
        )}
      />
      {variant === "labeled" && (
        <span className="hidden lg:inline">{tNav("notifications")}</span>
      )}
      {hasUnread && (
        <span
          aria-hidden
          className={cn(
            variant === "labeled"
              ? "flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-[11px] font-bold leading-none"
              : "absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-[10px] font-bold leading-none",
            active && variant === "labeled"
              ? "bg-white text-[var(--text-primary)]"
              : variant === "labeled"
                ? "bg-[var(--text-primary)] text-[var(--text-inverted)]"
                : "bg-[var(--brand-red)] text-white",
          )}
        >
          {display}
        </span>
      )}
    </>
  );

  if (href) {
    return (
      <Link href={href} aria-label={ariaLabel} className={variant === "labeled" ? labeledClassName : iconClassName}>
        {content}
      </Link>
    );
  }

  return (
    <div className="relative inline-flex">
      {variant === "labeled" ? (
        <button
          type="button"
          aria-label={ariaLabel}
          aria-haspopup="dialog"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
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
          onClick={() => setOpen((v) => !v)}
          className={iconClassName}
        >
          {content}
        </button>
      )}

      <NotificationCenter open={open} onClose={() => setOpen(false)} />
    </div>
  );
}
