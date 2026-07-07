/**
 * The 8 built-in template themes (design spec §5). These are the SAME shape the
 * backend ships in `template.layout_schema` — this map is a FRONTEND FALLBACK so
 * gallery thumbnails render distinct designs even before the backend theme
 * migration/seed (P1-backend) lands, or for older rows with no theme. When a
 * template's API `layout_schema` already carries a full theme, that wins
 * (see {@link themeForTemplate}).
 *
 * All colours live inside the CV document only — they never touch app chrome.
 */

import type { CvTemplate } from "@/lib/api";
import { resolveTheme, type CvTheme, type PartialCvTheme } from "./theme";

/** Raw partial theme presets keyed by template `key`. Merged onto DEFAULT_THEME. */
const BUILTIN_THEMES: Record<string, PartialCvTheme> = {
  classic_ats: {
    layout: { kind: "single", bodyColumns: 1 },
    palette: {
      primary: "#111827",
      accent: "#374151",
      text: "#1f2937",
      muted: "#6b7280",
      rule: "#d1d5db",
      pageBg: "#ffffff",
      sidebarBg: "#1f2937",
      sidebarText: "#f9fafb",
    },
    typography: { headingFont: "serif", bodyFont: "sans", scale: "regular" },
    photo: { show: false, shape: "square", position: "top-left" },
    sectionStyle: { heading: "rule", itemGap: "regular" },
  },
  modern_navy: {
    layout: { kind: "left-sidebar", sidebarWidthPct: 34, bodyColumns: 1 },
    palette: {
      primary: "#0f172a",
      accent: "#1d4ed8",
      sidebarBg: "#1e293b",
      sidebarText: "#f1f5f9",
      text: "#334155",
      muted: "#64748b",
      rule: "#e2e8f0",
      pageBg: "#ffffff",
    },
    typography: { headingFont: "sans", bodyFont: "sans", scale: "regular" },
    photo: { show: true, shape: "circle", position: "sidebar" },
    sectionStyle: { heading: "rule", itemGap: "regular" },
    regions: {
      sidebar: ["skills", "languages", "certifications", "interests"],
      main: ["summary", "experience", "education", "projects", "awards", "activities"],
    },
  },
  modern_teal: {
    layout: { kind: "right-sidebar", sidebarWidthPct: 33, bodyColumns: 1 },
    palette: {
      primary: "#0f172a",
      accent: "#0d9488",
      sidebarBg: "#0f766e",
      sidebarText: "#f0fdfa",
      text: "#334155",
      muted: "#64748b",
      rule: "#e2e8f0",
      pageBg: "#ffffff",
    },
    typography: { headingFont: "sans", bodyFont: "sans", scale: "regular" },
    photo: { show: true, shape: "rounded", position: "sidebar" },
    sectionStyle: { heading: "rule", itemGap: "regular" },
    regions: {
      sidebar: ["skills", "languages", "certifications", "interests"],
      main: ["summary", "experience", "education", "projects", "awards", "activities"],
    },
  },
  minimal_mono: {
    layout: { kind: "single", bodyColumns: 1 },
    palette: {
      primary: "#171717",
      accent: "#525252",
      text: "#404040",
      muted: "#a3a3a3",
      rule: "#e5e5e5",
      pageBg: "#ffffff",
      sidebarBg: "#171717",
      sidebarText: "#fafafa",
    },
    typography: { headingFont: "sans", bodyFont: "sans", scale: "regular", headingCase: "upper" },
    photo: { show: false, shape: "square", position: "top-left" },
    sectionStyle: { heading: "plain", itemGap: "regular" },
  },
  bold_header: {
    layout: { kind: "header-band", bodyColumns: 2 },
    palette: {
      primary: "#18181b",
      accent: "#ea580c",
      sidebarBg: "#18181b",
      sidebarText: "#fafafa",
      text: "#27272a",
      muted: "#71717a",
      rule: "#e4e4e7",
      pageBg: "#ffffff",
    },
    typography: { headingFont: "sans", bodyFont: "sans", scale: "compact" },
    photo: { show: true, shape: "square", position: "header" },
    sectionStyle: { heading: "caps", itemGap: "regular" },
  },
  elegant_serif: {
    layout: { kind: "two-column", bodyColumns: 2 },
    palette: {
      primary: "#3f2d20",
      accent: "#9a6a3f",
      sidebarBg: "#3f2d20",
      sidebarText: "#faf5ef",
      text: "#44403c",
      muted: "#8a7a6c",
      rule: "#e7ddd2",
      pageBg: "#fdfbf7",
    },
    typography: { headingFont: "serif", bodyFont: "serif", scale: "regular" },
    photo: { show: true, shape: "circle", position: "top-left" },
    sectionStyle: { heading: "caps", itemGap: "regular" },
  },
  creative_twotone: {
    layout: { kind: "left-sidebar", sidebarWidthPct: 30, bodyColumns: 1 },
    palette: {
      primary: "#4c1d95",
      accent: "#db2777",
      sidebarBg: "#4c1d95",
      sidebarText: "#f5f3ff",
      text: "#3b3b52",
      muted: "#6d6d8a",
      rule: "#e9e5f5",
      pageBg: "#ffffff",
    },
    typography: { headingFont: "sans", bodyFont: "sans", scale: "regular" },
    photo: { show: true, shape: "rounded", position: "sidebar" },
    sectionStyle: { heading: "band", itemGap: "regular" },
    regions: {
      sidebar: ["skills", "languages", "interests", "certifications"],
      main: ["summary", "experience", "education", "projects", "awards", "activities"],
    },
  },
  tech_chips: {
    layout: { kind: "single", bodyColumns: 1 },
    palette: {
      primary: "#0f172a",
      accent: "#2563eb",
      text: "#1e293b",
      muted: "#64748b",
      rule: "#dbe4f0",
      pageBg: "#ffffff",
      sidebarBg: "#0f172a",
      sidebarText: "#e2e8f0",
    },
    typography: { headingFont: "mono", bodyFont: "sans", scale: "regular" },
    photo: { show: false, shape: "square", position: "top-left" },
    sectionStyle: { heading: "caps", itemGap: "regular" },
  },
};

/**
 * Resolve the theme for a template card. Prefers the API-provided
 * `layout_schema` (which the backend enriches with the full theme); falls back
 * to a built-in preset keyed by `template.key`, then to the neutral default.
 * `overrides` layers a student's `canvas.theme` on top (unused for gallery).
 */
export function themeForTemplate(
  template: Pick<CvTemplate, "key" | "layout_schema"> | null | undefined,
  overrides?: PartialCvTheme,
): CvTheme {
  if (!template) return resolveTheme(undefined, overrides);
  // `layout_schema` is permissively typed on the wire; `resolveTheme` validates
  // and clamps every field, so a structural cast through `unknown` is safe here.
  const apiTheme = (template.layout_schema ?? undefined) as unknown as PartialCvTheme;
  // A template counts as "themed by the API" once it carries a real layout.kind.
  const hasApiTheme = Boolean(apiTheme && (apiTheme.layout?.kind || apiTheme.palette));
  const preset = hasApiTheme ? apiTheme : BUILTIN_THEMES[template.key];
  return resolveTheme(preset, overrides);
}
