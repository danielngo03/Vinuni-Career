"use client";

import { useTranslations } from "next-intl";
import {
  ArrowUp,
  ArrowDown,
  DotsSixVertical,
  Eye,
  EyeSlash,
  Plus,
  TextAlignLeft,
  Trash,
} from "@phosphor-icons/react";
import { Button } from "@/components/ui";
import type { CvSection, CvSectionContent } from "@/lib/api";
import {
  buildListContent,
  buildTextContent,
  sectionItems,
  sectionMode,
  sectionText,
  sectionTypeKey,
} from "@/lib/cv/sections";
import { cn } from "@/lib/utils";

/**
 * Controlled editor for a single CV section. The parent owns section content
 * (single source for the live A4 preview) and the optimistic-version save queue.
 * `onContentChange` updates the working copy immediately; `onFlush` persists.
 */
export function CvSectionEditor({
  section,
  index,
  total,
  onContentChange,
  onFlush,
  onToggleVisible,
  onMove,
  onArmDrag,
}: {
  section: CvSection;
  index: number;
  total: number;
  onContentChange: (content: CvSectionContent) => void;
  onFlush: () => void;
  onToggleVisible: (visible: boolean) => void;
  onMove: (direction: "up" | "down") => void;
  /** Arms the parent's drag-to-reorder for this section (pointer-driven). */
  onArmDrag?: () => void;
}) {
  const t = useTranslations("cv");
  const mode = sectionMode(section);
  const items = sectionItems(section.content);

  const labelKey = `sectionTypes.${sectionTypeKey(section.section_type)}`;
  const label = t.has(labelKey) ? t(labelKey) : section.title;
  const placeholderKey = `sectionHints.${sectionTypeKey(section.section_type)}`;
  const placeholder = t.has(placeholderKey)
    ? t(placeholderKey)
    : t("sectionHints.generic");

  const dimmed = !section.is_visible;

  function setItem(i: number, value: string) {
    const next = [...items];
    next[i] = value;
    onContentChange(buildListContent(next));
  }
  function addItem() {
    onContentChange(buildListContent([...items, ""]));
    onFlush();
  }
  function removeItem(i: number) {
    onContentChange(buildListContent(items.filter((_, idx) => idx !== i)));
    onFlush();
  }
  function moveItem(i: number, dir: -1 | 1) {
    const j = i + dir;
    if (j < 0 || j >= items.length) return;
    const next = [...items];
    [next[i], next[j]] = [next[j]!, next[i]!];
    onContentChange(buildListContent(next));
    onFlush();
  }

  return (
    <section
      aria-label={label}
      className={cn(
        "rounded-2xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] backdrop-blur-md p-4 shadow-[var(--shadow-sm)] sm:p-5",
        dimmed && "opacity-70",
      )}
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          {onArmDrag && (
            <button
              type="button"
              aria-label={t("editor.dragHandle", { name: label })}
              title={t("editor.dragHandle", { name: label })}
              onPointerDown={onArmDrag}
              className="cursor-grab touch-none rounded p-0.5 text-[var(--text-muted)] outline-none hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40 active:cursor-grabbing"
            >
              <DotsSixVertical aria-hidden weight="bold" className="size-4" />
            </button>
          )}
          <span className="flex size-5 shrink-0 items-center justify-center rounded-md icon-chip-primary shadow-sm">
            <TextAlignLeft aria-hidden weight="duotone" className="size-3 text-white" />
          </span>
          <h3 className="text-sm font-bold text-[var(--text-primary)]">
            {label}
          </h3>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="xs"
            aria-label={t("editor.moveUp")}
            disabled={index === 0}
            onClick={() => onMove("up")}
          >
            <ArrowUp aria-hidden weight="bold" className="size-4" />
          </Button>
          <Button
            variant="ghost"
            size="xs"
            aria-label={t("editor.moveDown")}
            disabled={index === total - 1}
            onClick={() => onMove("down")}
          >
            <ArrowDown aria-hidden weight="bold" className="size-4" />
          </Button>
          <Button
            variant="ghost"
            size="xs"
            aria-pressed={section.is_visible}
            aria-label={
              section.is_visible ? t("editor.hide") : t("editor.show")
            }
            onClick={() => onToggleVisible(!section.is_visible)}
          >
            {section.is_visible ? (
              <Eye aria-hidden weight="duotone" className="size-4" />
            ) : (
              <EyeSlash aria-hidden weight="duotone" className="size-4" />
            )}
          </Button>
        </div>
      </div>

      {mode === "text" ? (
        <div>
          <label htmlFor={`sec-${section.id}`} className="sr-only">
            {label}
          </label>
          <textarea
            id={`sec-${section.id}`}
            rows={4}
            value={sectionText(section.content)}
            placeholder={placeholder}
            onChange={(e) => onContentChange(buildTextContent(e.target.value))}
            onBlur={onFlush}
            className="w-full resize-y rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] px-3.5 py-2.5 text-sm text-[var(--text-primary)] outline-none backdrop-blur-sm transition-colors placeholder:text-[var(--text-muted)] focus:border-[var(--brand-primary)]/50 focus:bg-[var(--glass-surface-heavy)] focus:ring-2 focus:ring-[var(--brand-primary)]/30"
          />
        </div>
      ) : (
        <div className="space-y-2">
          {items.length === 0 && (
            <p className="rounded-lg border border-[var(--glass-border)] bg-[var(--glass-surface-light)] px-3 py-2 text-xs text-[var(--text-secondary)]">
              {placeholder}
            </p>
          )}
          {items.map((value, i) => (
            <div key={i} className="flex items-start gap-1.5">
              <label htmlFor={`sec-${section.id}-item-${i}`} className="sr-only">
                {label} — {i + 1}
              </label>
              <textarea
                id={`sec-${section.id}-item-${i}`}
                rows={2}
                value={value}
                onChange={(e) => setItem(i, e.target.value)}
                onBlur={onFlush}
                className="min-h-[2.5rem] w-full resize-y rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none backdrop-blur-sm transition-colors focus:border-[var(--brand-primary)]/50 focus:bg-[var(--glass-surface-heavy)] focus:ring-2 focus:ring-[var(--brand-primary)]/30"
              />
              <div className="flex shrink-0 flex-col">
                <button
                  type="button"
                  aria-label={t("editor.moveItemUp")}
                  disabled={i === 0}
                  onClick={() => moveItem(i, -1)}
                  className="rounded p-1 text-[var(--text-muted)] outline-none hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] disabled:opacity-30"
                >
                  <ArrowUp aria-hidden weight="bold" className="size-3.5" />
                </button>
                <button
                  type="button"
                  aria-label={t("editor.moveItemDown")}
                  disabled={i === items.length - 1}
                  onClick={() => moveItem(i, 1)}
                  className="rounded p-1 text-[var(--text-muted)] outline-none hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] disabled:opacity-30"
                >
                  <ArrowDown aria-hidden weight="bold" className="size-3.5" />
                </button>
              </div>
              <button
                type="button"
                aria-label={t("editor.removeItem")}
                onClick={() => removeItem(i)}
                className="shrink-0 rounded p-1.5 text-[var(--text-muted)] outline-none hover:bg-[var(--red-50)] hover:text-[var(--brand-red)]"
              >
                <Trash aria-hidden weight="duotone" className="size-4" />
              </button>
            </div>
          ))}
          <Button variant="ghost" size="sm" onClick={addItem}>
            <Plus aria-hidden weight="bold" className="size-4" />
            {t("editor.addItem")}
          </Button>
        </div>
      )}
    </section>
  );
}
