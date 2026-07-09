"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { CircleNotch } from "@phosphor-icons/react";
import { Sidebar } from "./sidebar";
import { Topbar } from "./topbar";
import { LoginModal } from "./login-modal";
import { BrandMark } from "./brand-mark";
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

      {/* Main column — left offset only applies at the lg breakpoint where the fixed sidebar shows */}
      <div
        className={cn(
          "flex min-h-dvh flex-col transition-[padding-left] duration-200 motion-reduce:transition-none lg:pl-[var(--sidebar-offset)]",
          aiOpen && "xl:h-dvh xl:min-h-0 xl:overflow-hidden",
        )}
      >
        <Topbar
          persona={persona}
          onAiClick={() => setAiOpen((open) => !open)}
          aiActive={aiOpen}
        />
        <div
          className={cn(
            "flex min-h-0 flex-1 flex-col bg-[var(--surface-card)] shadow-[inset_1px_1px_0_rgba(0,0,0,0.04)] lg:rounded-tl-[28px]",
            aiOpen && "xl:bg-[#f7f6f2] xl:shadow-none",
            isFullCanvasRoute && "overflow-hidden",
          )}
        >
          <div
            className={cn(
              "flex min-h-0 flex-1",
              aiOpen &&
              "xl:grid xl:grid-cols-[minmax(0,5fr)_minmax(380px,2fr)] xl:gap-5 xl:overflow-hidden",
            )}
          >
            <main
              id="main-content"
              tabIndex={-1}
              className={cn(
                "min-w-0 flex-1 outline-none transition-[padding] duration-200 motion-reduce:transition-none",
                isFullCanvasRoute ? "flex min-h-0 p-0" : "px-4 py-6 lg:px-6",
                aiOpen &&
                  "xl:min-h-0 xl:overflow-hidden xl:bg-[var(--surface-card)] xl:rounded-r-[24px] xl:rounded-tl-[28px]",
                aiOpen &&
                  !isFullCanvasRoute &&
                  "xl:px-4 xl:text-[0.875rem] xl:[&_.text-sm]:text-[0.8125rem] xl:[&_.text-base]:text-[0.875rem] xl:[&_.text-lg]:text-[1rem] xl:[&_.text-xl]:text-[1.125rem] xl:[&_.text-2xl]:text-[1.25rem]",
              )}
            >
              <div
                className={cn(
                  "w-full",
                  isFullCanvasRoute
                    ? "min-h-0 flex-1"
                    : aiOpen
                      ? "mx-0 max-w-none xl:h-full xl:overflow-y-auto xl:pr-2"
                      : "mx-auto max-w-7xl",
                )}
              >
                {children}
              </div>
            </main>

            {aiOpen && (
              <aside
                aria-label={tNav("aiAssistant")}
                className={cn(
                  "fixed inset-x-3 bottom-3 top-[72px] z-50 overflow-hidden rounded-2xl bg-[var(--surface-card)] shadow-[0_18px_60px_rgba(11,34,57,0.18)]",
                  "xl:static xl:inset-auto xl:z-auto xl:h-full xl:min-h-0 xl:rounded-l-[24px] xl:rounded-r-none xl:shadow-[0_1px_2px_rgba(11,34,57,0.04)]",
                )}
              >
                <AiChatWindow
                  open={aiOpen}
                  onClose={() => setAiOpen(false)}
                  variant="embedded"
                />
              </aside>
            )}
          </div>
        </div>
      </div>

      <LoginModal />
    </div>
  );
}
