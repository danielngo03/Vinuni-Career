/**
 * CV document theme — the canonical visual schema shipped in a template's
 * `layout_schema` (backend uses the identical shape; older rows may be missing
 * or partial, so every consumer merges onto {@link DEFAULT_THEME}).
 *
 * IMPORTANT — colour policy: the APP CHROME is v9 Monochrome (see
 * `docs/DESIGN.md`), but a CV DOCUMENT is user content and is intentionally
 * colourful. All document colour comes from `theme.palette` — never from the
 * app's ink/gray tokens. This module holds no app-chrome tokens.
 *
 * Fonts are web-safe stacks only (no external/Google font loads) so the
 * renderer is CSP-safe and works offline and inside the headless PDF worker.
 */

/** Structural layout family a template uses. */
export type LayoutKind =
  | "single"
  | "left-sidebar"
  | "right-sidebar"
  | "header-band"
  | "two-column";

/** Font family class. Maps to a web-safe stack in {@link FONT_STACK}. */
export type FontKind = "sans" | "serif" | "mono";

export interface CvThemeLayout {
  kind: LayoutKind;
  /** Sidebar width as a percentage of page width (sidebar layouts only). */
  sidebarWidthPct?: number;
  /** Number of columns the MAIN/body region flows into. */
  bodyColumns?: 1 | 2;
}

export interface CvThemePalette {
  /** Headings, name, strong text. */
  primary: string;
  /** Accent detail: rules, timeframes, bullets, skill fills, chips. */
  accent: string;
  /** Sidebar / header-band background. */
  sidebarBg: string;
  /** Text placed on `sidebarBg`. */
  sidebarText: string;
  /** Default body text. */
  text: string;
  /** Muted meta text (subheadings, contact line). */
  muted: string;
  /** Hairline rule colour used in the main body. */
  rule: string;
  /** The A4 page background. */
  pageBg: string;
}

export interface CvThemeTypography {
  headingFont: FontKind;
  bodyFont: FontKind;
  /** `compact` tightens type scale + gaps for dense CVs. */
  scale: "compact" | "regular";
  /** Force heading text to UPPERCASE regardless of section heading style. */
  headingCase?: "normal" | "upper";
}

export interface CvThemePhoto {
  show: boolean;
  shape: "circle" | "square" | "rounded";
  position: "sidebar" | "header" | "top-left";
}

export interface CvThemeSectionStyle {
  /** How each section heading is drawn. */
  heading: "rule" | "band" | "caps" | "plain";
  /** Vertical rhythm between entries/items within a section. */
  itemGap: "tight" | "regular";
}

export interface CvThemeRegions {
  /** section_type ids placed in the sidebar / header band. */
  sidebar: string[];
  /** section_type ids placed in the main body. */
  main: string[];
}

/** The full theme. `version` is a forward-compat guard for the schema. */
export interface CvTheme {
  version: 1;
  layout: CvThemeLayout;
  palette: CvThemePalette;
  typography: CvThemeTypography;
  photo: CvThemePhoto;
  sectionStyle: CvThemeSectionStyle;
  regions: CvThemeRegions;
  /** Canonical section order (section_type ids). */
  order: string[];
}

/**
 * A partial theme as it may arrive from the API (older templates carry only a
 * `section_order` + font hint, newer ones carry the full theme). Every field is
 * optional and permissively typed so {@link resolveTheme} can deep-merge it.
 */
export type PartialCvTheme = {
  version?: number;
  layout?: Partial<CvThemeLayout>;
  palette?: Partial<CvThemePalette>;
  typography?: Partial<CvThemeTypography>;
  photo?: Partial<CvThemePhoto>;
  sectionStyle?: Partial<CvThemeSectionStyle>;
  regions?: Partial<CvThemeRegions>;
  order?: string[];
  /** Legacy field on older seeds — used as a fallback for `order`. */
  section_order?: string[];
} | null | undefined;

/* --------------------------------- Fonts ---------------------------------- */

/**
 * Web-safe font stacks — NO external/network font loads (CSP + offline safe).
 * `sans` intentionally leans on the app's already-loaded Plus Jakarta Sans /
 * Inter / system stack; serif + mono use OS-bundled families only.
 */
export const FONT_STACK: Record<FontKind, string> = {
  sans: "'Plus Jakarta Sans', Inter, system-ui, -apple-system, sans-serif",
  serif: "Georgia, 'Times New Roman', 'Nimbus Roman', serif",
  mono: "'JetBrains Mono', ui-monospace, 'SFMono-Regular', Menlo, Consolas, monospace",
};

/* -------------------------------- Default --------------------------------- */

/**
 * The neutral fallback theme — a clean single-column ATS-style document. Any
 * template that has no (or a partial) `layout_schema` renders through this.
 */
export const DEFAULT_THEME: CvTheme = {
  version: 1,
  layout: { kind: "single", bodyColumns: 1 },
  palette: {
    primary: "#1a1a1a",
    accent: "#334155",
    sidebarBg: "#1e293b",
    sidebarText: "#f8fafc",
    text: "#333333",
    muted: "#6b7280",
    rule: "#d1d5db",
    pageBg: "#ffffff",
  },
  typography: {
    headingFont: "sans",
    bodyFont: "sans",
    scale: "regular",
    headingCase: "normal",
  },
  photo: { show: false, shape: "circle", position: "top-left" },
  sectionStyle: { heading: "rule", itemGap: "regular" },
  regions: {
    sidebar: ["skills", "languages", "certifications", "interests"],
    main: ["summary", "experience", "education", "projects", "awards", "activities"],
  },
  order: [
    "summary",
    "experience",
    "education",
    "projects",
    "skills",
    "certifications",
    "awards",
    "languages",
    "activities",
    "interests",
  ],
};

/* -------------------------------- Merge ----------------------------------- */

function mergeStringArray(base: string[], override?: string[]): string[] {
  return override && override.length > 0 ? override : base;
}

/**
 * Deep-merge a template theme (and optional per-CV student overrides from
 * `canvas.theme`) onto {@link DEFAULT_THEME}. Missing fields fall back to the
 * default; provided fields win. `order` falls back to a legacy `section_order`.
 *
 * @param templateTheme the template's `layout_schema` (may be partial/legacy).
 * @param overrides     the student's `canvas.theme` recolour/refont overrides.
 */
export function resolveTheme(
  templateTheme?: PartialCvTheme,
  overrides?: PartialCvTheme,
): CvTheme {
  const t = templateTheme ?? {};
  const o = overrides ?? {};

  // Layer template over default, then student overrides over that, per group.
  const layout: CvThemeLayout = {
    ...DEFAULT_THEME.layout,
    ...t.layout,
    ...o.layout,
  };
  const palette: CvThemePalette = {
    ...DEFAULT_THEME.palette,
    ...t.palette,
    ...o.palette,
  };
  const typography: CvThemeTypography = {
    ...DEFAULT_THEME.typography,
    ...t.typography,
    ...o.typography,
  };
  const photo: CvThemePhoto = {
    ...DEFAULT_THEME.photo,
    ...t.photo,
    ...o.photo,
  };
  const sectionStyle: CvThemeSectionStyle = {
    ...DEFAULT_THEME.sectionStyle,
    ...t.sectionStyle,
    ...o.sectionStyle,
  };
  const regions: CvThemeRegions = {
    sidebar: mergeStringArray(
      DEFAULT_THEME.regions.sidebar,
      o.regions?.sidebar ?? t.regions?.sidebar,
    ),
    main: mergeStringArray(
      DEFAULT_THEME.regions.main,
      o.regions?.main ?? t.regions?.main,
    ),
  };
  const order = mergeStringArray(
    DEFAULT_THEME.order,
    o.order ?? t.order ?? t.section_order,
  );

  return {
    version: 1,
    layout,
    palette,
    typography,
    photo,
    sectionStyle,
    regions,
    order,
  };
}

/** Resolve a {@link FontKind} to its web-safe CSS stack. */
export function fontStack(kind: FontKind): string {
  return FONT_STACK[kind] ?? FONT_STACK.sans;
}
