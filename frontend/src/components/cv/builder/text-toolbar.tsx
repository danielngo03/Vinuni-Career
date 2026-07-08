"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import {
  TextAlignCenter,
  TextAlignLeft,
  TextAlignRight,
  TextB,
  TextItalic,
  TextT,
  X,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import type {
  ElementStyle,
  ElementStyleAlign,
  ElementStyleSize,
  ElementStyleWeight,
} from "@/lib/api";

/**
 * Contextual text toolbar (design spec §4 — the Canva signature). When a text
 * node on the canvas is focused, a small floating toolbar appears near it with
 * Font · Size · Bold/Italic · Color · Align. Each control writes a single-key
 * patch to `elementStyles[editPath]` via the parent (optimistic + the existing
 * autosave/version machinery). Purely presentational — it owns no CV state.
 *
 * Anchoring: the parent measures the focused node's bounding rect (relative to
 * the canvas scroll container) and passes it as `anchor`; the toolbar clamps
 * itself inside the container so it never overflows on mobile.
 */

const FONTS: Array<{ value: NonNullable<ElementStyle["font"]>; sample: string; labelKey: string }> = [
  { value: "sans", sample: "Aa", labelKey: "sans" },
  { value: "serif", sample: "Aa", labelKey: "serif" },
  { value: "mono", sample: "Aa", labelKey: "mono" },
];

const SIZES: ElementStyleSize[] = ["xs", "sm", "base", "lg", "xl", "2xl"];
const ALIGNS: Array<{ value: ElementStyleAlign; icon: typeof TextAlignLeft }> = [
  { value: "left", icon: TextAlignLeft },
  { value: "center", icon: TextAlignCenter },
  { value: "right", icon: TextAlignRight },
];

/** Anchor rect (canvas-relative px) + the container size for clamping. */
export interface ToolbarAnchor {
  top: number;
  left: number;
  width: number;
  containerWidth: number;
}

export function TextToolbar({
  anchor,
  value,
  onChange,
  onClose,
}: {
  anchor: ToolbarAnchor;
  /** The active element's current override (drives the pressed/selected state). */
  value: ElementStyle | undefined;
  /** Emit a single-key patch (merged into the element's style map by the parent). */
  onChange: (patch: ElementStyle) => void;
  onClose: () => void;
}) {
  const t = useTranslations("cv.textToolbar");
  const ref = useRef<HTMLDivElement>(null);
  const [left, setLeft] = useState(anchor.left);
  const [sizeOpen, setSizeOpen] = useState(false);
  const [fontOpen, setFontOpen] = useState(false);

  // Clamp horizontally inside the container so the toolbar never overflows.
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) {
      setLeft(anchor.left);
      return;
    }
    const w = el.offsetWidth;
    const max = Math.max(4, anchor.containerWidth - w - 4);
    setLeft(Math.min(Math.max(4, anchor.left), max));
  }, [anchor]);

  // Escape closes the toolbar.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const currentSize = value?.size ?? "base";
  const currentAlign = value?.align ?? "left";
  const isBold = value?.weight === "bold" || value?.weight === "semibold";
  const isItalic = value?.italic === true;
  const currentColor = /^#[0-9a-f]{6}$/i.test(value?.color ?? "") ? value!.color! : "";

  return (
    <div
      ref={ref}
      role="toolbar"
      aria-label={t("label")}
      // Anchored above the node; `onMouseDown preventDefault` keeps the canvas
      // node focused so the toolbar stays open while the student clicks controls.
      onMouseDown={(e) => e.preventDefault()}
      style={{ position: "absolute", top: anchor.top, left, zIndex: 30 }}
      className="flex items-center gap-0.5 rounded-xl border border-[var(--border-strong)] bg-[var(--surface-dropdown)] p-1 shadow-[var(--shadow-lg)]"
    >
      {/* Font family */}
      <div className="relative">
        <button
          type="button"
          aria-haspopup="menu"
          aria-expanded={fontOpen}
          onClick={() => {
            setFontOpen((v) => !v);
            setSizeOpen(false);
          }}
          className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs font-semibold text-[var(--text-primary)] outline-none transition-colors hover:bg-[var(--surface-hover)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
        >
          <TextT aria-hidden weight="bold" className="size-3.5" />
          {t("font")}
        </button>
        {fontOpen && (
          <div
            role="menu"
            className="absolute left-0 top-full z-10 mt-1 flex flex-col gap-0.5 rounded-lg border border-[var(--border-strong)] bg-[var(--surface-dropdown)] p-1 shadow-[var(--shadow-lg)]"
          >
            {FONTS.map((f) => {
              const active = (value?.font ?? "sans") === f.value;
              return (
                <button
                  key={f.value}
                  type="button"
                  role="menuitemradio"
                  aria-checked={active}
                  onClick={() => {
                    onChange({ font: f.value });
                    setFontOpen(false);
                  }}
                  className={cn(
                    "flex items-center gap-2 rounded-md px-2 py-1 text-left text-xs outline-none transition-colors hover:bg-[var(--surface-hover)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40",
                    active && "bg-[var(--surface-hover)] font-semibold text-[var(--text-primary)]",
                  )}
                >
                  <span
                    className="text-sm"
                    style={{
                      fontFamily:
                        f.value === "serif"
                          ? "Georgia, serif"
                          : f.value === "mono"
                            ? "ui-monospace, monospace"
                            : "var(--font-sans, system-ui)",
                    }}
                  >
                    {f.sample}
                  </span>
                  {t(`fonts.${f.labelKey}`)}
                </button>
              );
            })}
          </div>
        )}
      </div>

      <span aria-hidden className="mx-0.5 h-5 w-px bg-[var(--glass-border-strong)]" />

      {/* Size */}
      <div className="relative">
        <button
          type="button"
          aria-haspopup="menu"
          aria-expanded={sizeOpen}
          onClick={() => {
            setSizeOpen((v) => !v);
            setFontOpen(false);
          }}
          className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs font-semibold text-[var(--text-primary)] outline-none transition-colors hover:bg-[var(--surface-hover)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
        >
          {t(`sizes.${currentSize}`)}
        </button>
        {sizeOpen && (
          <div
            role="menu"
            className="absolute left-0 top-full z-10 mt-1 flex flex-col gap-0.5 rounded-lg border border-[var(--border-strong)] bg-[var(--surface-dropdown)] p-1 shadow-[var(--shadow-lg)]"
          >
            {SIZES.map((sz) => {
              const active = currentSize === sz;
              return (
                <button
                  key={sz}
                  type="button"
                  role="menuitemradio"
                  aria-checked={active}
                  onClick={() => {
                    onChange({ size: sz === "base" ? undefined : sz });
                    setSizeOpen(false);
                  }}
                  className={cn(
                    "rounded-md px-3 py-1 text-left text-xs outline-none transition-colors hover:bg-[var(--surface-hover)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40",
                    active && "bg-[var(--surface-hover)] font-semibold text-[var(--text-primary)]",
                  )}
                >
                  {t(`sizes.${sz}`)}
                </button>
              );
            })}
          </div>
        )}
      </div>

      <span aria-hidden className="mx-0.5 h-5 w-px bg-[var(--glass-border-strong)]" />

      {/* Bold / Italic */}
      <button
        type="button"
        aria-pressed={isBold}
        aria-label={t("bold")}
        title={t("bold")}
        onClick={() => onChange({ weight: isBold ? "normal" : "bold" })}
        className={cn(
          "rounded-lg p-1.5 outline-none transition-colors hover:bg-[var(--surface-hover)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40",
          isBold ? "bg-[var(--brand-primary)]/10 text-[var(--text-primary)]" : "text-[var(--text-secondary)]",
        )}
      >
        <TextB aria-hidden weight="bold" className="size-4" />
      </button>
      <button
        type="button"
        aria-pressed={isItalic}
        aria-label={t("italic")}
        title={t("italic")}
        onClick={() => onChange({ italic: !isItalic })}
        className={cn(
          "rounded-lg p-1.5 outline-none transition-colors hover:bg-[var(--surface-hover)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40",
          isItalic ? "bg-[var(--brand-primary)]/10 text-[var(--text-primary)]" : "text-[var(--text-secondary)]",
        )}
      >
        <TextItalic aria-hidden weight="bold" className="size-4" />
      </button>

      <span aria-hidden className="mx-0.5 h-5 w-px bg-[var(--glass-border-strong)]" />

      {/* Color */}
      <label
        className="relative flex size-7 cursor-pointer items-center justify-center rounded-lg outline-none transition-colors hover:bg-[var(--surface-hover)]"
        title={t("color")}
      >
        <span className="sr-only">{t("color")}</span>
        <span
          aria-hidden
          className="size-4 rounded-full border border-[var(--border-strong)]"
          style={{ background: currentColor || "conic-gradient(from 180deg, #ef4444, #eab308, #22c55e, #3b82f6, #a855f7, #ef4444)" }}
        />
        <input
          type="color"
          value={currentColor || "#1a1a1a"}
          onChange={(e) => onChange({ color: e.target.value })}
          className="absolute inset-0 cursor-pointer opacity-0"
          aria-label={t("color")}
        />
      </label>
      {currentColor && (
        <button
          type="button"
          aria-label={t("clearColor")}
          title={t("clearColor")}
          onClick={() => onChange({ color: undefined })}
          className="rounded-lg p-1 text-[var(--text-muted)] outline-none transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
        >
          <X aria-hidden weight="bold" className="size-3" />
        </button>
      )}

      <span aria-hidden className="mx-0.5 h-5 w-px bg-[var(--glass-border-strong)]" />

      {/* Align */}
      {ALIGNS.map(({ value: al, icon: Icon }) => {
        const active = currentAlign === al;
        return (
          <button
            key={al}
            type="button"
            aria-pressed={active}
            aria-label={t(`align.${al}`)}
            title={t(`align.${al}`)}
            onClick={() => onChange({ align: al === "left" ? undefined : al })}
            className={cn(
              "rounded-lg p-1.5 outline-none transition-colors hover:bg-[var(--surface-hover)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40",
              active ? "bg-[var(--brand-primary)]/10 text-[var(--text-primary)]" : "text-[var(--text-secondary)]",
            )}
          >
            <Icon aria-hidden weight="bold" className="size-4" />
          </button>
        );
      })}

      <span aria-hidden className="mx-0.5 h-5 w-px bg-[var(--glass-border-strong)]" />

      <button
        type="button"
        aria-label={t("close")}
        title={t("close")}
        onClick={onClose}
        className="rounded-lg p-1.5 text-[var(--text-muted)] outline-none transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
      >
        <X aria-hidden weight="bold" className="size-3.5" />
      </button>
    </div>
  );
}

/** Re-exported for the parent's typed `onChange`. */
export type { ElementStyle, ElementStyleWeight };
