import {
  LayoutGrid,
  Briefcase,
  UsersRound,
  Users,
  Kanban,
  BookUser,
  CalendarDays,
  MessageSquareText,
  Star,
  Megaphone,
  BarChart3,
  Gauge,
  Building2,
  CreditCard,
  ShieldCheck,
  FileCheck,
  Workflow,
  GraduationCap,
  FileText,
  Bot,
  Layers,
  LineChart,
  Settings,
  HeartHandshake,
  LifeBuoy,
  Lock,
  ShieldAlert,
  Bell,
  Activity,
  ScrollText,
  ToggleRight,
  Siren,
} from "lucide-react";
import type { Persona } from "@/stores/auth-store";

/**
 * Personas that use the admin-style workspace shell (sidebar + topbar). The
 * student uses the marketplace top-nav shell (`student-shell.tsx`) rendering the
 * shared `PUBLIC_PRIMARY_NAV`, so it has no sidebar/topbar nav model here — that
 * kept three drifting student nav definitions in sync for no benefit.
 */
export type WorkspacePersona = Exclude<Persona, "student">;

export interface NavItem {
  /** i18n key under `nav`. */
  key: string;
  /** Path relative to the persona root (e.g. "/dashboard" → "/student/dashboard"). */
  href: string;
  icon: React.ElementType;
  /**
   * When false, the destination is not built yet: it is rendered in a disabled
   * "Sắp ra mắt" group instead of as a clickable dead-end (no ComingSoon route is
   * linked from primary nav). Defaults to true.
   */
  available?: boolean;
  /**
   * When true, `href` is an absolute app path (not persona-prefixed) — e.g. the
   * student "Jobs" entry points at the public marketplace board `/jobs`.
   */
  absolute?: boolean;
  /**
   * When true the item is rendered in a non-interactive "coming soon" state:
   * visible for IA clarity but not clickable. Used in admin nav stubs that are
   * planned but not yet built.
   */
  disabled?: boolean;
  /**
   * When true, this item is only shown to users with `isSuperadmin === true`.
   * The sidebar filter gates visibility; the per-page SuperadminGuard enforces
   * server-side protection on direct URL access.
   */
  requiresSuperadmin?: boolean;
  /**
   * When set, the item is shown only if the user has `permissions.includes("*")`
   * (superadmin) OR `permissions.includes(requiresPermission)`. This is additive
   * with `requiresSuperadmin` — an item may require both. No existing item is
   * gated by `requiresPermission` yet; this wires the capability for future use.
   */
  requiresPermission?: string;
}

/**
 * A sidebar block (v7.4 "Quiet Operations" hybrid). Two shapes:
 * - Flat block (`accordion` unset): items render as always-visible links.
 *   `key` (i18n under `nav.group`) renders a small-caps title above them, or
 *   no title at all for the first, most-frequent block (`key: null`).
 * - Accordion block (`accordion: true`): renders as ONE clickable row (its
 *   own icon + `nav.group.{key}` label + chevron) whose `items` are the
 *   submenu — auto-expands when the active route is inside it. Reserved for
 *   genuinely dense, drill-down workflow clusters; everything else stays a
 *   flat, always-visible link so the common surfaces are never one click away.
 */
export interface NavGroup {
  key: string | null;
  items: NavItem[];
  accordion?: boolean;
  /** Icon for the accordion trigger row. Required when `accordion` is true. */
  icon?: React.ElementType;
}

/**
 * Workspace sidebar per persona. Student is intentionally absent — it uses the
 * marketplace top-nav shell, not the sidebar.
 */
export const WORKSPACE_NAV_GROUPS: Record<WorkspacePersona, NavGroup[]> = {
  partner: [
    {
      key: null,
      items: [
        { key: "dashboard", href: "/dashboard", icon: LayoutGrid },
        { key: "ops", href: "/ops", icon: Gauge },
        { key: "jobs", href: "/jobs", icon: Briefcase },
      ],
    },
    {
      key: "recruitment",
      accordion: true,
      icon: UsersRound,
      items: [
        { key: "candidates", href: "/candidates", icon: Users },
        { key: "pipeline", href: "/pipeline", icon: Kanban },
        { key: "talentPool", href: "/talent-pool", icon: BookUser },
        { key: "recruitingWorkflows", href: "/workflow", icon: Workflow },
        { key: "security", href: "/security", icon: ShieldCheck },
      ],
    },
    {
      key: null,
      items: [
        { key: "events", href: "/events", icon: CalendarDays },
        { key: "advertising", href: "/advertising", icon: Megaphone },
        { key: "analytics", href: "/analytics", icon: BarChart3 },
      ],
    },
  ],
  university: [
    {
      key: null,
      items: [
        { key: "dashboard", href: "/dashboard", icon: LayoutGrid },
        { key: "reports", href: "/reports", icon: LineChart },
      ],
    },
    {
      key: "governance",
      accordion: true,
      icon: ShieldCheck,
      items: [
        { key: "moderation", href: "/moderation", icon: FileCheck },
        { key: "partners", href: "/partners", icon: Building2 },
        { key: "users", href: "/users", icon: Users },
        { key: "workflowBuilder", href: "/workflow", icon: Workflow },
      ],
    },
    {
      key: "engagement",
      items: [
        { key: "careerServices", href: "/career-services", icon: HeartHandshake },
        { key: "messages", href: "/messages", icon: MessageSquareText },
        { key: "events", href: "/events", icon: CalendarDays },
        { key: "reviews", href: "/reviews", icon: Star },
        { key: "advertising", href: "/advertising", icon: Megaphone },
      ],
    },
    {
      key: "platform",
      accordion: true,
      icon: Layers,
      items: [
        { key: "careerOutcomes", href: "/career-outcomes", icon: GraduationCap },
        { key: "cvTemplates", href: "/cv-templates", icon: FileText },
        { key: "notificationTemplates", href: "/notifications/templates", icon: Bell },
        { key: "subscriptions", href: "/billing", icon: CreditCard },
        { key: "aiSettings", href: "/ai-settings", icon: Bot },
      ],
    },
    {
      key: "trust",
      accordion: true,
      icon: LifeBuoy,
      items: [
        { key: "support", href: "/support", icon: LifeBuoy },
        { key: "privacyAdmin", href: "/privacy", icon: Lock },
        { key: "abuseTriage", href: "/abuse", icon: ShieldAlert },
      ],
    },
    {
      key: "systemAdmin",
      accordion: true,
      icon: Gauge,
      items: [
        { key: "platformOverview", href: "/platform-overview", icon: LayoutGrid, requiresSuperadmin: true },
        { key: "aiOperations", href: "/ai-operations", icon: Bot, requiresSuperadmin: true },
        { key: "analytics", href: "/analytics", icon: BarChart3, requiresSuperadmin: true },
        { key: "logs", href: "/logs", icon: ScrollText, requiresSuperadmin: true },
        { key: "systemHealth", href: "/system-health", icon: Activity, requiresSuperadmin: true },
        { key: "usersAccess", href: "/access", icon: Users, requiresSuperadmin: true },
        { key: "featureFlags", href: "/feature-flags", icon: ToggleRight, requiresSuperadmin: true },
        { key: "alertsAdmin", href: "/alerts", icon: Siren, requiresSuperadmin: true },
      ],
    },
  ],
};

/** Flat per-persona nav — derived from the grouped structure for consumers
 * that only need the item list (route-title resolution, placeholder catch-alls). */
export const WORKSPACE_NAV: Record<WorkspacePersona, NavItem[]> = {
  partner: WORKSPACE_NAV_GROUPS.partner.flatMap((g) => g.items),
  university: WORKSPACE_NAV_GROUPS.university.flatMap((g) => g.items),
};

export const SETTINGS_NAV: NavItem = {
  key: "settings",
  href: "/settings",
  icon: Settings,
};
