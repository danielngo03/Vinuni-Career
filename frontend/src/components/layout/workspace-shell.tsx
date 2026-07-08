"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { CircleNotch } from "@phosphor-icons/react";
import { HelpCircle } from "lucide-react";
import { Sidebar } from "./sidebar";
import { Topbar } from "./topbar";
import { WorkspaceFooter } from "./workspace-footer";
import { LoginModal } from "./login-modal";
import { BrandMark } from "./brand-mark";
import { FeedbackModal } from "./feedback-modal";
import { HelpSupportModal } from "./help-support-modal";
import { AiChatWindow } from "@/components/ai-assistant/ai-chat-window";
import { Sheet } from "@/components/ui";
import { usePathname, useRouter } from "@/i18n/navigation";
import { readPersistedSidebarCollapsed, useUiStore } from "@/stores/ui-store";
import { useAuthStore, type Persona } from "@/stores/auth-store";
import { cn } from "@/lib/utils";

/**
 * Shared workspace shell for student/partner/university route groups
 * (DESIGN.md §6.1). Responsive: fixed sidebar at >=lg, slide-in drawer below.
 * Skip link + landmark roles for accessibility.
 */
export function WorkspaceShell({
  persona,
  children,
}: {
  persona: Persona;
  children: React.ReactNode;
}) {
  const t = useTranslations("common");
  const tNav = useTranslations("nav");
  const status = useAuthStore((s) => s.status);
  const user = useAuthStore((s) => s.user);
  const {
    mobileNavOpen,
    setMobileNavOpen,
    sidebarCollapsed,
    toggleSidebarCollapsed,
    setSidebarCollapsed,
  } = useUiStore();
  const [aiOpen, setAiOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const pathname = usePathname();
  const router = useRouter();
  const isFullCanvasRoute =
    pathname === `/${persona}/messages` ||
    pathname.startsWith(`/${persona}/messages/`) ||
    pathname === `/${persona}/notifications` ||
    pathname.startsWith(`/${persona}/notifications/`);

  // Route guard: unauthenticated users → login; wrong persona → their workspace.
  // Hydration runs once at app load; while it resolves we show a loading state.
  useEffect(() => {
    if (status === "guest") {
      router.replace(
        `/auth/login?returnTo=${encodeURIComponent(pathname)}`,
      );
      return;
    }
    if (status === "authenticated" && user && user.persona !== persona) {
      router.replace(`/${user.persona}`);
    }
  }, [status, user, persona, pathname, router]);

  // Sync the persisted collapse preference post-mount only, so SSR and the
  // first client render both start expanded and never hydration-mismatch.
  useEffect(() => {
    setSidebarCollapsed(readPersistedSidebarCollapsed());
  }, [setSidebarCollapsed]);

  // Wait for hydration; reject wrong-persona access (persona check is also
  // enforced by backend RBAC, so this is a UX guard only).
  if (status !== "authenticated" || (user && user.persona !== persona)) {
    return (
      <div className="flex min-h-dvh flex-col items-center justify-center gap-4 bg-[var(--bg-subtle)] px-4">
        <BrandMark />
        <div className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
          <CircleNotch
            aria-hidden
            className="size-4 animate-spin text-[var(--brand-primary)]"
          />
          <span role="status">
            {status === "guest" ? t("redirecting") : t("loading")}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div
      className="min-h-dvh bg-[#f7f6f2]"
      style={{
        ["--sidebar-offset" as string]: sidebarCollapsed ? "64px" : "var(--sidebar-width)",
      }}
    >
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[70] focus:rounded-lg focus:bg-[var(--brand-primary)] focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-white"
      >
        {t("skipToContent")}
      </a>

      {/* Desktop sidebar — collapsible icon rail (64px) or full (256px), persisted */}
      <aside
        aria-label={tNav("dashboard")}
        className="fixed inset-y-0 left-0 z-20 hidden transition-[width] duration-200 motion-reduce:transition-none lg:block"
        style={{ width: sidebarCollapsed ? "64px" : "var(--sidebar-width)" }}
      >
        <Sidebar
          persona={persona}
          collapsed={sidebarCollapsed}
          onToggleCollapsed={toggleSidebarCollapsed}
        />
      </aside>

      {/* Mobile drawer — always full width, collapse is a desktop-only affordance */}
      <Sheet
        open={mobileNavOpen}
        onClose={() => setMobileNavOpen(false)}
        side="left"
        title={tNav("dashboard")}
        closeLabel={tNav("closeMenu")}
      >
        <Sidebar
          persona={persona}
          onNavigate={() => setMobileNavOpen(false)}
        />
      </Sheet>

      {/* AI chat — available in all workspace personas */}
      <AiChatWindow open={aiOpen} onClose={() => setAiOpen(false)} />

      <div className="pointer-events-none fixed bottom-4 right-4 z-40">
        <button
          type="button"
          onClick={() => setHelpOpen(true)}
          aria-label={tNav("help")}
          className="group/help-fab pointer-events-auto relative flex size-12 items-center justify-center rounded-full border border-[var(--glass-border-strong)] bg-[var(--btn-primary-bg)] text-[var(--btn-primary-fg)] shadow-[0_8px_24px_rgba(0,0,0,0.18)] outline-none transition-colors duration-200 hover:bg-[var(--btn-primary-hover)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/35 focus-visible:ring-offset-2"
        >
          <HelpCircle aria-hidden strokeWidth={1.9} className="size-5" />
          <span className="pointer-events-none absolute right-[calc(100%+0.65rem)] top-1/2 -translate-y-1/2 whitespace-nowrap rounded-full border border-[var(--border-default)] bg-[var(--surface-card)] px-3 py-1.5 text-xs font-semibold text-[var(--text-primary)] opacity-0 shadow-[var(--shadow-sm)] transition-opacity duration-150 group-hover/help-fab:opacity-100 group-focus-visible/help-fab:opacity-100">
            {tNav("help")}
          </span>
        </button>
      </div>

      <HelpSupportModal
        open={helpOpen}
        onClose={() => setHelpOpen(false)}
        onOpenFeedback={() => setFeedbackOpen(true)}
      />
      <FeedbackModal open={feedbackOpen} onClose={() => setFeedbackOpen(false)} />

      {/* Main column — left offset only applies at the lg breakpoint where the fixed sidebar shows */}
      <div className="flex min-h-dvh flex-col transition-[padding-left] duration-200 motion-reduce:transition-none lg:pl-[var(--sidebar-offset)]">
        <Topbar persona={persona} onAiClick={() => setAiOpen(true)} />
        <div
          className={cn(
            "flex flex-1 flex-col bg-[var(--surface-card)] shadow-[inset_1px_1px_0_rgba(0,0,0,0.04)] lg:rounded-tl-[28px]",
            isFullCanvasRoute && "overflow-hidden",
          )}
        >
          <main
            id="main-content"
            tabIndex={-1}
            className={cn(
              "flex-1 outline-none",
              isFullCanvasRoute ? "flex min-h-0 p-0" : "px-4 py-6 lg:px-6",
            )}
          >
            <div
              className={cn(
                "w-full",
                isFullCanvasRoute ? "min-h-0 flex-1" : "mx-auto max-w-7xl",
              )}
            >
              {children}
            </div>
          </main>
          <WorkspaceFooter />
        </div>
      </div>

      <LoginModal />
    </div>
  );
}
