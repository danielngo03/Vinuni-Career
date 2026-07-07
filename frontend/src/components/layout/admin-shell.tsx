"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { ChevronDown, HelpCircle, Menu, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { ChevronRight } from "lucide-react";
import { Link, usePathname } from "@/i18n/navigation";
import { BrandMark } from "./brand-mark";
import { LanguageSwitcher } from "./language-switcher";
import { ThemeSwitcher } from "./theme-switcher";
import { AccountMenu } from "./account-menu";
import { NotificationBell } from "@/components/notifications/notification-bell";
import { MessagingBell } from "@/components/messaging/messaging-bell";
import { WorkspaceFooter } from "./workspace-footer";
// Note: Topbar (persona-based) intentionally not imported — AdminTopbar is
// defined inline below, using ADMIN_NAV_GROUPS / adminConsole i18n namespace.
import { FeedbackModal } from "./feedback-modal";
import { HelpSupportModal } from "./help-support-modal";
import { Sheet } from "@/components/ui";
import { ADMIN_NAV_GROUPS } from "@/config/nav";
import type { NavItem, NavGroup } from "@/config/nav";
import { readPersistedSidebarCollapsed, useUiStore } from "@/stores/ui-store";
import { cn } from "@/lib/utils";

// ─── Row styles (mirrors workspace Sidebar) ──────────────────────────────────
const ROW_CLASS =
  "group/nav-row flex min-h-10 cursor-pointer items-center gap-3 rounded-[14px] px-3.5 py-2 text-[0.875rem] font-semibold outline-none transition-colors duration-200 ease-out focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/25";
const ROW_IDLE_CLASS =
  "text-[var(--text-secondary)] hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus-visible:bg-[var(--bg-subtle)] focus-visible:text-[var(--text-primary)]";
const ROW_ACTIVE_CLASS =
  "bg-[var(--nav-active-bg)] font-bold text-[var(--nav-active-fg)]";
const ROW_DISABLED_CLASS =
  "cursor-default opacity-40 text-[var(--text-muted)]";

// ─── Nav link ────────────────────────────────────────────────────────────────
function AdminNavLink({
  href,
  label,
  icon: Icon,
  active,
  disabled,
  collapsed,
  onNavigate,
}: {
  href: string;
  label: string;
  icon: React.ElementType;
  active: boolean;
  disabled?: boolean;
  collapsed?: boolean;
  onNavigate?: () => void;
}) {
  if (disabled) {
    return (
      <span
        aria-disabled="true"
        title={collapsed ? label : undefined}
        className={cn(
          ROW_CLASS,
          collapsed && "justify-center px-0 py-2.5",
          ROW_DISABLED_CLASS,
        )}
      >
        <Icon
          aria-hidden
          strokeWidth={1.7}
          className={cn(
            "shrink-0 size-[18px] text-[var(--text-muted)]",
          )}
        />
        <span className={cn("min-w-0 truncate", collapsed && "sr-only")}>
          {label}
        </span>
      </span>
    );
  }

  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      onClick={onNavigate}
      title={collapsed ? label : undefined}
      className={cn(
        ROW_CLASS,
        collapsed && "justify-center px-0 py-2.5",
        active ? ROW_ACTIVE_CLASS : ROW_IDLE_CLASS,
      )}
    >
      <Icon
        aria-hidden
        strokeWidth={active ? 2.2 : 1.7}
        className={cn(
          "shrink-0",
          active
            ? "size-5 text-[var(--nav-active-fg)]"
            : "size-[18px] text-[var(--text-muted)] transition-colors duration-200 group-hover/nav-row:text-[var(--text-primary)]",
        )}
      />
      <span className={cn("min-w-0 truncate", active && "text-sm", collapsed && "sr-only")}>
        {label}
      </span>
    </Link>
  );
}

// ─── Sidebar ─────────────────────────────────────────────────────────────────
interface AdminSidebarProps {
  onNavigate?: () => void;
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
}

function AdminSidebar({ onNavigate, collapsed = false, onToggleCollapsed }: AdminSidebarProps) {
  const t = useTranslations("adminConsole");
  const tNav = useTranslations("nav");
  const pathname = usePathname();
  const groups = ADMIN_NAV_GROUPS;
  const sidebarToggleLabel = collapsed ? tNav("expandSidebar") : tNav("collapseSidebar");

  function isActive(href: string) {
    if (href === "/admin") return pathname === href;
    return pathname === href || pathname.startsWith(`${href}/`);
  }

  function groupHasActiveChild(group: NavGroup) {
    return group.items.some((i) => isActive(i.href));
  }

  const [openKeys, setOpenKeys] = useState<Record<string, boolean>>({});
  useEffect(() => {
    setOpenKeys((prev) => {
      const next = { ...prev };
      for (const group of groups) {
        if (group.accordion && group.key && groupHasActiveChild(group)) {
          next[group.key] = true;
        }
      }
      return next;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  return (
    <div className="flex h-full flex-col bg-[#f7f6f2]">
      <div
        className={cn(
          "flex h-[60px] shrink-0 items-center",
          collapsed ? "justify-center px-0" : "px-4",
        )}
      >
        {collapsed ? (
          <BrandMark showTagline={false} />
        ) : (
          <BrandMark wordmarkClassName="text-[0.75rem] tracking-[0.13em]" />
        )}
      </div>

      <nav
        aria-label={t("page.overviewTitle")}
        className={cn("scrollbar-thin flex-1 overflow-y-auto py-3.5", collapsed ? "px-2" : "px-3")}
      >
        {groups.map((group, gi) => {
          const previousGroup = groups[gi - 1];
          const gapBefore =
            gi > 0 &&
            !(gi === 1 && groups[0]?.key === null) &&
            !(group.key === null && previousGroup?.key === null);

          if (group.accordion && group.icon) {
            const GroupIcon = group.icon;
            const childActive = groupHasActiveChild(group);
            const label = t(`group.${group.key}`);

            if (collapsed) {
              const first = group.items[0];
              if (!first) return null;
              return (
                <div key={group.key} className={cn(gapBefore && "mt-5")}>
                  <AdminNavLink
                    href={first.href}
                    label={label}
                    icon={GroupIcon}
                    active={childActive}
                    collapsed
                    onNavigate={onNavigate}
                  />
                </div>
              );
            }

            const open = openKeys[group.key!] ?? false;
            return (
              <div key={group.key} className={cn(gapBefore && "mt-4")}>
                <button
                  type="button"
                  aria-expanded={open}
                  onClick={() =>
                    setOpenKeys((prev) => ({ ...prev, [group.key!]: !open }))
                  }
                  className={cn(ROW_CLASS, "w-full", childActive ? ROW_ACTIVE_CLASS : ROW_IDLE_CLASS)}
                >
                  <GroupIcon
                    aria-hidden
                    strokeWidth={childActive ? 2.2 : 1.7}
                    className={cn(
                      "shrink-0",
                      childActive
                        ? "size-5 text-[var(--nav-active-fg)]"
                        : "size-[18px] text-[var(--text-muted)] transition-colors duration-200 group-hover/nav-row:text-[var(--text-primary)]",
                    )}
                  />
                  <span className={cn("min-w-0 flex-1 truncate text-left", childActive && "text-sm")}>
                    {label}
                  </span>
                  <ChevronDown
                    aria-hidden
                    strokeWidth={2}
                    className={cn(
                      "size-3.5 shrink-0 transition-transform duration-150",
                      open && "rotate-180",
                      childActive ? "text-[var(--nav-active-fg)]" : "text-[var(--text-muted)]",
                    )}
                  />
                </button>
                {open && (
                  <ul className="ml-[1.2rem] mt-1.5 space-y-1 border-l border-[var(--border-default)] pl-2.5">
                    {group.items.map((item: NavItem) => (
                      <li key={item.href}>
                        <AdminNavLink
                          href={item.href}
                          label={t(`nav.${item.key}`)}
                          icon={item.icon}
                          active={isActive(item.href)}
                          disabled={item.disabled}
                          onNavigate={onNavigate}
                        />
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            );
          }

          // Flat block
          return (
            <div key={group.key ?? `flat-${gi}`} className={cn(gapBefore && "mt-4")}>
              {group.key && !collapsed && (
                <p className="px-3 pb-1.5 text-[0.6875rem] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                  {t(`group.${group.key}`)}
                </p>
              )}
              {group.key && collapsed && gi > 0 && (
                <div aria-hidden className="mx-2 mb-2 border-t border-[var(--border-subtle)]" />
              )}
              <div className="space-y-0.5">
                {group.items.map((item: NavItem) => (
                  <AdminNavLink
                    key={item.href}
                    href={item.href}
                    label={t(`nav.${item.key}`)}
                    icon={item.icon}
                    active={isActive(item.href)}
                    disabled={item.disabled}
                    collapsed={collapsed}
                    onNavigate={onNavigate}
                  />
                ))}
              </div>
            </div>
          );
        })}
      </nav>

      <div className={cn("space-y-0.5 py-3", collapsed ? "px-2" : "px-3")}>
        {onToggleCollapsed && (
          <button
            type="button"
            onClick={onToggleCollapsed}
            aria-pressed={collapsed}
            aria-label={sidebarToggleLabel}
            title={sidebarToggleLabel}
            className={cn(
              ROW_CLASS,
              "w-full text-[var(--text-secondary)] hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)]",
              collapsed && "justify-center px-0 py-2.5",
            )}
          >
            {collapsed ? (
              <PanelLeftOpen aria-hidden strokeWidth={1.8} className="size-[18px] text-[var(--text-muted)]" />
            ) : (
              <PanelLeftClose aria-hidden strokeWidth={1.8} className="size-[18px] text-[var(--text-muted)]" />
            )}
            <span className={cn(collapsed && "sr-only")}>{sidebarToggleLabel}</span>
          </button>
        )}
      </div>
    </div>
  );
}

// ─── Admin Topbar ─────────────────────────────────────────────────────────────
/**
 * Fixed topbar for the admin shell. Resolves breadcrumb context from
 * `ADMIN_NAV_GROUPS` (keyed under `adminConsole.nav`) instead of `WORKSPACE_NAV`
 * (keyed under `nav`), so admin routes show correct section labels rather than
 * falling back to university navigation labels.
 */
function AdminTopbar() {
  const t = useTranslations("adminConsole");
  const tNav = useTranslations("nav");
  const pathname = usePathname();
  const setMobileNavOpen = useUiStore((s) => s.setMobileNavOpen);

  // Resolve current admin nav item
  const allAdminItems = ADMIN_NAV_GROUPS.flatMap((g) => g.items);
  const currentItem = allAdminItems.find((item) => {
    if (item.href === "/admin") return pathname === item.href;
    return pathname === item.href || pathname.startsWith(`${item.href}/`);
  });
  const currentKey = currentItem?.key ?? "overview";
  const isOverview = pathname === "/admin";
  const currentLabel = t(`nav.${currentKey}`);
  const overviewLabel = t("nav.overview");

  return (
    <header className="sticky top-0 z-30 flex h-[60px] items-center gap-3 bg-[#f7f6f2]/95 px-4 backdrop-blur-sm lg:px-6">
      <button
        type="button"
        onClick={() => setMobileNavOpen(true)}
        aria-label={tNav("openMenu")}
        className="rounded-lg p-2 text-[var(--text-secondary)] outline-none hover:bg-[var(--bg-subtle)] lg:hidden"
      >
        <Menu aria-hidden strokeWidth={1.8} className="size-5" />
      </button>

      <div className="lg:hidden">
        <BrandMark showTagline={false} />
      </div>

      <nav
        aria-label={t("page.overviewTitle")}
        className="hidden min-w-0 flex-1 items-center gap-1.5 text-sm lg:flex"
      >
        {isOverview ? (
          <span className="truncate font-semibold text-[var(--text-primary)]">
            {overviewLabel}
          </span>
        ) : (
          <>
            <Link
              href="/admin"
              className="truncate font-medium text-[var(--text-muted)] outline-none transition-colors hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
            >
              {overviewLabel}
            </Link>
            <ChevronRight
              aria-hidden
              strokeWidth={1.8}
              className="size-4 shrink-0 text-[var(--text-muted)]"
            />
            <span className="truncate font-semibold text-[var(--text-primary)]">
              {currentLabel}
            </span>
          </>
        )}
      </nav>

      <div className="ml-auto flex items-center gap-2">
        <LanguageSwitcher compact />
        <ThemeSwitcher />
        <NotificationBell variant="labeled" href="/university/notifications" />
        <MessagingBell variant="labeled" href="/university/messages" />
        <AccountMenu settingsHref="/university/settings" showName />
      </div>
    </header>
  );
}

// ─── Shell ───────────────────────────────────────────────────────────────────
/**
 * Workspace shell for the superadmin `(admin)` route group.
 * Structurally identical to `WorkspaceShell` but uses `ADMIN_NAV_GROUPS` and
 * the `adminConsole` i18n namespace — it does not accept a `persona` prop
 * because admin is not a user-persona in the app's auth model.
 */
export function AdminShell({ children }: { children: React.ReactNode }) {
  const tNav = useTranslations("nav");
  const {
    mobileNavOpen,
    setMobileNavOpen,
    sidebarCollapsed,
    toggleSidebarCollapsed,
    setSidebarCollapsed,
  } = useUiStore();
  const [helpOpen, setHelpOpen] = useState(false);
  const [feedbackOpen, setFeedbackOpen] = useState(false);

  // Admin routes are accessible by any authenticated superadmin persona.
  // Redirect is handled by AdminGuard — this shell only handles layout concerns.

  useEffect(() => {
    setSidebarCollapsed(readPersistedSidebarCollapsed());
  }, [setSidebarCollapsed]);

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
        {tNav("closeMenu")}
      </a>

      {/* Desktop sidebar */}
      <aside
        aria-label={tNav("dashboard")}
        className="fixed inset-y-0 left-0 z-20 hidden transition-[width] duration-200 motion-reduce:transition-none lg:block"
        style={{ width: sidebarCollapsed ? "64px" : "var(--sidebar-width)" }}
      >
        <AdminSidebar
          collapsed={sidebarCollapsed}
          onToggleCollapsed={toggleSidebarCollapsed}
        />
      </aside>

      {/* Mobile drawer */}
      <Sheet
        open={mobileNavOpen}
        onClose={() => setMobileNavOpen(false)}
        side="left"
        title={tNav("dashboard")}
        closeLabel={tNav("closeMenu")}
      >
        <AdminSidebar onNavigate={() => setMobileNavOpen(false)} />
      </Sheet>

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

      {/* Main column */}
      <div className="flex min-h-dvh flex-col transition-[padding-left] duration-200 motion-reduce:transition-none lg:pl-[var(--sidebar-offset)]">
        <AdminTopbar />
        <div className="flex flex-1 flex-col bg-[var(--surface-card)] shadow-[inset_1px_1px_0_rgba(0,0,0,0.04)] lg:rounded-tl-[28px]">
          <main
            id="main-content"
            tabIndex={-1}
            className="flex-1 px-4 py-6 outline-none lg:px-6"
          >
            <div className="mx-auto w-full max-w-7xl">
              {children}
            </div>
          </main>
          <WorkspaceFooter />
        </div>
      </div>
    </div>
  );
}
