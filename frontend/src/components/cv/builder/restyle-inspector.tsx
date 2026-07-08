"use client";

import { useTranslations } from "next-intl";
import { Check, PaintBrushBroad } from "@phosphor-icons/react";
import { CvDocument, SAMPLE_CV, themeForTemplate } from "@/components/cv/render";
import type { PartialCvTheme } from "@/components/cv/render";
import type { CvCanvasTheme, CvTemplate } from "@/lib/api";
import {
  PALETTE_PRESETS,
  FONT_PAIRINGS,
  type FontPairingKey,
} from "@/components/cv/render/palettes";
import { cn } from "@/lib/utils";

/**
 * The Restyle inspector (design spec §6, "Restyle rail — the Canva feel").
 * Lets a student switch template, recolour the palette, change the font
 * pairing, and toggle density. Template changes patch `template_id`; palette /
 * font / density write into `canvas.theme` (a per-CV override the renderer
 * merges live). Every change is applied optimistically by the parent and
 * autosaved — this component is purely presentational.
 */
export function RestyleInspector({
  templates,
  templatesLoading,
  activeTemplateId,
  canvasTheme,
  onSelectTemplate,
  onPaletteChange,
  onAccentChange,
  onFontChange,
  onDensityChange,
}: {
  templates: CvTemplate[];
  templatesLoading: boolean;
  activeTemplateId: string;
  /** Current per-CV overrides (drives the selected-state highlights). */
  canvasTheme: CvCanvasTheme | null | undefined;
  onSelectTemplate: (templateId: string) => void;
  onPaletteChange: (palette: Record<string, string>) => void;
  onAccentChange: (accent: string) => void;
  onFontChange: (pairing: FontPairingKey) => void;
  onDensityChange: (scale: "regular" | "compact") => void;
}) {
  const t = useTranslations("cv");

  const currentAccent = canvasTheme?.palette?.accent ?? "";
  const currentFont = (canvasTheme?.typography?.headingFont as FontPairingKey | undefined) ?? null;
  const currentScale = (canvasTheme?.typography?.scale as "regular" | "compact" | undefined) ?? null;

  return (
    <section
      aria-label={t("restyle.title")}
      className="space-y-5 rounded-2xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] p-4 shadow-[var(--shadow-sm)] backdrop-blur-md"
    >
      <div className="flex items-center gap-2">
        <span className="flex size-6 shrink-0 items-center justify-center rounded-lg icon-chip-primary shadow-sm">
          <PaintBrushBroad aria-hidden weight="duotone" className="size-3.5 text-white" />
        </span>
        <h3 className="text-sm font-bold text-[var(--text-primary)]">{t("restyle.title")}</h3>
      </div>

      {/* -------------------------------- Template ------------------------- */}
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
          {t("restyle.template")}
        </p>
        {templatesLoading ? (
          <div className="grid grid-cols-3 gap-2">
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className="aspect-[210/297] animate-pulse rounded-md bg-[var(--glass-surface-light)]"
              />
            ))}
          </div>
        ) : (
          <ul className="grid grid-cols-3 gap-2">
            {templates.map((tpl) => {
              const selected = tpl.id === activeTemplateId;
              const thumbTheme = themeForTemplate(tpl);
              return (
                <li key={tpl.id}>
                  <button
                    type="button"
                    aria-pressed={selected}
                    onClick={() => onSelectTemplate(tpl.id)}
                    title={tpl.name}
                    className={cn(
                      "group relative block w-full overflow-hidden rounded-md border bg-white outline-none transition-shadow focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40",
                      selected
                        ? "border-[var(--brand-primary)] ring-2 ring-[var(--brand-primary)]/40"
                        : "border-[var(--glass-border-strong)] hover:border-[var(--text-muted)]",
                    )}
                  >
                    <div className="pointer-events-none aspect-[210/297] w-full overflow-hidden">
                      <CvDocument content={SAMPLE_CV} theme={thumbTheme} scale={0.135} />
                    </div>
                    {selected && (
                      <span className="absolute right-1 top-1 flex size-4 items-center justify-center rounded-full bg-[var(--brand-primary)] text-white shadow-sm">
                        <Check aria-hidden weight="bold" className="size-2.5" />
                      </span>
                    )}
                    <span className="block truncate border-t border-[var(--glass-border)] px-1 py-0.5 text-center text-[10px] font-medium text-[var(--text-secondary)]">
                      {tpl.name}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* -------------------------------- Palette -------------------------- */}
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
          {t("restyle.palette")}
        </p>
        <div className="flex flex-wrap gap-2">
          {PALETTE_PRESETS.map((preset) => {
            const selected = currentAccent.toLowerCase() === preset.swatch.toLowerCase();
            const label = t.has(`restyle.palettes.${preset.labelKey}`)
              ? t(`restyle.palettes.${preset.labelKey}`)
              : preset.key;
            return (
              <button
                key={preset.key}
                type="button"
                aria-pressed={selected}
                aria-label={label}
                title={label}
                onClick={() => onPaletteChange(preset.palette as Record<string, string>)}
                className={cn(
                  "relative size-8 rounded-full outline-none transition focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-[var(--brand-primary)]/50",
                  selected
                    ? "ring-2 ring-offset-2 ring-[var(--brand-primary)]"
                    : "ring-1 ring-[var(--glass-border-strong)]",
                )}
                style={{ background: preset.swatch }}
              >
                {selected && (
                  <Check
                    aria-hidden
                    weight="bold"
                    className="absolute inset-0 m-auto size-3.5 text-white drop-shadow"
                  />
                )}
              </button>
            );
          })}
        </div>
        <div className="mt-3 flex items-center gap-2">
          <label
            htmlFor="cv-accent-color"
            className="text-xs font-medium text-[var(--text-secondary)]"
          >
            {t("restyle.accentLabel")}
          </label>
          <input
            id="cv-accent-color"
            type="color"
            value={/^#[0-9a-f]{6}$/i.test(currentAccent) ? currentAccent : "#334155"}
            onChange={(e) => onAccentChange(e.target.value)}
            className="size-7 cursor-pointer rounded-md border border-[var(--glass-border-strong)] bg-transparent p-0.5 outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
          />
        </div>
      </div>

      {/* --------------------------------- Font ---------------------------- */}
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
          {t("restyle.font")}
        </p>
        <div className="flex gap-1.5">
          {FONT_PAIRINGS.map((pairing) => {
            const selected = currentFont === pairing.headingFont;
            const label = t.has(`restyle.fonts.${pairing.labelKey}`)
              ? t(`restyle.fonts.${pairing.labelKey}`)
              : pairing.key;
            const family =
              pairing.headingFont === "serif"
                ? "Georgia, serif"
                : pairing.headingFont === "mono"
                  ? "ui-monospace, monospace"
                  : "var(--font-sans, system-ui)";
            return (
              <button
                key={pairing.key}
                type="button"
                aria-pressed={selected}
                onClick={() => onFontChange(pairing.key)}
                className={cn(
                  "flex flex-1 flex-col items-center gap-0.5 rounded-lg border px-2 py-1.5 outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40",
                  selected
                    ? "border-[var(--brand-primary)]/60 bg-[var(--brand-primary)]/10"
                    : "border-[var(--glass-border-strong)] hover:bg-[var(--glass-surface-light)]",
                )}
              >
                <span
                  className={cn(
                    "text-base font-bold leading-none",
                    selected ? "text-[var(--brand-primary)]" : "text-[var(--text-primary)]",
                  )}
                  style={{ fontFamily: family }}
                >
                  {pairing.sample}
                </span>
                <span
                  className={cn(
                    "text-[10px] font-medium",
                    selected ? "text-[var(--brand-primary)]" : "text-[var(--text-secondary)]",
                  )}
                >
                  {label}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* -------------------------------- Density -------------------------- */}
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
          {t("restyle.density")}
        </p>
        <div className="flex gap-1.5">
          {(["regular", "compact"] as const).map((scale) => {
            const selected = currentScale === scale;
            return (
              <button
                key={scale}
                type="button"
                aria-pressed={selected}
                onClick={() => onDensityChange(scale)}
                className={cn(
                  "flex-1 rounded-lg border px-2 py-1.5 text-xs font-semibold outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40",
                  selected
                    ? "border-[var(--brand-primary)]/60 bg-[var(--brand-primary)]/10 text-[var(--brand-primary)]"
                    : "border-[var(--glass-border-strong)] text-[var(--text-secondary)] hover:bg-[var(--glass-surface-light)]",
                )}
              >
                {t(`restyle.density_${scale}`)}
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}

/** Convenience re-export used by the parent to type the accent-only override. */
export type { PartialCvTheme };
