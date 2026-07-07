/**
 * Preset palettes offered by the Restyle inspector (design spec §6, "Palette").
 * Each preset is a small student override merged onto the active template theme
 * via `canvas.theme.palette` — it never forks the template. Presets tune the
 * key document colours (primary/accent/sidebar) while keeping body/muted/rule
 * readable; the renderer still enforces its own structure/contrast.
 *
 * All colours live inside the CV document only — never in app chrome.
 */

import type { CvThemePalette } from "./theme";

export interface PalettePreset {
  key: string;
  /** i18n label key under `cv.restyle.palettes.*` (with a safe fallback name). */
  labelKey: string;
  /** The swatch shown in the picker (usually the accent/sidebar colour). */
  swatch: string;
  /** The partial palette written to `canvas.theme.palette`. */
  palette: Partial<CvThemePalette>;
}

/**
 * A curated, professional, WCAG-minded set. The first entry ("template default")
 * clears overrides so the student can return to the template's own palette.
 */
export const PALETTE_PRESETS: PalettePreset[] = [
  {
    key: "slate",
    labelKey: "slate",
    swatch: "#334155",
    palette: {
      primary: "#0f172a",
      accent: "#334155",
      sidebarBg: "#1e293b",
      sidebarText: "#f1f5f9",
    },
  },
  {
    key: "navy",
    labelKey: "navy",
    swatch: "#1d4ed8",
    palette: {
      primary: "#0f172a",
      accent: "#1d4ed8",
      sidebarBg: "#1e293b",
      sidebarText: "#f1f5f9",
    },
  },
  {
    key: "teal",
    labelKey: "teal",
    swatch: "#0d9488",
    palette: {
      primary: "#0f172a",
      accent: "#0d9488",
      sidebarBg: "#0f766e",
      sidebarText: "#f0fdfa",
    },
  },
  {
    key: "burgundy",
    labelKey: "burgundy",
    swatch: "#9f1239",
    palette: {
      primary: "#4c0519",
      accent: "#9f1239",
      sidebarBg: "#4c0519",
      sidebarText: "#fff1f2",
    },
  },
  {
    key: "forest",
    labelKey: "forest",
    swatch: "#15803d",
    palette: {
      primary: "#14532d",
      accent: "#15803d",
      sidebarBg: "#14532d",
      sidebarText: "#f0fdf4",
    },
  },
  {
    key: "plum",
    labelKey: "plum",
    swatch: "#7e22ce",
    palette: {
      primary: "#3b0764",
      accent: "#7e22ce",
      sidebarBg: "#4c1d95",
      sidebarText: "#faf5ff",
    },
  },
  {
    key: "warm",
    labelKey: "warm",
    swatch: "#c2410c",
    palette: {
      primary: "#431407",
      accent: "#c2410c",
      sidebarBg: "#7c2d12",
      sidebarText: "#fff7ed",
    },
  },
  {
    key: "graphite",
    labelKey: "graphite",
    swatch: "#171717",
    palette: {
      primary: "#171717",
      accent: "#404040",
      sidebarBg: "#171717",
      sidebarText: "#fafafa",
    },
  },
];

/** Font-pairing choices written to `canvas.theme.typography`. */
export type FontPairingKey = "sans" | "serif" | "mono";

export interface FontPairing {
  key: FontPairingKey;
  headingFont: "sans" | "serif" | "mono";
  bodyFont: "sans" | "serif" | "mono";
  /** i18n label key under `cv.restyle.fonts.*`. */
  labelKey: string;
  /** A short preview glyph string. */
  sample: string;
}

export const FONT_PAIRINGS: FontPairing[] = [
  { key: "sans", headingFont: "sans", bodyFont: "sans", labelKey: "sans", sample: "Aa" },
  { key: "serif", headingFont: "serif", bodyFont: "serif", labelKey: "serif", sample: "Aa" },
  { key: "mono", headingFont: "mono", bodyFont: "sans", labelKey: "mono", sample: "Aa" },
];
