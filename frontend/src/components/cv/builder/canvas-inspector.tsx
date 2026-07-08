"use client";

import { useTranslations } from "next-intl";
import {
  ArrowDown,
  ArrowUp,
  Eye,
  EyeSlash,
  TextAlignCenter,
  TextAlignLeft,
  TextAlignRight,
  TextB,
} from "@phosphor-icons/react";
import type { CvCanvasBlock, CvCanvasBlockStyle, CvSection } from "@/lib/api";
import { sectionTypeKey } from "@/lib/cv/sections";
import { cn } from "@/lib/utils";

/**
 * Inspector panel for the selected canvas block. Edits presentation only
 * (alignment/size/emphasis + order/visibility) — never section content
 * (`docs/CV_STUDIO_SPEC.md` "side panels may edit layout, not become the
 * primary editing surface").
 */
export function CanvasInspector({
  block,
  section,
  index,
  total,
  onStyleChange,
  onToggleVisible,
  onShift,
}: {
  block: CvCanvasBlock | null;
  section: CvSection | null;
  index: number;
  total: number;
  onStyleChange: (style: CvCanvasBlockStyle) => void;
  onToggleVisible: (visible: boolean) => void;
  onShift: (direction: "up" | "down") => void;
}) {
  const t = useTranslations("cv");

  if (!block) {
    return (
      <div className="rounded-2xl border border-dashed border-[var(--glass-border-strong)] bg-[var(--glass-surface-light)] p-4 text-center text-xs text-[var(--text-muted)]">
        {t("canvas.inspectorEmpty")}
      </div>
    );
  }

  const style = block.style ?? {};
  const align = style.align ?? "left";
  const fontSize = style.fontSize ?? "md";
  const emphasis = style.emphasis ?? "normal";
  const label = section
    ? (t.has(`sectionTypes.${sectionTypeKey(section.section_type)}`)
        ? t(`sectionTypes.${sectionTypeKey(section.section_type)}`)
        : section.title)
    : block.type;

  return (
    <div className="space-y-4 rounded-2xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] backdrop-blur-md p-4 shadow-[var(--shadow-sm)]">
      <div>
        <p className="text-xs font-bold uppercase tracking-wide text-[var(--text-muted)]">
          {t("canvas.inspectorTitle")}
        </p>
        <p className="mt-0.5 truncate text-sm font-semibold text-[var(--text-primary)]">
          {label}
        </p>
      </div>

      <div>
        <p className="mb-1.5 text-xs font-semibold text-[var(--text-secondary)]">
          {t("canvas.align")}
        </p>
        <div className="flex gap-1.5">
          {(
            [
              { value: "left", Icon: TextAlignLeft },
              { value: "center", Icon: TextAlignCenter },
              { value: "right", Icon: TextAlignRight },
            ] as const
          ).map(({ value, Icon }) => (
            <button
              key={value}
              type="button"
              aria-pressed={align === value}
              aria-label={t(`canvas.align_${value}`)}
              onClick={() => onStyleChange({ align: value })}
              className={cn(
                "flex size-8 items-center justify-center rounded-lg border text-[var(--text-secondary)] outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40",
                align === value
                  ? "border-[var(--brand-primary)]/60 bg-[var(--brand-primary)]/10 text-[var(--brand-primary)]"
                  : "border-[var(--glass-border-strong)] hover:bg-[var(--glass-surface-light)]",
              )}
            >
              <Icon aria-hidden weight="bold" className="size-4" />
            </button>
          ))}
        </div>
      </div>

      <div>
        <p className="mb-1.5 text-xs font-semibold text-[var(--text-secondary)]">
          {t("canvas.fontSize")}
        </p>
        <div className="flex gap-1.5">
          {(["sm", "md", "lg"] as const).map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={fontSize === value}
              onClick={() => onStyleChange({ fontSize: value })}
              className={cn(
                "flex-1 rounded-lg border px-2 py-1.5 text-xs font-semibold outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40",
                fontSize === value
                  ? "border-[var(--brand-primary)]/60 bg-[var(--brand-primary)]/10 text-[var(--brand-primary)]"
                  : "border-[var(--glass-border-strong)] text-[var(--text-secondary)] hover:bg-[var(--glass-surface-light)]",
              )}
            >
              {t(`canvas.fontSize_${value}`)}
            </button>
          ))}
        </div>
      </div>

      <div>
        <p className="mb-1.5 text-xs font-semibold text-[var(--text-secondary)]">
          {t("canvas.emphasis")}
        </p>
        <button
          type="button"
          aria-pressed={emphasis === "bold"}
          aria-label={t("canvas.emphasisBold")}
          onClick={() => onStyleChange({ emphasis: emphasis === "bold" ? "normal" : "bold" })}
          className={cn(
            "flex size-8 items-center justify-center rounded-lg border outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40",
            emphasis === "bold"
              ? "border-[var(--brand-primary)]/60 bg-[var(--brand-primary)]/10 text-[var(--brand-primary)]"
              : "border-[var(--glass-border-strong)] text-[var(--text-secondary)] hover:bg-[var(--glass-surface-light)]",
          )}
        >
          <TextB aria-hidden weight="bold" className="size-4" />
        </button>
      </div>

      <div className="flex items-center justify-between gap-2 border-t border-[var(--glass-border)] pt-3">
        <div className="flex items-center gap-1">
          <button
            type="button"
            aria-label={t("canvas.moveBlockUp")}
            disabled={index <= 0}
            onClick={() => onShift("up")}
            className="rounded-lg p-1.5 text-[var(--text-muted)] outline-none hover:bg-[var(--glass-surface-light)] hover:text-[var(--text-primary)] disabled:opacity-30 focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
          >
            <ArrowUp aria-hidden weight="bold" className="size-4" />
          </button>
          <button
            type="button"
            aria-label={t("canvas.moveBlockDown")}
            disabled={index < 0 || index >= total - 1}
            onClick={() => onShift("down")}
            className="rounded-lg p-1.5 text-[var(--text-muted)] outline-none hover:bg-[var(--glass-surface-light)] hover:text-[var(--text-primary)] disabled:opacity-30 focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
          >
            <ArrowDown aria-hidden weight="bold" className="size-4" />
          </button>
        </div>
        <button
          type="button"
          aria-pressed={block.visible}
          onClick={() => onToggleVisible(!block.visible)}
          className="flex items-center gap-1.5 rounded-lg border border-[var(--glass-border-strong)] px-2.5 py-1.5 text-xs font-semibold text-[var(--text-secondary)] outline-none hover:bg-[var(--glass-surface-light)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
        >
          {block.visible ? (
            <Eye aria-hidden weight="duotone" className="size-3.5" />
          ) : (
            <EyeSlash aria-hidden weight="duotone" className="size-3.5" />
          )}
          {block.visible ? t("canvas.hideBlock") : t("canvas.showBlock")}
        </button>
      </div>
    </div>
  );
}
