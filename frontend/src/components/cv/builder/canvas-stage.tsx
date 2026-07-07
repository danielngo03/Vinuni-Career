"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { MagnifyingGlassMinus, MagnifyingGlassPlus, Warning } from "@phosphor-icons/react";
import { CvDocument } from "@/components/cv/render";
import type { CvDocumentContent, CvDocumentEditing, CvTheme } from "@/components/cv/render";
import { CANVAS_PAGE_HEIGHT_PX, CANVAS_WIDTH_PX } from "@/lib/cv/canvas";
import { cn } from "@/lib/utils";
import type { ElementStyle, ElementStyleMap } from "@/lib/api";
import { TextToolbar, type ToolbarAnchor } from "./text-toolbar";

const ZOOM_STEPS = [0.6, 0.75, 0.9, 1, 1.15, 1.3] as const;

/**
 * The editing stage: an A4 frame that fits the editable `<CvDocument/>` to the
 * available width (or an explicit zoom), and warns when the rendered document
 * exceeds one A4 page (measured, not heuristic — design spec §6 "page-break /
 * overflow warning against A4 height"). No horizontal overflow on mobile: the
 * page scales to width and the whole stage scrolls vertically only.
 *
 * Also hosts the contextual text toolbar (design spec §4): when a text node is
 * focused it reports its `data-edit-path` + DOM node through
 * `editing.onActiveStylePathChange`; the stage measures that node relative to
 * its scroll container and anchors a floating Font/Size/Bold/Italic/Color/Align
 * toolbar above it. Style changes flow back up via `onStylePatch`.
 */
export function CanvasStage({
  content,
  theme,
  editing,
  photoControl,
  elementStyles,
  activeStylePath,
  activeStyle,
  onStylePatch,
  onCloseToolbar,
}: {
  content: CvDocumentContent;
  theme: CvTheme;
  editing: CvDocumentEditing;
  /** Rendered above the page (the photo add/edit affordance). */
  photoControl?: React.ReactNode;
  /** Per-element style overrides applied by the renderer. */
  elementStyles?: ElementStyleMap | null;
  /** The `data-edit-path` of the toolbar-selected node (null ⇒ toolbar hidden). */
  activeStylePath?: string | null;
  /** The active node's current override (drives the toolbar pressed states). */
  activeStyle?: ElementStyle;
  /** A single-key style patch for the active node. */
  onStylePatch?: (patch: ElementStyle) => void;
  /** Dismiss the toolbar + clear the active path. */
  onCloseToolbar?: () => void;
}) {
  const t = useTranslations("cv");
  const wrapperRef = useRef<HTMLDivElement>(null);
  const pageRef = useRef<HTMLDivElement>(null);
  const activeElRef = useRef<HTMLElement | null>(null);
  const [fitScale, setFitScale] = useState(1);
  /** null ⇒ fit-to-width; a number ⇒ user-chosen zoom step. */
  const [zoom, setZoom] = useState<number | null>(null);
  const [overflow, setOverflow] = useState(false);
  const [anchor, setAnchor] = useState<ToolbarAnchor | null>(null);

  // Fit-to-width scale (never upscale past 1 for the auto fit).
  useLayoutEffect(() => {
    const el = wrapperRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width ?? CANVAS_WIDTH_PX;
      setFitScale(Math.min(1, width / CANVAS_WIDTH_PX));
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const scale = zoom ?? fitScale;

  // Measure the real rendered document height against a single A4 page.
  const measure = useCallback(() => {
    const el = pageRef.current;
    if (!el) return;
    // The inner CvDocument sets its own transform; measure the un-transformed
    // scrollHeight of the page content via the child image node.
    const doc = el.querySelector<HTMLElement>('[role="img"]');
    const h = doc?.scrollHeight ?? el.scrollHeight;
    setOverflow(h > CANVAS_PAGE_HEIGHT_PX + 4);
  }, []);

  useEffect(() => {
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const el = pageRef.current;
    if (!el) return;
    const observer = new ResizeObserver(() => measure());
    observer.observe(el);
    const doc = el.querySelector<HTMLElement>('[role="img"]');
    if (doc) observer.observe(doc);
    return () => observer.disconnect();
  }, [measure, content, theme]);

  const zoomIndex = ZOOM_STEPS.findIndex((z) => z >= scale - 0.001);
  function stepZoom(dir: -1 | 1) {
    const base = zoomIndex < 0 ? ZOOM_STEPS.length - 1 : zoomIndex;
    const next = Math.max(0, Math.min(ZOOM_STEPS.length - 1, base + dir));
    setZoom(ZOOM_STEPS[next]!);
  }

  // ---- Contextual toolbar anchoring -------------------------------------
  // Measure the active node relative to the scroll container's content box so
  // the absolutely-positioned toolbar tracks it through scroll + zoom.
  const measureAnchor = useCallback(() => {
    const el = activeElRef.current;
    const container = wrapperRef.current;
    if (!el || !container || !el.isConnected) {
      setAnchor(null);
      return;
    }
    const elRect = el.getBoundingClientRect();
    const cRect = container.getBoundingClientRect();
    const top = elRect.top - cRect.top + container.scrollTop - 44; // 44px above the node
    const left = elRect.left - cRect.left + container.scrollLeft;
    setAnchor({
      top: Math.max(0, top),
      left,
      width: elRect.width,
      containerWidth: container.clientWidth,
    });
  }, []);

  // Wrap the parent's active-path callback so the stage also captures the node
  // for measurement. (The parent still owns the persisted `activeStylePath`.)
  const parentOnActive = editing.onActiveStylePathChange;
  const editingWithToolbar: CvDocumentEditing = {
    ...editing,
    activeStylePath,
    onActiveStylePathChange: (path, el) => {
      activeElRef.current = el;
      parentOnActive?.(path, el);
    },
  };

  // Re-measure when the selection, scale, or content changes; and on scroll.
  useLayoutEffect(() => {
    if (!activeStylePath) {
      setAnchor(null);
      activeElRef.current = null;
      return;
    }
    // Resolve the node fresh from the DOM (survives re-renders that drop the ref).
    const node = pageRef.current?.querySelector<HTMLElement>(
      `[data-edit-path="${CSS.escape(activeStylePath)}"]`,
    );
    if (node) activeElRef.current = node;
    measureAnchor();
  }, [activeStylePath, scale, content, elementStyles, measureAnchor]);

  useEffect(() => {
    if (!activeStylePath) return;
    const container = wrapperRef.current;
    if (!container) return;
    const onScroll = () => measureAnchor();
    container.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      container.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, [activeStylePath, measureAnchor]);

  return (
    <div className="flex flex-col gap-3">
      {/* Toolbar: photo affordance + zoom + page-break warning. */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">{photoControl}</div>
        <div className="flex items-center gap-1.5">
          {overflow && (
            <span
              role="status"
              className="flex items-center gap-1.5 rounded-lg bg-[var(--amber-100)] px-2.5 py-1 text-xs font-medium text-[var(--amber-700)]"
            >
              <Warning aria-hidden weight="fill" className="size-3.5 shrink-0" />
              {t("preview.pageBreakWarning")}
            </span>
          )}
          <div className="flex items-center gap-0.5 rounded-lg border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] p-0.5">
            <button
              type="button"
              aria-label={t("canvas.zoomOut")}
              onClick={() => stepZoom(-1)}
              className="rounded-md p-1 text-[var(--text-secondary)] outline-none hover:bg-[var(--glass-surface-light)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
            >
              <MagnifyingGlassMinus aria-hidden weight="bold" className="size-4" />
            </button>
            <button
              type="button"
              onClick={() => setZoom(null)}
              aria-label={t("canvas.zoomFit")}
              className="min-w-[3rem] rounded-md px-1.5 py-1 text-center text-xs font-semibold tabular-nums text-[var(--text-secondary)] outline-none hover:bg-[var(--glass-surface-light)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
            >
              {Math.round(scale * 100)}%
            </button>
            <button
              type="button"
              aria-label={t("canvas.zoomIn")}
              onClick={() => stepZoom(1)}
              className="rounded-md p-1 text-[var(--text-secondary)] outline-none hover:bg-[var(--glass-surface-light)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
            >
              <MagnifyingGlassPlus aria-hidden weight="bold" className="size-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Scroll container: horizontal scroll only kicks in when zoomed past the
          available width; the page never causes a page-wide horizontal scroll.
          `relative` anchors the absolutely-positioned contextual toolbar. */}
      <div
        ref={wrapperRef}
        className="relative w-full overflow-auto rounded-xl border border-[var(--glass-border)] bg-[var(--surface-secondary)] p-3 sm:p-5"
      >
        <div
          ref={pageRef}
          className={cn(
            "mx-auto overflow-hidden rounded-lg shadow-[0_4px_28px_rgba(0,0,0,0.12)]",
          )}
          style={{ width: CANVAS_WIDTH_PX * scale }}
        >
          <CvDocument
            content={content}
            theme={theme}
            scale={scale}
            editable
            editing={editingWithToolbar}
            elementStyles={elementStyles}
          />
        </div>

        {activeStylePath && anchor && onStylePatch && onCloseToolbar && (
          <TextToolbar
            anchor={anchor}
            value={activeStyle}
            onChange={onStylePatch}
            onClose={onCloseToolbar}
          />
        )}
      </div>
    </div>
  );
}
