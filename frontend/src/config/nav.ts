import {
  SquaresFour,
  UserCircle,
  FileText as PhFileText,
  Briefcase as PhBriefcase,
  ClipboardText,
  Calendar as PhCalendar,
  BellSimple,
  EnvelopeSimple,
} from "@phosphor-icons/react";
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
  LineChart,
  Settings,
  HeartHandshake,
  LifeBuoy,
  Lock,
  ShieldAlert,
  Bell,
  Activity,
  ScrollText,
  ClipboardList,
  ToggleRight,
  Siren,
  Zap,
} from "lucide-react";
import type { Persona } from "@/stores/auth-store";

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
 * Student primary navigation (SCREEN_SPECS §1: "signed-in marketplace top nav
 * inherited from the public gateway"). The student does NOT use the admin-style
 * sidebar — these items render in the marketplace-style top-nav shell
 * (`student-shell.tsx`) and its mobile drawer. Every item deep-links into a
 * shipped surface, so there is no "coming soon" group here (no dead ends).
 * Employer-acquisition items (Employers, partner registration) are intentionally
 * absent from the student context. `Saved` is exposed via the header's
 * `SavedButton`, not as a primary tab.
 */
export const STUDENT_PRIMARY_NAV: NavItem[] = [
  { key: "jobs", href: "/jobs", icon: PhBriefcase, absolute: true },
  { key: "dashboard", href: "/dashboard", icon: SquaresFour },
  { key: "cv", href: "/cv", icon: PhFileText },
  { key: "profile", href: "/profile", icon: UserCircle },
  { key: "applications", href: "/applications", icon: ClipboardText },
  { key: "invitations", href: "/invitations", icon: EnvelopeSimple },
  { key: "alerts", href: "/alerts", icon: BellSimple },
  { key: "myEvents", href: "/events", icon: PhCalendar },
];

/** Resolve a student nav item to its full path (persona-prefixed unless absolute). */
export function studentHref(item: NavItem): string {
  return item.absolute ? item.href : `/student${item.href}`;
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
 * Workspace sidebar per persona.
 */
export const WORKSPACE_NAV_GROUPS: Record<Persona, NavGroup[]> = {
  student: [{ key: null, items: STUDENT_PRIMARY_NAV }],
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
  // University Operations — a career-office operating model. Platform/system
  // administration (AI ops, health, logs, flags, alerts, platform users) is NOT
  // here anymore: it lives in the separate superadmin Platform Admin console
  // (`ADMIN_NAV_GROUPS` → `/admin/*`). This shell is the day-to-day career
  // services / governance surface for university staff.
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
        { key: "reviews", href: "/reviews", icon: Star },
        { key: "abuseTriage", href: "/abuse", icon: ShieldAlert },
        { key: "workflowBuilder", href: "/workflow", icon: Workflow },
      ],
    },
    {
      key: "students",
      items: [
        { key: "careerServices", href: "/career-services", icon: HeartHandshake },
        { key: "careerOutcomes", href: "/career-outcomes", icon: GraduationCap },
        { key: "cvTemplates", href: "/cv-templates", icon: FileText },
      ],
    },
    {
      key: "engagement",
      accordion: true,
      icon: Megaphone,
      items: [
        { key: "events", href: "/events", icon: CalendarDays },
        { key: "messages", href: "/messages", icon: MessageSquareText },
        { key: "advertising", href: "/advertising", icon: Megaphone },
        { key: "notificationTemplates", href: "/notifications/templates", icon: Bell },
      ],
    },
    {
      key: "trust",
      accordion: true,
      icon: LifeBuoy,
      items: [
        { key: "support", href: "/support", icon: LifeBuoy },
        { key: "privacyAdmin", href: "/privacy", icon: Lock },
      ],
    },
    {
      key: "administration",
      accordion: true,
      icon: Gauge,
      items: [
        // Org RBAC control plane: departments, staff, roles, invitations.
        // Superadmin-only this phase (matches /university/team's SuperadminGuard).
        { key: "teamAccess", href: "/team", icon: UsersRound, requiresSuperadmin: true },
        // Staff-facing AI energy governance: my usage + capacity requests.
        { key: "aiGovernance", href: "/ai-governance", icon: Zap },
        // Masked AI settings (aliases/status/budget) for staff; the real
        // provider registry inside is superadmin-gated in the screen itself.
        { key: "aiSettings", href: "/ai-settings", icon: Bot },
        { key: "subscriptions", href: "/billing", icon: CreditCard },
      ],
    },
  ],
};

/**
 * Platform Admin console navigation — a distinct superadmin-only workspace
 * (`/admin/*`), split out of the University Operations shell (owner decision
 * 2026-07-08). Every destination is superadmin-only both here (nav filter) and
 * at the shell (`AdminShell` wraps in `SuperadminGuard`) and per page. Backend
 * `/admin/*` API paths are unchanged; this only reorganizes the frontend IA.
 */
export const ADMIN_NAV_GROUPS: NavGroup[] = [
  {
    key: null,
    items: [
      { key: "platformOverview", href: "/platform-overview", icon: LayoutGrid, requiresSuperadmin: true },
      { key: "analytics", href: "/analytics", icon: BarChart3, requiresSuperadmin: true },
    ],
  },
  {
    key: "aiOps",
    items: [
      { key: "aiOperations", href: "/ai-operations", icon: Bot, requiresSuperadmin: true },
      { key: "aiDistribution", href: "/ai-distribution", icon: Zap, requiresSuperadmin: true },
    ],
  },
  {
    key: "system",
    items: [
      { key: "systemHealth", href: "/system-health", icon: Activity, requiresSuperadmin: true },
      { key: "alertsAdmin", href: "/alerts", icon: Siren, requiresSuperadmin: true },
      { key: "logs", href: "/logs", icon: ScrollText, requiresSuperadmin: true },
      { key: "auditLog", href: "/audit-log", icon: ClipboardList, requiresSuperadmin: true },
      { key: "featureFlags", href: "/feature-flags", icon: ToggleRight, requiresSuperadmin: true },
      { key: "usersAccess", href: "/access", icon: Users, requiresSuperadmin: true },
    ],
  },
];

/** Flat per-persona nav — derived from the grouped structure for consumers
 * that only need the item list (route-title resolution, placeholder catch-alls). */
export const WORKSPACE_NAV: Record<Persona, NavItem[]> = {
  student: STUDENT_PRIMARY_NAV,
  partner: WORKSPACE_NAV_GROUPS.partner.flatMap((g) => g.items),
  university: WORKSPACE_NAV_GROUPS.university.flatMap((g) => g.items),
};

/** Flat admin nav — derived from `ADMIN_NAV_GROUPS`. */
export const ADMIN_NAV: NavItem[] = ADMIN_NAV_GROUPS.flatMap((g) => g.items);

/**
 * A workspace shell is one of the three persona shells or the superadmin
 * Platform Admin console. The shared `WorkspaceShell`/`Sidebar`/`Topbar` accept
 * a `Workspace` so the admin console can reuse the same chrome with its own nav
 * and `/admin` base path.
 */
export type Workspace = Persona | "admin";

/** Grouped nav for a workspace (persona shells or the admin console). */
export function navGroupsForWorkspace(workspace: Workspace): NavGroup[] {
  return workspace === "admin" ? ADMIN_NAV_GROUPS : WORKSPACE_NAV_GROUPS[workspace];
}

/** Flat nav item list for a workspace (breadcrumb / route-title resolution). */
export function navItemsForWorkspace(workspace: Workspace): NavItem[] {
  return workspace === "admin" ? ADMIN_NAV : WORKSPACE_NAV[workspace];
}

export const SETTINGS_NAV: NavItem = {
  key: "settings",
  href: "/settings",
  icon: Settings,
};
