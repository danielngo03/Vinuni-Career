"use client";

import { CircleNotch } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { useAuthStore, type Persona } from "@/stores/auth-store";
import { AccountMenu } from "./account-menu";
import { SavedButton } from "./saved-button";
import { HeaderAiButton } from "./header-ai-button";
import { NotificationBell } from "@/components/notifications/notification-bell";
import { MessagingBell } from "@/components/messaging/messaging-bell";

export interface PersonaAccountRoutes {
  dashboardHref: string;
  profileHref: string;
  applicationsHref: string;
  invitationsHref: string;
  notificationsHref: string;
  messagesHref: string;
  savedHref: string;
  settingsHref: string;
  billingHref: string;
}

export function getPersonaAccountRoutes(
  persona: Persona | null | undefined,
): PersonaAccountRoutes {
  const normalized = persona ?? "student";
  return {
    dashboardHref: `/${normalized}/dashboard`,
    profileHref: `/${normalized}/profile`,
    applicationsHref: `/${normalized}/applications`,
    invitationsHref: `/${normalized}/invitations`,
    notificationsHref: `/${normalized}/notifications`,
    messagesHref: `/${normalized}/messages`,
    savedHref: `/${normalized}/saved`,
    settingsHref: `/${normalized}/settings`,
    billingHref: `/${normalized}/billing`,
  };
}

/**
 * Auth-aware right-hand actions for the shared marketplace header. Used by both
 * the public shell and the signed-in student shell so the two never drift:
 *
 *  - guest        → login / register.
 *  - student      → notifications, messages, saved, AI assistant, and the
 *                   account menu (Overview / Profile / Applications / …).
 *  - other authed → account menu only (partner/university rarely browse here).
 *
 * Overview/Profile/Settings live inside the account menu (avatar), not as a
 * standalone nav pill.
 */
export function PublicAuthActions() {
  const tNav = useTranslations("nav");
  const tCommon = useTranslations("common");
  const status = useAuthStore((s) => s.status);
  const persona = useAuthStore((s) => s.user?.persona);

  if (status === "unknown") {
    return (
      <div
        aria-label={tCommon("loading")}
        className="hidden h-9 w-[168px] items-center justify-end gap-2 text-[var(--text-muted)] min-[1360px]:flex"
      >
        <CircleNotch aria-hidden className="size-4 animate-spin" />
        <span className="h-2 w-20 rounded-full bg-[var(--bg-subtle)]" />
      </div>
    );
  }

  if (status === "authenticated") {
    const routes = getPersonaAccountRoutes(persona);
    const isStudent = (persona ?? "student") === "student";
    return (
      <div className="hidden items-center gap-1.5 min-[1360px]:flex">
        {isStudent && (
          <>
            <NotificationBell href={routes.notificationsHref} />
            <MessagingBell href={routes.messagesHref} />
            <SavedButton variant="icon" />
            <HeaderAiButton />
          </>
        )}
        <AccountMenu
          settingsHref={routes.settingsHref}
          billingHref={routes.billingHref}
          dashboardHref={routes.dashboardHref}
          profileHref={isStudent ? routes.profileHref : undefined}
          applicationsHref={isStudent ? routes.applicationsHref : undefined}
          invitationsHref={isStudent ? routes.invitationsHref : undefined}
          showFeedback={isStudent}
        />
      </div>
    );
  }

  return (
    <>
      <Link
        href="/auth/login"
        className="hidden h-9 items-center rounded-full px-3.5 text-sm font-semibold text-[var(--text-secondary)] outline-none transition-colors hover:bg-[var(--bg-subtle)] hover:text-[var(--brand-navy)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40 min-[1360px]:inline-flex"
      >
        {tNav("login")}
      </Link>
      <Link
        href="/auth/register"
        className="hidden h-9 items-center rounded-full bg-[var(--brand-primary)] px-5 text-sm font-semibold text-white shadow-[var(--shadow-brand)] outline-none transition-colors hover:bg-[var(--blue-700)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40 min-[1360px]:inline-flex"
      >
        {tNav("register")}
      </Link>
    </>
  );
}
