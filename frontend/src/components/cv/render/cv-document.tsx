"use client";

/**
 * `<CvDocument/>` — the ONE renderer that draws a CV. It turns structured CV
 * content + a template theme into a pixel-accurate A4 document, and is the
 * single source of visual truth reused by:
 *   - template gallery thumbnails (sample content, small `scale`),
 *   - the CV canvas editor (the editing surface itself, `editable`),
 *   - (later) the headless PDF print route.
 *
 * App chrome stays v9 Monochrome, but this document is USER CONTENT and is
 * intentionally colourful — every colour comes from `theme.palette`, never from
 * the app's ink/gray tokens. Fonts are web-safe stacks only (CSP/offline safe).
 *
 * ── EDITABLE MODE (design spec §6) ──
 * When `editable`, every text node becomes `contentEditable`, carries a stable
 * `data-edit-path` (see `edit-path.ts`), and reports edits through
 * `onEditCommit(path, value)` (fired on blur + debounced input). Selecting a
 * section/entry reveals on-canvas affordances (add/remove highlight/entry/item,
 * skill level, move up/down) that emit through `onEdit`/`onMoveSection`.
 * Read-only rendering (no `editable`) is byte-for-byte the same as before, so
 * gallery thumbnails and previews are unaffected.
 */

import {
  createContext,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useTranslations } from "next-intl";
import {
  ArrowDown,
  ArrowUp,
  Plus,
  User,
  X,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { DEFAULT_THEME, fontStack, type CvTheme, type FontKind } from "./theme";
import type { CvEdit } from "./edit-path";
import { CONTACT_FIELD_ICON, iconForLink } from "./link-icons";
import type { ElementStyle, ElementStyleMap } from "@/lib/api";

/* ------------------------------ Content model ----------------------------- */

export interface CvDocLink {
  label: string;
  url?: string;
  /** `email|phone|website|linkedin|github|facebook|twitter|instagram|custom`. */
  type?: string;
}

export interface CvDocHeader {
  name: string;
  headline?: string;
  email?: string;
  phone?: string;
  location?: string;
  links: CvDocLink[];
}

export interface CvDocEntry {
  heading?: string;
  subheading?: string;
  timeframe?: string;
  location?: string;
  note?: string;
  highlights: string[];
}

export interface CvDocSkill {
  name: string;
  /** 0–100; when present renders as bars/dots, else as chip/comma text. */
  level?: number;
}

interface CvDocSectionBase {
  id: string;
  section_type: string;
  title: string;
  is_visible: boolean;
  sort_order: number;
}

export type CvDocSection = CvDocSectionBase &
  (
    | { kind: "entries"; entries: CvDocEntry[] }
    | { kind: "skills"; skills: CvDocSkill[] }
    | { kind: "languages"; languages: CvDocSkill[] }
    | { kind: "text"; text?: string; items?: string[] }
    | { kind: "divider" }
  );

export interface CvDocumentPhoto {
  url?: string | null;
}

export interface CvDocumentContent {
  header: CvDocHeader;
  sections: CvDocSection[];
  photo?: CvDocumentPhoto | null;
}

/* ------------------------------- Edit context ----------------------------- */

/** Callbacks the editing surface wires in; absent ⇒ read-only render. */
export interface CvDocumentEditing {
  /** The currently selected section id (reveals its affordances). */
  selectedSectionId: string | null;
  /** Fired on blur + debounced input for a `data-edit-path` text node. */
  onEditCommit: (path: string, value: string) => void;
  /** Fired when a section (or a node inside it) is focused/clicked. */
  onSelectSection: (sectionId: string) => void;
  /** Structural mutations from on-canvas affordances. */
  onEdit: (edit: CvEdit) => void;
  /** Keyboard-accessible section reorder (up/down). */
  onMoveSection: (sectionId: string, direction: "up" | "down") => void;
  /**
   * Contextual text toolbar (design spec §4). When a text node is focused it
   * reports its `data-edit-path` here so the parent can anchor the floating
   * Font/Size/Bold/Italic/Color/Align toolbar next to it. `activeStylePath`
   * mirrors the current selection back so the node can render a selected ring.
   */
  onActiveStylePathChange?: (path: string | null, el: HTMLElement | null) => void;
  activeStylePath?: string | null;
  /** i18n placeholder/label lookups (namespace `cv.canvasEdit`). */
  labels: {
    placeholderName: string;
    placeholderHeadline: string;
    placeholderEmail: string;
    placeholderPhone: string;
    placeholderLocation: string;
    placeholderLinkLabel: string;
    placeholderLinkUrl: string;
    placeholderHeading: string;
    placeholderSubheading: string;
    placeholderTimeframe: string;
    placeholderEntryLocation: string;
    placeholderNote: string;
    placeholderHighlight: string;
    placeholderText: string;
    placeholderSkill: string;
    addHighlight: string;
    addEntry: string;
    addItem: string;
    removeHighlight: string;
    removeEntry: string;
    removeItem: string;
    moveSectionUp: string;
    moveSectionDown: string;
    skillLevel: string;
    editField: (name: string) => string;
  };
}

const EditingContext = createContext<CvDocumentEditing | null>(null);
const useEditing = () => useContext(EditingContext);

/* ------------------------- Per-element style context ---------------------- */

/**
 * Per-element style overrides (design spec §1 "Per-element styles"). Provided in
 * BOTH editable and read-only render so preview/PDF match the editor exactly.
 * `DocText` looks up its own `path` and layers the override on top of the theme
 * style it already computes. When the map is empty the read-only render is
 * byte-stable with the old behaviour (no wrapper elements, no extra styles).
 */
const ElementStylesContext = createContext<ElementStyleMap | null>(null);
const useElementStyle = (path: string): ElementStyle | undefined => {
  const map = useContext(ElementStylesContext);
  return map?.[path];
};

/**
 * Relative font-size multiplier per size token. `base` is the theme's own size
 * for that node (multiplier 1) so a per-element override scales the node's
 * natural size rather than snapping every node to one absolute px.
 */
const SIZE_MULTIPLIER: Record<NonNullable<ElementStyle["size"]>, number> = {
  xs: 0.82,
  sm: 0.92,
  base: 1,
  lg: 1.14,
  xl: 1.3,
  "2xl": 1.5,
};

const WEIGHT_VALUE: Record<NonNullable<ElementStyle["weight"]>, number> = {
  normal: 400,
  medium: 500,
  semibold: 600,
  bold: 700,
};

/**
 * Fold a per-element `ElementStyle` override onto a base CSS style object. Only
 * provided keys win; a valid 6-digit hex is required for `color`. `size` scales
 * the node's existing `fontSize` (falling back to `baseFontSize`).
 */
function applyElementStyle(
  base: React.CSSProperties,
  override: ElementStyle | undefined,
  baseFontSize: number,
): React.CSSProperties {
  if (!override) return base;
  const out: React.CSSProperties = { ...base };
  if (override.font) out.fontFamily = fontStack(override.font as FontKind);
  if (override.size) {
    const current = typeof base.fontSize === "number" ? base.fontSize : baseFontSize;
    out.fontSize = Math.round(current * SIZE_MULTIPLIER[override.size] * 10) / 10;
  }
  if (override.weight) out.fontWeight = WEIGHT_VALUE[override.weight];
  if (override.italic) out.fontStyle = "italic";
  if (override.align) out.textAlign = override.align;
  if (override.color && /^#[0-9a-f]{6}$/i.test(override.color)) out.color = override.color;
  return out;
}

/* ------------------------------- Geometry --------------------------------- */

/** A4 at 96dpi CSS px (210×297mm) — matches the editor's canvas geometry. */
const A4_WIDTH = 794;
const A4_HEIGHT = 1123;

/** Type-scale + gap presets driven by `typography.scale`. */
const SCALE = {
  regular: {
    name: 30,
    headline: 14,
    body: 11,
    heading: 11,
    meta: 10,
    pad: 44,
    sectionGap: 18,
    itemGap: 10,
  },
  compact: {
    name: 26,
    headline: 12.5,
    body: 10,
    heading: 10,
    meta: 9,
    pad: 38,
    sectionGap: 14,
    itemGap: 7,
  },
} as const;

/* --------------------------------- Props ---------------------------------- */

export interface CvDocumentProps {
  content: CvDocumentContent;
  theme?: CvTheme;
  /**
   * Explicit render scale (thumbnails). When omitted the page scales to fit the
   * container width via a ResizeObserver (same pattern as the canvas editor).
   */
  scale?: number;
  className?: string;
  /** Optional accessible label override (defaults to the A4 label). */
  ariaLabel?: string;
  /** When true, text nodes become editable and affordances appear. */
  editable?: boolean;
  /** Editing wiring; required (and only honoured) when `editable`. */
  editing?: CvDocumentEditing;
  /**
   * Per-element style overrides keyed by `data-edit-path` (design spec §1).
   * Applied on top of the theme in BOTH editable and read-only render so the
   * live editor, preview, and PDF stay identical. Omit for the byte-stable
   * default render (gallery thumbnails always omit it).
   */
  elementStyles?: ElementStyleMap | null;
  /**
   * The currently toolbar-selected element path (editable mode only) — the
   * renderer marks that node so the caller can anchor a floating text toolbar.
   */
  activeStylePath?: string | null;
  /** Fired when a text node is focused (editable) — carries its `data-edit-path`. */
  onActiveStylePathChange?: (path: string | null) => void;
}

/**
 * Renders `content` through `theme` on a fixed A4 page, scaled to fit its
 * container (or to an explicit `scale`).
 */
export function CvDocument({
  content,
  theme = DEFAULT_THEME,
  scale: explicitScale,
  className,
  ariaLabel,
  editable = false,
  editing,
  elementStyles,
}: CvDocumentProps) {
  const t = useTranslations("cv.render");

  // ---- Scale-to-fit (same ResizeObserver + transform pattern as editor). ----
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [fitScale, setFitScale] = useState(1);
  useLayoutEffect(() => {
    if (explicitScale !== undefined) return;
    const el = wrapperRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width ?? A4_WIDTH;
      setFitScale(Math.min(1, width / A4_WIDTH));
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [explicitScale]);

  const scale = explicitScale ?? fitScale;
  const s = SCALE[theme.typography.scale] ?? SCALE.regular;
  const label = ariaLabel ?? t("a4Label");
  const activeEditing = editable ? (editing ?? null) : null;

  const page = (
    <div
      role="img"
      aria-label={label}
      style={{
        width: A4_WIDTH,
        minHeight: A4_HEIGHT,
        transform: `scale(${scale})`,
        transformOrigin: "top left",
        background: theme.palette.pageBg,
        color: theme.palette.text,
        fontFamily: fontStack(theme.typography.bodyFont),
        fontSize: s.body,
        lineHeight: 1.45,
        overflow: "hidden",
      }}
    >
      <LayoutRouter content={content} theme={theme} />
    </div>
  );

  const styleMap =
    elementStyles && Object.keys(elementStyles).length > 0 ? elementStyles : null;

  const wrapped = (
    <ElementStylesContext.Provider value={styleMap}>
      <EditingContext.Provider value={activeEditing}>{page}</EditingContext.Provider>
    </ElementStylesContext.Provider>
  );

  // With an explicit scale (thumbnails), size the box to the scaled page so the
  // card doesn't reserve full A4 height.
  if (explicitScale !== undefined) {
    return (
      <div
        className={cn("overflow-hidden", className)}
        style={{ width: A4_WIDTH * scale, height: A4_HEIGHT * scale }}
      >
        {wrapped}
      </div>
    );
  }

  return (
    <div
      ref={wrapperRef}
      className={cn("w-full", className)}
      style={{ height: A4_HEIGHT * scale }}
    >
      {wrapped}
    </div>
  );
}

/* ---------------------------- Editable text node -------------------------- */

/**
 * A single inline-editable text field. Uncontrolled contentEditable that only
 * re-syncs its DOM text from `value` when NOT focused (initial mount + external
 * updates such as undo/redo or a conflict reload) — this avoids the classic
 * caret-jump bug where feeding live keystrokes back through children resets the
 * caret. In read-only mode it renders a plain node (no editing affordances).
 */
function DocText({
  path,
  value,
  placeholder,
  style,
  as = "span",
  multiline = false,
  className,
}: {
  path: string;
  value: string;
  placeholder?: string;
  style?: React.CSSProperties;
  as?: "span" | "div" | "p";
  multiline?: boolean;
  className?: string;
}) {
  const editing = useEditing();
  const override = useElementStyle(path);
  const ref = useRef<HTMLElement>(null);
  const mountedRef = useRef(false);
  const debounceRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (!mountedRef.current) {
      el.textContent = value;
      mountedRef.current = true;
      return;
    }
    if (document.activeElement !== el && el.textContent !== value) {
      el.textContent = value;
    }
  }, [value]);

  useEffect(() => {
    return () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current);
    };
  }, []);

  const Tag = as as "span";
  // Layer the per-element override on top of the base theme style. `baseFontSize`
  // reads the node's own theme size so `size` scales relative to it.
  const baseFontSize =
    typeof style?.fontSize === "number" ? style.fontSize : 11;
  const styled = applyElementStyle(style ?? {}, override, baseFontSize);

  if (!editing) {
    // Read-only: render exactly as text (empty ⇒ nothing, matching old
    // behaviour). Styles include any per-element override so preview/PDF match.
    return value ? (
      <Tag style={styled} className={className}>
        {value}
      </Tag>
    ) : null;
  }

  const isEmpty = value.trim().length === 0;
  const selected = editing.activeStylePath === path;

  return (
    <Tag
      ref={ref as React.Ref<HTMLElement>}
      data-edit-path={path}
      role="textbox"
      aria-label={editing.labels.editField(placeholder ?? path)}
      aria-multiline={multiline ? "true" : undefined}
      contentEditable
      suppressContentEditableWarning
      data-placeholder={placeholder}
      onFocus={(e) =>
        editing.onActiveStylePathChange?.(path, e.currentTarget as HTMLElement)
      }
      onInput={(e) => {
        const text = (e.currentTarget as HTMLElement).textContent ?? "";
        if (debounceRef.current) window.clearTimeout(debounceRef.current);
        debounceRef.current = window.setTimeout(() => {
          editing.onEditCommit(path, text);
        }, 500);
      }}
      onBlur={(e) => {
        if (debounceRef.current) window.clearTimeout(debounceRef.current);
        editing.onEditCommit(path, (e.currentTarget as HTMLElement).textContent ?? "");
      }}
      onKeyDown={(e) => {
        if (!multiline && e.key === "Enter") {
          e.preventDefault();
          (e.currentTarget as HTMLElement).blur();
        }
      }}
      style={styled}
      className={cn(
        "cv-editable outline-none",
        isEmpty && "cv-editable-empty",
        selected && "cv-editable-selected",
        className,
      )}
    />
  );
}

/** Small circular on-canvas action button (delete/add), themed to the surface. */
function CanvasAction({
  label,
  onClick,
  onDark = false,
  variant = "add",
  accent,
}: {
  label: string;
  onClick: () => void;
  onDark?: boolean;
  variant?: "add" | "remove";
  accent: string;
}) {
  const remove = variant === "remove";
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      contentEditable={false}
      onPointerDown={(e) => e.stopPropagation()}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      style={{
        borderColor: onDark ? "rgba(255,255,255,0.5)" : accent,
        color: remove ? "#dc2626" : onDark ? "#ffffff" : accent,
      }}
      className={cn(
        "inline-flex items-center gap-1 rounded-full border bg-white/90 px-1.5 py-0.5 align-middle text-[10px] font-semibold leading-none outline-none transition hover:bg-white focus-visible:ring-2 focus-visible:ring-offset-1",
      )}
    >
      {remove ? (
        <X aria-hidden weight="bold" style={{ width: 10, height: 10 }} />
      ) : (
        <Plus aria-hidden weight="bold" style={{ width: 10, height: 10 }} />
      )}
    </button>
  );
}

/* ------------------------------ Layout router ----------------------------- */

function LayoutRouter({
  content,
  theme,
}: {
  content: CvDocumentContent;
  theme: CvTheme;
}) {
  const s = SCALE[theme.typography.scale] ?? SCALE.regular;
  const kind = theme.layout.kind;

  // Split sections into sidebar vs main by the theme regions, preserving the
  // document's own sort order within each region.
  const { sidebar, main } = useMemo(
    () => splitByRegion(content.sections, theme),
    [content.sections, theme],
  );

  if (kind === "left-sidebar" || kind === "right-sidebar") {
    return (
      <SidebarLayout
        content={content}
        theme={theme}
        sidebarSections={sidebar}
        mainSections={main}
        side={kind === "left-sidebar" ? "left" : "right"}
      />
    );
  }

  if (kind === "header-band") {
    return <HeaderBandLayout content={content} theme={theme} sections={main.length ? [...sidebar, ...main] : content.sections} />;
  }

  // single / two-column
  return (
    <div style={{ padding: s.pad }}>
      <FlowHeader header={content.header} theme={theme} photo={content.photo} />
      <SectionColumns
        sections={content.sections}
        theme={theme}
        columns={theme.layout.bodyColumns === 2 || kind === "two-column" ? 2 : 1}
      />
    </div>
  );
}

/** Distribute sections into sidebar/main regions per theme.regions. */
function splitByRegion(sections: CvDocSection[], theme: CvTheme) {
  const inSidebar = new Set(theme.regions.sidebar);
  const sidebar: CvDocSection[] = [];
  const main: CvDocSection[] = [];
  for (const sec of sections) {
    if (inSidebar.has(sec.section_type)) sidebar.push(sec);
    else main.push(sec);
  }
  return { sidebar, main };
}

/* ------------------------------ Header (flow) ----------------------------- */

function FlowHeader({
  header,
  theme,
  photo,
}: {
  header: CvDocHeader;
  theme: CvTheme;
  photo?: CvDocumentPhoto | null;
}) {
  const s = SCALE[theme.typography.scale] ?? SCALE.regular;
  const editing = useEditing();
  const showPhoto = theme.photo.show && theme.photo.position !== "sidebar";
  const upper = theme.typography.headingCase === "upper";

  return (
    <header
      style={{ marginBottom: s.sectionGap, display: "flex", alignItems: "flex-start", gap: 16 }}
    >
      {showPhoto && (
        <Photo
          url={photo?.url}
          shape={theme.photo.shape}
          bg={theme.palette.rule}
          fg={theme.palette.muted}
          size={72}
        />
      )}
      <div style={{ minWidth: 0, flex: 1 }}>
        <DocText
          as="div"
          path="header.name"
          value={header.name}
          placeholder={editing?.labels.placeholderName}
          style={{
            color: theme.palette.primary,
            fontFamily: fontStack(theme.typography.headingFont),
            fontSize: s.name,
            lineHeight: 1.1,
            fontWeight: 700,
            textTransform: upper ? "uppercase" : undefined,
            letterSpacing: upper ? "0.04em" : undefined,
          }}
        />
        {(header.headline || editing) && (
          <DocText
            as="p"
            path="header.headline"
            value={header.headline ?? ""}
            placeholder={editing?.labels.placeholderHeadline}
            style={{ color: theme.palette.muted, fontSize: s.headline, marginTop: 3 }}
          />
        )}
        <ContactLine header={header} theme={theme} />
      </div>
    </header>
  );
}

function ContactLine({
  header,
  theme,
  onDark = false,
  stack = false,
}: {
  header: CvDocHeader;
  theme: CvTheme;
  onDark?: boolean;
  stack?: boolean;
}) {
  const s = SCALE[theme.typography.scale] ?? SCALE.regular;
  const editing = useEditing();
  const color = onDark ? theme.palette.sidebarText : theme.palette.muted;
  const linkColor = onDark ? theme.palette.sidebarText : theme.palette.accent;
  // Contact icons inherit the surrounding contact colour (monochrome-consistent
  // with the theme — never a per-brand rainbow). Sized to the meta line.
  const iconSize = Math.round(s.meta * 1.05);

  // ── Editable contact block: every contact field + link is inline-editable. ──
  if (editing) {
    return (
      <div
        style={{
          color,
          fontSize: s.meta,
          marginTop: 6,
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          columnGap: 10,
          rowGap: 4,
        }}
      >
        <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
          <CONTACT_FIELD_ICON.email aria-hidden weight="regular" style={{ width: iconSize, height: iconSize, color, flexShrink: 0 }} />
          <DocText
            path="header.email"
            value={header.email ?? ""}
            placeholder={editing.labels.placeholderEmail}
            style={{ color: linkColor }}
          />
        </span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
          <CONTACT_FIELD_ICON.phone aria-hidden weight="regular" style={{ width: iconSize, height: iconSize, color, flexShrink: 0 }} />
          <DocText
            path="header.phone"
            value={header.phone ?? ""}
            placeholder={editing.labels.placeholderPhone}
          />
        </span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
          <CONTACT_FIELD_ICON.location aria-hidden weight="regular" style={{ width: iconSize, height: iconSize, color, flexShrink: 0 }} />
          <DocText
            path="header.location"
            value={header.location ?? ""}
            placeholder={editing.labels.placeholderLocation}
          />
        </span>
        {header.links.map((link, i) => {
          const LinkIcon = iconForLink(link.type, link.url);
          return (
            <span key={i} style={{ display: "inline-flex", alignItems: "center", gap: 3 }}>
              <LinkIcon aria-hidden weight="regular" style={{ width: iconSize, height: iconSize, color: linkColor, flexShrink: 0 }} />
              <DocText
                path={`header.links.${i}.label`}
                value={link.label}
                placeholder={editing.labels.placeholderLinkLabel}
                style={{ color: linkColor }}
              />
              <CanvasAction
                label={editing.labels.removeItem}
                variant="remove"
                onDark={onDark}
                accent={theme.palette.accent}
                onClick={() => editing.onEdit({ kind: "remove-link", index: i })}
              />
            </span>
          );
        })}
        <CanvasAction
          label={editing.labels.addItem}
          accent={theme.palette.accent}
          onDark={onDark}
          onClick={() => editing.onEdit({ kind: "add-link" })}
        />
      </div>
    );
  }

  const IconWrap = ({ icon: I, tone }: { icon: typeof CONTACT_FIELD_ICON.email; tone: string }) => (
    <I aria-hidden weight="regular" style={{ width: iconSize, height: iconSize, color: tone, flexShrink: 0 }} />
  );

  const parts: React.ReactNode[] = [];
  if (header.email)
    parts.push(
      <a key="email" href={`mailto:${header.email}`} style={{ color: linkColor, wordBreak: "break-all", display: "inline-flex", alignItems: "center", gap: 4 }}>
        <IconWrap icon={CONTACT_FIELD_ICON.email} tone={color} />
        {header.email}
      </a>,
    );
  if (header.phone)
    parts.push(
      <span key="phone" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
        <IconWrap icon={CONTACT_FIELD_ICON.phone} tone={color} />
        {header.phone}
      </span>,
    );
  if (header.location)
    parts.push(
      <span key="loc" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
        <IconWrap icon={CONTACT_FIELD_ICON.location} tone={color} />
        {header.location}
      </span>,
    );
  for (const link of header.links) {
    const LinkIcon = iconForLink(link.type, link.url);
    parts.push(
      <a
        key={link.url ?? link.label}
        href={link.url ?? "#"}
        target="_blank"
        rel="noopener noreferrer"
        style={{ color: linkColor, wordBreak: "break-all", display: "inline-flex", alignItems: "center", gap: 4 }}
      >
        <IconWrap icon={LinkIcon} tone={linkColor} />
        {link.label}
      </a>,
    );
  }
  if (parts.length === 0) return null;

  if (stack) {
    return (
      <ul
        style={{
          color,
          fontSize: s.meta,
          marginTop: 8,
          display: "flex",
          flexDirection: "column",
          gap: 4,
          listStyle: "none",
        }}
      >
        {parts.map((p, i) => (
          <li key={i}>{p}</li>
        ))}
      </ul>
    );
  }

  return (
    <p
      style={{
        color,
        fontSize: s.meta,
        marginTop: 6,
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
        columnGap: 8,
        rowGap: 2,
      }}
    >
      {parts.map((p, i) => (
        <span key={i} style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
          {i > 0 && <span aria-hidden style={{ color }}>·</span>}
          {p}
        </span>
      ))}
    </p>
  );
}

/* ------------------------------ Sidebar layout ---------------------------- */

function SidebarLayout({
  content,
  theme,
  sidebarSections,
  mainSections,
  side,
}: {
  content: CvDocumentContent;
  theme: CvTheme;
  sidebarSections: CvDocSection[];
  mainSections: CvDocSection[];
  side: "left" | "right";
}) {
  const s = SCALE[theme.typography.scale] ?? SCALE.regular;
  const editing = useEditing();
  const widthPct = clamp(theme.layout.sidebarWidthPct ?? 34, 24, 44);
  const showPhoto = theme.photo.show && theme.photo.position === "sidebar";

  const sidebar = (
    <aside
      style={{
        width: `${widthPct}%`,
        flexShrink: 0,
        display: "flex",
        flexDirection: "column",
        background: theme.palette.sidebarBg,
        color: theme.palette.sidebarText,
        padding: s.pad * 0.7,
      }}
    >
      {showPhoto && (
        <div style={{ marginBottom: 16, display: "flex", justifyContent: "center" }}>
          <Photo
            url={content.photo?.url}
            shape={theme.photo.shape}
            bg={"rgba(255,255,255,0.12)"}
            fg={theme.palette.sidebarText}
            size={96}
          />
        </div>
      )}
      <ContactLine header={content.header} theme={theme} onDark stack />
      <div style={{ marginTop: s.sectionGap }}>
        {sidebarSections.map((sec) => (
          <SectionBlock key={sec.id} section={sec} theme={theme} region="sidebar" />
        ))}
      </div>
    </aside>
  );

  const mainName = (
    <header style={{ marginBottom: s.sectionGap }}>
      <DocText
        as="div"
        path="header.name"
        value={content.header.name}
        placeholder={editing?.labels.placeholderName}
        style={{
          color: theme.palette.primary,
          fontFamily: fontStack(theme.typography.headingFont),
          fontSize: s.name,
          lineHeight: 1.1,
          fontWeight: 700,
          textTransform: theme.typography.headingCase === "upper" ? "uppercase" : undefined,
          letterSpacing: theme.typography.headingCase === "upper" ? "0.04em" : undefined,
        }}
      />
      {(content.header.headline || editing) && (
        <DocText
          as="p"
          path="header.headline"
          value={content.header.headline ?? ""}
          placeholder={editing?.labels.placeholderHeadline}
          style={{ color: theme.palette.muted, fontSize: s.headline, marginTop: 3 }}
        />
      )}
    </header>
  );

  const main = (
    <div style={{ padding: s.pad, flex: 1, minWidth: 0 }}>
      {mainName}
      <div>
        {mainSections.map((sec) => (
          <SectionBlock key={sec.id} section={sec} theme={theme} region="main" />
        ))}
      </div>
    </div>
  );

  return (
    <div style={{ display: "flex", alignItems: "stretch", minHeight: A4_HEIGHT }}>
      {side === "left" ? (
        <>
          {sidebar}
          {main}
        </>
      ) : (
        <>
          {main}
          {sidebar}
        </>
      )}
    </div>
  );
}

/* ---------------------------- Header-band layout -------------------------- */

function HeaderBandLayout({
  content,
  theme,
  sections,
}: {
  content: CvDocumentContent;
  theme: CvTheme;
  sections: CvDocSection[];
}) {
  const s = SCALE[theme.typography.scale] ?? SCALE.regular;
  const editing = useEditing();
  const showPhoto = theme.photo.show;

  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: A4_HEIGHT }}>
      <header
        style={{
          background: theme.palette.sidebarBg,
          color: theme.palette.sidebarText,
          padding: s.pad * 0.8,
          display: "flex",
          alignItems: "center",
          gap: 20,
        }}
      >
        {showPhoto && (
          <Photo
            url={content.photo?.url}
            shape={theme.photo.shape}
            bg={"rgba(255,255,255,0.14)"}
            fg={theme.palette.sidebarText}
            size={84}
          />
        )}
        <div style={{ minWidth: 0, flex: 1 }}>
          <DocText
            as="div"
            path="header.name"
            value={content.header.name}
            placeholder={editing?.labels.placeholderName}
            style={{
              color: theme.palette.sidebarText,
              fontFamily: fontStack(theme.typography.headingFont),
              fontSize: s.name,
              lineHeight: 1.1,
              fontWeight: 700,
              textTransform: theme.typography.headingCase === "upper" ? "uppercase" : undefined,
              letterSpacing: theme.typography.headingCase === "upper" ? "0.05em" : undefined,
            }}
          />
          {(content.header.headline || editing) && (
            <DocText
              as="p"
              path="header.headline"
              value={content.header.headline ?? ""}
              placeholder={editing?.labels.placeholderHeadline}
              style={{ fontSize: s.headline, marginTop: 3, opacity: 0.9 }}
            />
          )}
          <ContactLine header={content.header} theme={theme} onDark />
        </div>
      </header>
      <div style={{ padding: s.pad, flex: 1 }}>
        <SectionColumns
          sections={sections}
          theme={theme}
          columns={theme.layout.bodyColumns === 2 ? 2 : 1}
        />
      </div>
    </div>
  );
}

/* ------------------------------ Section columns --------------------------- */

/** Flow sections in 1 or 2 columns (balanced by count for 2-col). */
function SectionColumns({
  sections,
  theme,
  columns,
}: {
  sections: CvDocSection[];
  theme: CvTheme;
  columns: 1 | 2;
}) {
  if (columns === 2 && sections.length > 1) {
    const mid = Math.ceil(sections.length / 2);
    const left = sections.slice(0, mid);
    const right = sections.slice(mid);
    return (
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", columnGap: 24 }}>
        <div style={{ minWidth: 0 }}>
          {left.map((sec) => (
            <SectionBlock key={sec.id} section={sec} theme={theme} region="main" />
          ))}
        </div>
        <div style={{ minWidth: 0 }}>
          {right.map((sec) => (
            <SectionBlock key={sec.id} section={sec} theme={theme} region="main" />
          ))}
        </div>
      </div>
    );
  }
  return (
    <div>
      {sections.map((sec) => (
        <SectionBlock key={sec.id} section={sec} theme={theme} region="main" />
      ))}
    </div>
  );
}

/* ------------------------------ Section block ----------------------------- */

function SectionBlock({
  section,
  theme,
  region,
}: {
  section: CvDocSection;
  theme: CvTheme;
  region: "sidebar" | "main";
}) {
  const t = useTranslations("cv.sectionTypes");
  const s = SCALE[theme.typography.scale] ?? SCALE.regular;
  const editing = useEditing();
  const onDark = region === "sidebar";
  const bodyColor = onDark ? theme.palette.sidebarText : theme.palette.text;

  const labelKey = section.section_type.replace(/[^a-z0-9_]/gi, "_");
  const heading = t.has(labelKey) ? t(labelKey) : section.title;
  const selected = editing?.selectedSectionId === section.id;

  // Divider: a presentation-only hairline, no heading/body. Selectable in the
  // editor (so it can be reordered/removed via the outline) but never editable.
  if (section.kind === "divider") {
    return (
      <section
        data-section-id={section.id}
        onClick={editing ? () => editing.onSelectSection(section.id) : undefined}
        style={{
          marginTop: s.sectionGap * 0.4,
          marginBottom: s.sectionGap,
          borderRadius: editing ? 4 : undefined,
          outline: selected
            ? `1.5px solid ${onDark ? "rgba(255,255,255,0.6)" : theme.palette.accent}`
            : undefined,
          outlineOffset: selected ? 4 : undefined,
        }}
      >
        <span
          aria-hidden
          style={{
            display: "block",
            height: 1,
            background: onDark ? "rgba(255,255,255,0.25)" : theme.palette.rule,
          }}
        />
      </section>
    );
  }

  return (
    <section
      data-section-id={section.id}
      onClick={editing ? () => editing.onSelectSection(section.id) : undefined}
      onFocus={editing ? () => editing.onSelectSection(section.id) : undefined}
      style={{
        marginBottom: s.sectionGap,
        position: "relative",
        borderRadius: editing ? 4 : undefined,
        outline: selected
          ? `1.5px solid ${onDark ? "rgba(255,255,255,0.6)" : theme.palette.accent}`
          : undefined,
        outlineOffset: selected ? 4 : undefined,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <SectionHeading text={heading} theme={theme} region={region} />
        {editing && selected && (
          <span
            contentEditable={false}
            style={{ display: "inline-flex", gap: 2, flexShrink: 0 }}
          >
            <SectionMoveButton
              label={editing.labels.moveSectionUp}
              onDark={onDark}
              accent={theme.palette.accent}
              onClick={() => editing.onMoveSection(section.id, "up")}
              direction="up"
            />
            <SectionMoveButton
              label={editing.labels.moveSectionDown}
              onDark={onDark}
              accent={theme.palette.accent}
              onClick={() => editing.onMoveSection(section.id, "down")}
              direction="down"
            />
          </span>
        )}
      </div>
      <div style={{ marginTop: 8, color: bodyColor }}>
        {section.kind === "entries" && (
          <EntryList section={section} theme={theme} region={region} selected={selected} />
        )}
        {section.kind === "skills" && (
          <SkillList section={section} theme={theme} region={region} selected={selected} />
        )}
        {section.kind === "languages" && (
          <LanguageList section={section} theme={theme} region={region} selected={selected} />
        )}
        {section.kind === "text" && (
          <TextBlock section={section} theme={theme} region={region} selected={selected} />
        )}
      </div>
    </section>
  );
}

function SectionMoveButton({
  label,
  onClick,
  onDark,
  accent,
  direction,
}: {
  label: string;
  onClick: () => void;
  onDark: boolean;
  accent: string;
  direction: "up" | "down";
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      contentEditable={false}
      onPointerDown={(e) => e.stopPropagation()}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      style={{
        borderColor: onDark ? "rgba(255,255,255,0.5)" : accent,
        color: onDark ? "#ffffff" : accent,
      }}
      className="inline-flex size-5 items-center justify-center rounded border bg-white/90 outline-none transition hover:bg-white focus-visible:ring-2"
    >
      {direction === "up" ? (
        <ArrowUp aria-hidden weight="bold" style={{ width: 11, height: 11 }} />
      ) : (
        <ArrowDown aria-hidden weight="bold" style={{ width: 11, height: 11 }} />
      )}
    </button>
  );
}

/* ------------------------------ Section heading --------------------------- */

function SectionHeading({
  text,
  theme,
  region,
}: {
  text: string;
  theme: CvTheme;
  region: "sidebar" | "main";
}) {
  const s = SCALE[theme.typography.scale] ?? SCALE.regular;
  const onDark = region === "sidebar";
  const style = theme.sectionStyle.heading;
  const upper = theme.typography.headingCase === "upper" || style === "caps";
  const fontFamily = fontStack(theme.typography.headingFont);

  const baseColor = onDark ? theme.palette.sidebarText : theme.palette.primary;
  const accent = theme.palette.accent;
  const rule = onDark ? "rgba(255,255,255,0.25)" : theme.palette.rule;

  const common: React.CSSProperties = {
    fontFamily,
    fontSize: s.heading,
    fontWeight: 700,
    textTransform: upper ? "uppercase" : undefined,
    letterSpacing: upper ? "0.1em" : "0.02em",
    color: baseColor,
  };

  if (style === "band") {
    return (
      <h2
        style={{
          ...common,
          background: onDark ? "rgba(255,255,255,0.14)" : accent,
          color: onDark ? theme.palette.sidebarText : theme.palette.pageBg,
          padding: "3px 8px",
          borderRadius: 3,
          display: "inline-block",
        }}
      >
        {text}
      </h2>
    );
  }

  if (style === "caps") {
    return (
      <h2 style={{ ...common, borderBottom: `1px solid ${rule}`, paddingBottom: 4, flex: 1 }}>
        {text}
      </h2>
    );
  }

  if (style === "plain") {
    return <h2 style={common}>{text}</h2>;
  }

  // "rule" — label with a short accent underline.
  return (
    <h2 style={{ ...common }}>
      {text}
      <span
        aria-hidden
        style={{
          display: "block",
          width: 34,
          height: 2,
          marginTop: 3,
          background: onDark ? theme.palette.sidebarText : accent,
        }}
      />
    </h2>
  );
}

/* -------------------------------- Entries --------------------------------- */

function EntryList({
  section,
  theme,
  region,
  selected,
}: {
  section: Extract<CvDocSection, { kind: "entries" }>;
  theme: CvTheme;
  region: "sidebar" | "main";
  selected: boolean;
}) {
  const s = SCALE[theme.typography.scale] ?? SCALE.regular;
  const editing = useEditing();
  const gap = theme.sectionStyle.itemGap === "tight" ? s.itemGap * 0.6 : s.itemGap;
  const onDark = region === "sidebar";
  const headingColor = onDark ? theme.palette.sidebarText : theme.palette.primary;
  const metaColor = onDark ? withAlpha(theme.palette.sidebarText, 0.75) : theme.palette.muted;
  const timeColor = onDark ? theme.palette.sidebarText : theme.palette.accent;
  const entries = section.entries;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap }}>
      {entries.map((entry, i) => (
        <div key={i} style={{ position: "relative" }}>
          {(entry.heading || editing) && (
            <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
              <DocText
                as="p"
                path={`section.${section.id}.entries.${i}.heading`}
                value={entry.heading ?? ""}
                placeholder={editing?.labels.placeholderHeading}
                style={{ color: headingColor, fontWeight: 600, fontSize: s.body }}
              />
              {editing && selected && (
                <CanvasAction
                  label={editing.labels.removeEntry}
                  variant="remove"
                  onDark={onDark}
                  accent={theme.palette.accent}
                  onClick={() =>
                    editing.onEdit({ kind: "remove-entry", sectionId: section.id, index: i })
                  }
                />
              )}
            </div>
          )}
          <MetaLine
            sectionId={section.id}
            entryIndex={i}
            entry={entry}
            metaColor={metaColor}
            timeColor={timeColor}
            fontSize={s.meta}
          />
          {(entry.note || editing) && (
            <DocText
              as="p"
              path={`section.${section.id}.entries.${i}.note`}
              value={entry.note ?? ""}
              placeholder={editing?.labels.placeholderNote}
              style={{ color: metaColor, fontSize: s.meta, marginTop: 2 }}
            />
          )}
          {(entry.highlights.length > 0 || (editing && selected)) && (
            <Bullets
              sectionId={section.id}
              entryIndex={i}
              items={entry.highlights}
              theme={theme}
              region={region}
              selected={selected}
            />
          )}
        </div>
      ))}
      {editing && selected && (
        <button
          type="button"
          contentEditable={false}
          onPointerDown={(e) => e.stopPropagation()}
          onClick={(e) => {
            e.stopPropagation();
            editing.onEdit({ kind: "add-entry", sectionId: section.id });
          }}
          style={{
            color: onDark ? theme.palette.sidebarText : theme.palette.accent,
            borderColor: onDark ? "rgba(255,255,255,0.4)" : theme.palette.accent,
            fontSize: s.meta,
          }}
          className="inline-flex w-fit items-center gap-1 rounded-full border border-dashed bg-white/70 px-2 py-0.5 font-semibold outline-none transition hover:bg-white focus-visible:ring-2"
        >
          <Plus aria-hidden weight="bold" style={{ width: 11, height: 11 }} />
          {editing.labels.addEntry}
        </button>
      )}
    </div>
  );
}

function MetaLine({
  sectionId,
  entryIndex,
  entry,
  metaColor,
  timeColor,
  fontSize,
}: {
  sectionId: string;
  entryIndex: number;
  entry: CvDocEntry;
  metaColor: string;
  timeColor: string;
  fontSize: number;
}) {
  const editing = useEditing();

  if (editing) {
    return (
      <p
        style={{
          fontSize,
          marginTop: 1,
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          columnGap: 8,
          rowGap: 2,
        }}
      >
        <DocText
          path={`section.${sectionId}.entries.${entryIndex}.subheading`}
          value={entry.subheading ?? ""}
          placeholder={editing.labels.placeholderSubheading}
          style={{ color: metaColor }}
        />
        <DocText
          path={`section.${sectionId}.entries.${entryIndex}.timeframe`}
          value={entry.timeframe ?? ""}
          placeholder={editing.labels.placeholderTimeframe}
          style={{ color: timeColor, fontWeight: 500 }}
        />
        <DocText
          path={`section.${sectionId}.entries.${entryIndex}.location`}
          value={entry.location ?? ""}
          placeholder={editing.labels.placeholderEntryLocation}
          style={{ color: metaColor }}
        />
      </p>
    );
  }

  const parts: React.ReactNode[] = [];
  if (entry.subheading)
    parts.push(<span key="sub" style={{ color: metaColor }}>{entry.subheading}</span>);
  if (entry.timeframe)
    parts.push(<span key="time" style={{ color: timeColor, fontWeight: 500 }}>{entry.timeframe}</span>);
  if (entry.location)
    parts.push(<span key="loc" style={{ color: metaColor }}>{entry.location}</span>);
  if (parts.length === 0) return null;
  return (
    <p
      style={{
        fontSize,
        marginTop: 1,
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
        columnGap: 6,
      }}
    >
      {parts.map((p, i) => (
        <span key={i} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          {i > 0 && <span aria-hidden style={{ color: metaColor }}>·</span>}
          {p}
        </span>
      ))}
    </p>
  );
}

function Bullets({
  sectionId,
  entryIndex,
  items,
  theme,
  region,
  selected,
}: {
  sectionId: string;
  entryIndex: number;
  items: string[];
  theme: CvTheme;
  region: "sidebar" | "main";
  selected: boolean;
}) {
  const s = SCALE[theme.typography.scale] ?? SCALE.regular;
  const editing = useEditing();
  const onDark = region === "sidebar";
  const bulletColor = onDark ? theme.palette.sidebarText : theme.palette.accent;
  const textColor = onDark ? theme.palette.sidebarText : theme.palette.text;
  return (
    <ul
      style={{
        marginTop: 4,
        fontSize: s.body,
        display: "flex",
        flexDirection: "column",
        gap: 4,
        listStyle: "none",
      }}
    >
      {items.map((item, j) => (
        <li key={j} style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
          <span aria-hidden style={{ color: bulletColor, lineHeight: 1.4 }}>
            •
          </span>
          <DocText
            as="span"
            multiline
            path={`section.${sectionId}.entries.${entryIndex}.highlights.${j}`}
            value={item}
            placeholder={editing?.labels.placeholderHighlight}
            style={{ color: textColor, flex: 1 }}
          />
          {editing && selected && (
            <CanvasAction
              label={editing.labels.removeHighlight}
              variant="remove"
              onDark={onDark}
              accent={theme.palette.accent}
              onClick={() =>
                editing.onEdit({
                  kind: "remove-highlight",
                  sectionId,
                  entryIndex,
                  highlightIndex: j,
                })
              }
            />
          )}
        </li>
      ))}
      {editing && selected && (
        <li style={{ listStyle: "none", marginTop: 2 }}>
          <button
            type="button"
            contentEditable={false}
            onPointerDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation();
              editing.onEdit({ kind: "add-highlight", sectionId, entryIndex });
            }}
            style={{
              color: onDark ? theme.palette.sidebarText : theme.palette.accent,
              fontSize: s.meta,
            }}
            className="inline-flex items-center gap-1 rounded px-1 py-0.5 font-semibold outline-none transition hover:bg-black/5 focus-visible:ring-2"
          >
            <Plus aria-hidden weight="bold" style={{ width: 10, height: 10 }} />
            {editing.labels.addHighlight}
          </button>
        </li>
      )}
    </ul>
  );
}

/* --------------------------------- Skills --------------------------------- */

type SkillRender = "bars" | "chips" | "comma";

function skillRenderMode(theme: CvTheme, region: "sidebar" | "main"): SkillRender {
  if (region === "sidebar") return "bars";
  const heading = theme.sectionStyle.heading;
  // Classic/minimal ATS style (rule/plain single column) reads best as comma text.
  if (
    (heading === "rule" || heading === "plain") &&
    theme.layout.kind === "single" &&
    theme.typography.headingFont !== "mono"
  ) {
    return "comma";
  }
  return "chips";
}

function SkillList({
  section,
  theme,
  region,
  selected,
}: {
  section: Extract<CvDocSection, { kind: "skills" }>;
  theme: CvTheme;
  region: "sidebar" | "main";
  selected: boolean;
}) {
  const editing = useEditing();
  // Bars mode gives us the natural place for the level control, so when editing
  // we always render bars (regardless of theme) so students can edit levels.
  const mode = editing ? "bars" : skillRenderMode(theme, region);
  const s = SCALE[theme.typography.scale] ?? SCALE.regular;
  const onDark = region === "sidebar";
  const skills = section.skills;

  if (mode === "comma") {
    return (
      <p style={{ fontSize: s.body, color: theme.palette.text }}>
        {skills.map((sk) => sk.name).join(" · ")}
      </p>
    );
  }

  if (mode === "chips") {
    const chipBg = withAlpha(theme.palette.accent, 0.12);
    const chipText = theme.palette.accent;
    return (
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {skills.map((sk, i) => (
          <span
            key={i}
            style={{
              background: chipBg,
              color: chipText,
              fontSize: s.meta,
              padding: "2px 8px",
              borderRadius: 999,
              fontWeight: 500,
            }}
          >
            {sk.name}
          </span>
        ))}
      </div>
    );
  }

  // bars
  const trackBg = onDark ? "rgba(255,255,255,0.18)" : withAlpha(theme.palette.accent, 0.15);
  const fillBg = onDark ? theme.palette.sidebarText : theme.palette.accent;
  const labelColor = onDark ? theme.palette.sidebarText : theme.palette.text;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {skills.map((sk, i) => {
        const level = clamp(sk.level ?? 70, 0, 100);
        return (
          <div key={i}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <DocText
                as="span"
                path={`section.${section.id}.items.${i}.name`}
                value={sk.name}
                placeholder={editing?.labels.placeholderSkill}
                style={{ fontSize: s.meta, color: labelColor, flex: 1 }}
              />
              {editing && selected && (
                <CanvasAction
                  label={editing.labels.removeItem}
                  variant="remove"
                  onDark={onDark}
                  accent={theme.palette.accent}
                  onClick={() =>
                    editing.onEdit({ kind: "remove-item", sectionId: section.id, index: i })
                  }
                />
              )}
            </div>
            {editing && selected ? (
              <SkillLevelControl
                value={sk.level ?? 70}
                trackBg={trackBg}
                fillBg={fillBg}
                label={editing.labels.skillLevel}
                onChange={(v) =>
                  editing.onEdit({ kind: "set-skill-level", sectionId: section.id, index: i, level: v })
                }
              />
            ) : (
              <div
                style={{
                  background: trackBg,
                  height: 4,
                  borderRadius: 999,
                  marginTop: 3,
                  width: "100%",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{ width: `${level}%`, background: fillBg, height: "100%", borderRadius: 999 }}
                />
              </div>
            )}
          </div>
        );
      })}
      {editing && selected && (
        <AddItemButton section={section} theme={theme} onDark={onDark} />
      )}
    </div>
  );
}

/** Inline 0–100 skill-level range (drag) — updates `items.{i}.level`. */
function SkillLevelControl({
  value,
  trackBg,
  fillBg,
  label,
  onChange,
}: {
  value: number;
  trackBg: string;
  fillBg: string;
  label: string;
  onChange: (v: number) => void;
}) {
  return (
    <span
      contentEditable={false}
      style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 3 }}
      onPointerDown={(e) => e.stopPropagation()}
    >
      <input
        type="range"
        min={0}
        max={100}
        step={5}
        value={clamp(value, 0, 100)}
        aria-label={label}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{ flex: 1, accentColor: fillBg, height: 4 }}
      />
      <span style={{ fontSize: 9, color: fillBg, width: 24, textAlign: "right" }}>
        {clamp(value, 0, 100)}
      </span>
      <span aria-hidden style={{ display: "none", background: trackBg }} />
    </span>
  );
}

function AddItemButton({
  section,
  theme,
  onDark,
}: {
  section: CvDocSection;
  theme: CvTheme;
  onDark: boolean;
}) {
  const editing = useEditing();
  const s = SCALE[theme.typography.scale] ?? SCALE.regular;
  if (!editing) return null;
  return (
    <button
      type="button"
      contentEditable={false}
      onPointerDown={(e) => e.stopPropagation()}
      onClick={(e) => {
        e.stopPropagation();
        editing.onEdit({ kind: "add-item", sectionId: section.id });
      }}
      style={{
        color: onDark ? theme.palette.sidebarText : theme.palette.accent,
        borderColor: onDark ? "rgba(255,255,255,0.4)" : theme.palette.accent,
        fontSize: s.meta,
      }}
      className="inline-flex w-fit items-center gap-1 rounded-full border border-dashed bg-white/70 px-2 py-0.5 font-semibold outline-none transition hover:bg-white focus-visible:ring-2"
    >
      <Plus aria-hidden weight="bold" style={{ width: 11, height: 11 }} />
      {editing.labels.addItem}
    </button>
  );
}

/* ------------------------------- Languages -------------------------------- */

function LanguageList({
  section,
  theme,
  region,
  selected,
}: {
  section: Extract<CvDocSection, { kind: "languages" }>;
  theme: CvTheme;
  region: "sidebar" | "main";
  selected: boolean;
}) {
  const s = SCALE[theme.typography.scale] ?? SCALE.regular;
  const editing = useEditing();
  const onDark = region === "sidebar";
  const labelColor = onDark ? theme.palette.sidebarText : theme.palette.text;
  const dotOn = onDark ? theme.palette.sidebarText : theme.palette.accent;
  const dotOff = onDark ? "rgba(255,255,255,0.25)" : theme.palette.rule;
  const languages = section.languages;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {languages.map((lang, i) => {
        const hasLevel = typeof lang.level === "number";
        const filled = hasLevel ? Math.round(clamp(lang.level!, 0, 100) / 20) : 0;
        return (
          <div
            key={i}
            style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}
          >
            <DocText
              as="span"
              path={`section.${section.id}.items.${i}.name`}
              value={lang.name}
              placeholder={editing?.labels.placeholderSkill}
              style={{ fontSize: s.body, color: labelColor, flex: 1 }}
            />
            <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
              {hasLevel && (
                <span style={{ display: "flex", alignItems: "center", gap: 4 }} aria-hidden>
                  {[0, 1, 2, 3, 4].map((d) => (
                    <span
                      key={d}
                      style={{
                        width: 5,
                        height: 5,
                        borderRadius: 999,
                        background: d < filled ? dotOn : dotOff,
                      }}
                    />
                  ))}
                </span>
              )}
              {editing && selected && (
                <CanvasAction
                  label={editing.labels.removeItem}
                  variant="remove"
                  onDark={onDark}
                  accent={theme.palette.accent}
                  onClick={() =>
                    editing.onEdit({ kind: "remove-item", sectionId: section.id, index: i })
                  }
                />
              )}
            </span>
          </div>
        );
      })}
      {editing && selected && (
        <AddItemButton section={section} theme={theme} onDark={onDark} />
      )}
    </div>
  );
}

/* ------------------------------- Text block ------------------------------- */

function TextBlock({
  section,
  theme,
  region,
  selected,
}: {
  section: Extract<CvDocSection, { kind: "text" }>;
  theme: CvTheme;
  region: "sidebar" | "main";
  selected: boolean;
}) {
  const s = SCALE[theme.typography.scale] ?? SCALE.regular;
  const editing = useEditing();
  const onDark = region === "sidebar";
  const color = onDark ? theme.palette.sidebarText : theme.palette.text;

  // A `text`-mode section is either a single paragraph (`text`) or a bullet
  // list (`items`). When editing we keep whichever shape it already has.
  const isList = section.items !== undefined && section.text === undefined;

  if (isList) {
    const items = section.items ?? [];
    return (
      <ul
        style={{
          fontSize: s.body,
          display: "flex",
          flexDirection: "column",
          gap: 4,
          listStyle: "none",
        }}
      >
        {items.map((item, i) => (
          <li key={i} style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
            <span aria-hidden style={{ color: onDark ? theme.palette.sidebarText : theme.palette.accent }}>
              •
            </span>
            <DocText
              as="span"
              multiline
              path={`section.${section.id}.items.${i}.text`}
              value={item}
              placeholder={editing?.labels.placeholderText}
              style={{ color, flex: 1 }}
            />
            {editing && selected && (
              <CanvasAction
                label={editing.labels.removeItem}
                variant="remove"
                onDark={onDark}
                accent={theme.palette.accent}
                onClick={() =>
                  editing.onEdit({ kind: "remove-item", sectionId: section.id, index: i })
                }
              />
            )}
          </li>
        ))}
        {editing && selected && <AddItemButton section={section} theme={theme} onDark={onDark} />}
      </ul>
    );
  }

  if (section.text !== undefined || editing) {
    return (
      <DocText
        as="p"
        multiline
        path={`section.${section.id}.text`}
        value={section.text ?? ""}
        placeholder={editing?.labels.placeholderText}
        style={{ fontSize: s.body, color, lineHeight: 1.5 }}
      />
    );
  }
  return null;
}

/* --------------------------------- Photo ---------------------------------- */

function Photo({
  url,
  shape,
  bg,
  fg,
  size,
}: {
  url?: string | null;
  shape: "circle" | "square" | "rounded";
  bg: string;
  fg: string;
  size: number;
}) {
  const radius = shape === "circle" ? "9999px" : shape === "rounded" ? "12px" : "0px";
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: radius,
        background: bg,
        overflow: "hidden",
        flexShrink: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      {url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={url} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
      ) : (
        <User aria-hidden weight="fill" style={{ color: fg, width: size * 0.5, height: size * 0.5 }} />
      )}
    </div>
  );
}

/* --------------------------------- Utils ---------------------------------- */

function clamp(n: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, n));
}

/**
 * Overlay a hex colour with an alpha (for chip tints / track fills). Falls back
 * to a translucent slate if the input is not a 6-digit hex.
 */
function withAlpha(hex: string, alpha: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return `rgba(100,116,139,${alpha})`;
  const int = parseInt(m[1]!, 16);
  const r = (int >> 16) & 255;
  const g = (int >> 8) & 255;
  const b = int & 255;
  return `rgba(${r},${g},${b},${alpha})`;
}
