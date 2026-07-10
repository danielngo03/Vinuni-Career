/**
 * Primary public-gateway navigation (SCREEN_SPECS §1.1 / DESIGN.md §6.3).
 * Shared by the desktop bar and the mobile drawer so the two never drift.
 * `mega` marks items that render a desktop discovery mega-menu. The trigger is
 * still a real link, so clicking the top-level item opens the full directory.
 */
export interface PublicNavItem {
  /** i18n key under the `nav` namespace. */
  key: "jobs" | "companies" | "careerExplore" | "events" | "employers" | "createCv";
  href: string;
  mega?: "jobs" | "companies" | "events";
}

export const PUBLIC_PRIMARY_NAV: readonly PublicNavItem[] = [
  { key: "jobs", href: "/jobs", mega: "jobs" },
  { key: "companies", href: "/companies", mega: "companies" },
  { key: "events", href: "/events", mega: "events" },
  { key: "careerExplore", href: "/career-explore" },
  { key: "createCv", href: "/student/cv" },
] as const;
