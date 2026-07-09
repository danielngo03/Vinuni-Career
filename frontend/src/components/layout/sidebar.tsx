"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { Link, usePathname } from "@/i18n/navigation";
import { CompanyAvatar } from "@/components/companies/company-avatar";
import { WORKSPACE_NAV_GROUPS, type NavGroup, type NavItem } from "@/config/nav";
import { organizationApi } from "@/lib/api";
import { BrandMark } from "./brand-mark";
import { SidebarUsageCard } from "./sidebar-usage-card";
import { useAuthStore, type Persona } from "@/stores/auth-store";
import { cn } from "@/lib/utils";

interface SidebarProps {
  persona: Persona;
  onNavigate?: () => void;
  /** Icon-only rail mode (desktop only — DESIGN.md §4 collapsed width 64px). */
  collapsed?: boolean;
  /** Renders the collapse/expand toggle when provided (desktop rail only, not the mobile drawer). */
  onToggleCollapsed?: () => void;
}

const ROW_CLASS =
  "group/nav-row flex min-h-9 cursor-pointer items-center gap-2.5 rounded-[12px] px-3 py-1.5 text-[0.8125rem] font-semibold outline-none transition-colors duration-200 ease-out focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/25";
const ROW_IDLE_CLASS =
  "text-[var(--text-secondary)] hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus-visible:bg-[var(--bg-subtle)] focus-visible:text-[var(--text-primary)]";
/** VinUni mark navy fill — the current route reads as a real selected button. */
const ROW_ACTIVE_CLASS =
  "bg-[var(--nav-active-bg)] font-bold text-[var(--nav-active-fg)]";

function NavLink({
  href,
  label,
  icon: Icon,
  active,
  collapsed,
  onNavigate,
}: {
  href: string;
  label: string;
  icon: React.ElementType;
  active: boolean;
  collapsed?: boolean;
  onNavigate?: () => void;
}) {
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
      <span className={cn("min-w-0 truncate", active && "text-[0.8125rem]", collapsed && "sr-only")}>
        {label}
      </span>
    </Link>
  );
}

/** Text-only sub-item hanging off an accordion parent's left rail. */
function SubNavLink({
  href,
  label,
  active,
  onNavigate,
}: {
  href: string;
  label: string;
  active: boolean;
  onNavigate?: () => void;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      onClick={onNavigate}
      className={cn(
        "flex min-h-7 cursor-pointer items-center rounded-[9px] px-2.5 py-1 text-[0.75rem] outline-none transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/20",
        active
          ? "bg-[var(--bg-subtle)] font-semibold text-[var(--nav-active-text)]"
          : "font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus-visible:bg-[var(--bg-subtle)] focus-visible:text-[var(--text-primary)]",
      )}
    >
      <span className="min-w-0 truncate">{label}</span>
    </Link>
  );
}

function PartnerCompanyIdentity() {
  const t = useTranslations("nav");
  const query = useQuery({
    queryKey: ["org", "profile"],
    queryFn: () => organizationApi.get(),
    retry: false,
  });

  const org = query.data;
  const name = org?.display_name ?? t("group.organization");
  const detail = org?.is_verified
    ? org.status_label
    : org?.subscription_tier
      ? t("usage.plan", { name: org.subscription_tier })
      : t("group.organization");

  return (
    <div
      aria-label={name}
      className="mb-2 rounded-[14px] border border-[var(--border-default)] bg-[var(--surface-card)] p-2.5 shadow-[var(--shadow-xs)]"
    >
      <div className="flex min-w-0 items-center gap-2.5">
        {query.isPending ? (
          <span
            aria-hidden
            className="size-10 shrink-0 animate-pulse rounded-xl bg-[var(--bg-muted)]"
          />
        ) : (
          <CompanyAvatar
            name={name}
            logoUrl={org?.logo_url}
            size="sm"
            className="size-10 rounded-xl"
          />
        )}
        <div className="min-w-0">
          <p className="truncate text-[0.8125rem] font-bold text-[var(--text-primary)]">
            {query.isPending ? t("group.organization") : name}
          </p>
          <p className="mt-0.5 truncate text-[0.6875rem] font-medium text-[var(--text-muted)]">
            {detail}
          </p>
        </div>
      </div>
    </div>
  );
}

/**
 * Light workspace sidebar (v7.4 "Quiet Operations" hybrid). White surface,
 * no row borders. Most surfaces are flat always-visible links under a small
 * section title; genuinely dense workflow clusters (recruitment, org
 * settings, governance, platform) collapse into a single clickable accordion
 * row that auto-expands on its active route. Official VinUniversity lockup.
 */
export function Sidebar({
  persona,
  onNavigate,
  collapsed = false,
  onToggleCollapsed,
}: SidebarProps) {
  const t = useTranslations("nav");
  const pathname = usePathname();
  const isSuperadmin = useAuthStore((s) => s.user?.isSuperadmin ?? false);
  const permissions = useAuthStore((s) => s.user?.permissions ?? []);
  const groups = WORKSPACE_NAV_GROUPS[persona];
  const sidebarToggleLabel = collapsed ? t("expandSidebar") : t("collapseSidebar");

  // Workspace routes are namespaced by persona to avoid route-group collisions
  // on shared paths (e.g. /student/dashboard vs /partner/dashboard).
  const base = `/${persona}`;

  function isActive(href: string) {
    return pathname === href || pathname.startsWith(`${href}/`);
  }

  function resolveHref(item: NavItem) {
    return item.absolute ? item.href : `${base}${item.href}`;
  }

  function groupHasActiveChild(group: NavGroup) {
    return group.items.some((i) => isActive(resolveHref(i)));
  }

  // Manual toggles overlay the route-driven auto-open state.
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
  }, [pathname, persona]);

  return (
    <div className="flex h-full flex-col bg-[#f7f6f2]">
      {/* Official VinUniversity lockup. Collapse lives near the footer identity. */}
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

      {/* Primary nav — flat titled blocks + accordion rows for dense clusters */}
      <nav
        aria-label={t("dashboard")}
        className={cn("scrollbar-thin flex-1 overflow-y-auto py-3.5", collapsed ? "px-2" : "px-3")}
      >
        {/* The ungrouped top block has no title, so its immediate successor
            reads as a continuous list with it — no gap between e.g. "Việc
            làm" and the "Tuyển dụng" accordion right after it. Every other
            group boundary keeps its breathing room. */}
        {groups.map((group, gi) => {
          const available = group.items.filter((i) => {
            if (i.available === false) return false;
            if (i.requiresSuperadmin && !isSuperadmin) return false;
            if (
              i.requiresPermission &&
              !isSuperadmin &&
              !permissions.includes("*") &&
              !permissions.includes(i.requiresPermission)
            )
              return false;
            return true;
          });
          if (available.length === 0) return null;
          const previousGroup = groups[gi - 1];
          const gapBefore =
            gi > 0 &&
            !(gi === 1 && groups[0]?.key === null) &&
            !(persona === "partner" && group.key === null && previousGroup?.key === "recruitment");

          // Accordion block: one clickable row + collapsible submenu.
          if (group.accordion && group.icon) {
            const GroupIcon = group.icon;
            const childActive = groupHasActiveChild(group);
            const label = t(`group.${group.key}`);

            if (collapsed) {
              // Icon-only rail: the row deep-links to its first child.
              const first = available[0]!;
              return (
                <div key={group.key} className={cn(gapBefore && "mt-5")}>
                  <NavLink
                    href={resolveHref(first)}
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
                  <span
                    className={cn(
                      "min-w-0 flex-1 truncate text-left",
                      childActive && "text-[0.8125rem]",
                    )}
                  >
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
                    {available.map((item) => {
                      const href = resolveHref(item);
                      return (
                        <li key={item.href}>
                          <SubNavLink
                            href={href}
                            label={t(item.key)}
                            active={isActive(href)}
                            onNavigate={onNavigate}
                          />
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            );
          }

          // Flat block: always-visible links, with an optional small-caps title.
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
                {available.map((item) => {
                  const href = resolveHref(item);
                  return (
                    <NavLink
                      key={item.href}
                      href={href}
                      label={t(item.key)}
                      icon={item.icon}
                      active={isActive(href)}
                      collapsed={collapsed}
                      onNavigate={onNavigate}
                    />
                  );
                })}
              </div>
            </div>
          );
        })}
      </nav>

      {/* Footer: AI usage + plan card. The AI assistant now lives in the
          topbar (after the messaging bell); account & settings live in the
          topbar's AccountMenu. */}
      <div
        className={cn(
          "space-y-0.5 py-3",
          collapsed ? "px-2" : "px-3",
        )}
      >
        {!collapsed && (
          <div className="pb-2">
            <SidebarUsageCard persona={persona} />
          </div>
        )}
        {persona === "partner" && !collapsed && <PartnerCompanyIdentity />}
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
