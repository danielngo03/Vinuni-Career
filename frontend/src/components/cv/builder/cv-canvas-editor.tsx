"use client";

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useTranslations } from "next-intl";
import { DotsSixVertical, ImageSquare, Plus, Trash, Warning } from "@phosphor-icons/react";
import type { CvCanvasBlock, CvCanvasPhoto, CvSection, CvSectionContent } from "@/lib/api";
import {
  CANVAS_PADDING_FRACTION,
  CANVAS_PAGE_HEIGHT_PX,
  CANVAS_WIDTH_PX,
  computeOverflowingIndices,
} from "@/lib/cv/canvas";
import {
  buildListContent,
  buildTextContent,
  sectionItems,
  sectionMode,
  sectionText,
  sectionTypeKey,
} from "@/lib/cv/sections";
import { cn } from "@/lib/utils";

const STYLE_TO_CLASS: Record<string, string> = {
  left: "text-left",
  center: "text-center",
  right: "text-right",
  sm: "text-[0.7rem]",
  md: "text-[0.78rem]",
  lg: "text-[0.92rem]",
};

/**
 * The real A4 canvas editor (`docs/CV_STUDIO_SPEC.md`): click-to-select
 * blocks, inline text editing, pointer-based block reordering, keyboard block
 * navigation, and layout-measured page-break warnings. Block layout (order /
 * visibility / style) is presentation metadata persisted via
 * `PATCH /cvs/{id}/canvas`; section CONTENT edits still flow through the
 * existing per-section autosave (the parent's `onSectionTextChange`/`Flush`).
 */
export function CvCanvasEditor({
  title,
  sections,
  blocks,
  selectedBlockId,
  onSelectBlock,
  onMoveBlock,
  onShiftBlock,
  onToggleBlockVisible,
  onSectionTextChange,
  onSectionTextFlush,
  photo,
  onEditPhoto,
  className,
}: {
  title: string;
  sections: CvSection[];
  blocks: CvCanvasBlock[];
  selectedBlockId: string | null;
  onSelectBlock: (id: string | null) => void;
  onMoveBlock: (fromId: string, toId: string) => void;
  onShiftBlock: (id: string, direction: "up" | "down") => void;
  onToggleBlockVisible: (id: string, visible: boolean) => void;
  onSectionTextChange: (sectionId: string, content: CvSectionContent) => void;
  onSectionTextFlush: (sectionId: string) => void;
  photo?: CvCanvasPhoto | null;
  onEditPhoto: () => void;
  className?: string;
}) {
  const t = useTranslations("cv");

  const sectionById = useMemo(() => {
    const map = new Map<string, CvSection>();
    for (const s of sections) map.set(s.id, s);
    return map;
  }, [sections]);

  const orderedBlocks = useMemo(
    () => [...blocks].sort((a, b) => a.order - b.order),
    [blocks],
  );
  // A block only renders when BOTH the canvas layout marks it visible AND its
  // backing section is visible (the section editor's own show/hide toggle
  // must still take effect on the canvas).
  const visibleBlocks = useMemo(
    () =>
      orderedBlocks.filter((b) => {
        if (!b.visible) return false;
        const section = b.section_id ? sectionById.get(b.section_id) : null;
        return section ? section.is_visible : true;
      }),
    [orderedBlocks, sectionById],
  );

  // ---- Drag-to-reorder (pointer), arm-then-drag like the section list. ----
  const [armedId, setArmedId] = useState<string | null>(null);
  const [dragId, setDragId] = useState<string | null>(null);
  const [overId, setOverId] = useState<string | null>(null);

  // ---- Responsive scale so the fixed-width A4 page fits smaller viewports. ----
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  useLayoutEffect(() => {
    const el = wrapperRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width ?? CANVAS_WIDTH_PX;
      setScale(Math.min(1, width / CANVAS_WIDTH_PX));
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // ---- Layout-measured page-break detection (real rendered heights). ----
  const blockRefs = useRef<Map<string, HTMLElement>>(new Map());
  const [overflowingIds, setOverflowingIds] = useState<Set<string>>(new Set());

  const recomputeOverflow = useCallback(() => {
    const heights = visibleBlocks.map((b) => blockRefs.current.get(b.id)?.offsetHeight ?? 0);
    const gap = 16; // matches the `space-y-4` gap between blocks
    const withGaps = heights.map((h, i) => (i === 0 ? h : h + gap));
    const contentHeight = CANVAS_PAGE_HEIGHT_PX * (1 - 2 * CANVAS_PADDING_FRACTION);
    const overflowIndices = computeOverflowingIndices(withGaps, contentHeight);
    const ids = new Set<string>();
    overflowIndices.forEach((i) => {
      const id = visibleBlocks[i]?.id;
      if (id) ids.add(id);
    });
    setOverflowingIds(ids);
  }, [visibleBlocks]);

  useEffect(() => {
    if (typeof ResizeObserver === "undefined") {
      recomputeOverflow();
      return;
    }
    const observer = new ResizeObserver(() => recomputeOverflow());
    blockRefs.current.forEach((el) => observer.observe(el));
    recomputeOverflow();
    return () => observer.disconnect();
    // Re-run whenever the visible block set or its content changes.
  }, [visibleBlocks, sections, recomputeOverflow]);

  const overflowing = overflowingIds.size > 0;

  // ---- Keyboard block navigation (Tab reaches each block; arrows move focus). ----
  function focusBlock(id: string) {
    blockRefs.current.get(id)?.focus();
  }
  function handleBlockKeyDown(e: React.KeyboardEvent, blockId: string) {
    const idx = visibleBlocks.findIndex((b) => b.id === blockId);
    if (e.key === "ArrowDown" && idx < visibleBlocks.length - 1) {
      e.preventDefault();
      const next = visibleBlocks[idx + 1]!;
      onSelectBlock(next.id);
      focusBlock(next.id);
    } else if (e.key === "ArrowUp" && idx > 0) {
      e.preventDefault();
      const prev = visibleBlocks[idx - 1]!;
      onSelectBlock(prev.id);
      focusBlock(prev.id);
    } else if (
      (e.key === "ArrowDown" || e.key === "ArrowUp") &&
      (e.metaKey || e.ctrlKey)
    ) {
      e.preventDefault();
      onShiftBlock(blockId, e.key === "ArrowDown" ? "down" : "up");
    } else if (e.key === "Enter" || e.key === " ") {
      if (document.activeElement === blockRefs.current.get(blockId)) {
        e.preventDefault();
        onSelectBlock(blockId);
      }
    }
  }

  const pageHeightCss = `${CANVAS_PAGE_HEIGHT_PX}px`;

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      {overflowing && (
        <p
          role="status"
          className="flex items-center gap-2 rounded-lg bg-[var(--amber-100)] px-3 py-2 text-xs font-medium text-[var(--amber-700)]"
        >
          <Warning aria-hidden weight="fill" className="size-4 shrink-0" />
          {t("preview.pageBreakWarning")}
        </p>
      )}

      <div
        ref={wrapperRef}
        className="mx-auto w-full max-w-[794px] overflow-x-auto"
        style={{ height: scale < 1 ? CANVAS_PAGE_HEIGHT_PX * scale : undefined }}
      >
        <div
          aria-label={t("preview.a4Label")}
          style={{
            width: CANVAS_WIDTH_PX,
            minHeight: pageHeightCss,
            transform: `scale(${scale})`,
            transformOrigin: "top left",
          }}
          className="overflow-hidden rounded-lg border border-white/60 bg-white text-[#1a1a1a] shadow-[0_4px_24px_rgba(11,34,57,0.10)]"
        >
          <div className="p-[6%]">
            <div className="flex items-start gap-4">
              {photo?.url ? (
                  <button
                    type="button"
                    onClick={onEditPhoto}
                    className={cn(
                      "size-16 shrink-0 overflow-hidden border border-gray-200 bg-gray-100 outline-none ring-offset-2 focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]",
                      photo.shape === "circle"
                        ? "rounded-full"
                        : photo.shape === "rounded"
                          ? "rounded-xl"
                          : "rounded-none",
                    )}
                    aria-label={t("canvas.editPhoto")}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={photo.url} alt="" className="size-full object-cover" />
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={onEditPhoto}
                    className="flex size-16 shrink-0 flex-col items-center justify-center gap-1 rounded-xl border border-dashed border-gray-300 text-gray-400 outline-none transition hover:border-[var(--brand-primary)]/50 hover:text-[var(--brand-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
                    aria-label={t("canvas.addPhoto")}
                  >
                    <ImageSquare aria-hidden weight="duotone" className="size-5" />
                    <span className="text-[9px] font-semibold uppercase tracking-wide">
                      {t("canvas.photo")}
                    </span>
                  </button>
                )}
                <div className="min-w-0 flex-1">
                  <h2 className="text-[1.6rem] font-bold leading-tight text-[#111]">
                    {title || t("preview.untitled")}
                  </h2>
                  <div className="mt-1 h-0.5 w-16 bg-[var(--brand-primary)]" />
                </div>
              </div>

              {visibleBlocks.length === 0 ? (
                <p className="mt-6 text-sm italic text-gray-400">{t("preview.empty")}</p>
              ) : (
                <div className="mt-5 space-y-4">
                  {visibleBlocks.map((block) => {
                    const section = block.section_id ? sectionById.get(block.section_id) : null;
                    if (!section) return null;
                    const isSelected = selectedBlockId === block.id;
                    const isOverflowing = overflowingIds.has(block.id);
                    return (
                      <CanvasBlockView
                        key={block.id}
                        block={block}
                        section={section}
                        selected={isSelected}
                        overflowing={isOverflowing}
                        dragActive={dragId !== null}
                        isDragging={dragId === block.id}
                        isDropTarget={overId === block.id}
                        isArmed={armedId === block.id}
                        setRef={(el) => {
                          if (el) blockRefs.current.set(block.id, el);
                          else blockRefs.current.delete(block.id);
                        }}
                        onSelect={() => onSelectBlock(block.id)}
                        onKeyDown={(e) => handleBlockKeyDown(e, block.id)}
                        onArmDrag={() => setArmedId(block.id)}
                        onDragStart={() => setDragId(block.id)}
                        onDragOverBlock={() => setOverId(block.id)}
                        onDropOnBlock={() => {
                          onMoveBlock(dragId ?? "", block.id);
                          setDragId(null);
                          setOverId(null);
                          setArmedId(null);
                        }}
                        onDragEnd={() => {
                          setDragId(null);
                          setOverId(null);
                          setArmedId(null);
                        }}
                        onTextChange={(content) => onSectionTextChange(section.id, content)}
                        onTextFlush={() => onSectionTextFlush(section.id)}
                        onHideBlock={() => onToggleBlockVisible(block.id, false)}
                      />
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
  );
}

/**
 * Uncontrolled contentEditable text node that only re-syncs its DOM content
 * from `value` when the element is not focused (initial mount + external
 * updates such as undo/redo or a conflict reload). This avoids the classic
 * React-controlled-contentEditable bug where feeding live keystrokes back
 * through `children` resets the caret to the start on every character.
 */
function EditableText({
  value,
  onChange,
  onCommit,
  ariaLabel,
  className,
}: {
  value: string;
  onChange: (value: string) => void;
  onCommit: () => void;
  ariaLabel: string;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const mountedRef = useRef(false);

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

  return (
    <div
      ref={ref}
      role="textbox"
      aria-label={ariaLabel}
      aria-multiline="true"
      contentEditable
      suppressContentEditableWarning
      onClick={(e) => e.stopPropagation()}
      onInput={(e) => onChange(e.currentTarget.textContent ?? "")}
      onBlur={onCommit}
      className={className}
    />
  );
}

/** One selectable/editable canvas block, mapped 1:1 to a CV section. */
function CanvasBlockView({
  block,
  section,
  selected,
  overflowing,
  dragActive,
  isDragging,
  isDropTarget,
  isArmed,
  setRef,
  onSelect,
  onKeyDown,
  onArmDrag,
  onDragStart,
  onDragOverBlock,
  onDropOnBlock,
  onDragEnd,
  onTextChange,
  onTextFlush,
  onHideBlock,
}: {
  block: CvCanvasBlock;
  section: CvSection;
  selected: boolean;
  overflowing: boolean;
  dragActive: boolean;
  isDragging: boolean;
  isDropTarget: boolean;
  isArmed: boolean;
  setRef: (el: HTMLElement | null) => void;
  onSelect: () => void;
  onKeyDown: (e: React.KeyboardEvent) => void;
  onArmDrag: () => void;
  onDragStart: () => void;
  onDragOverBlock: () => void;
  onDropOnBlock: () => void;
  onDragEnd: () => void;
  onTextChange: (content: CvSectionContent) => void;
  onTextFlush: () => void;
  onHideBlock: () => void;
}) {
  const t = useTranslations("cv");
  const mode = sectionMode(section);
  const items = sectionItems(section.content);
  const style = block.style ?? {};
  const alignClass = style.align ? STYLE_TO_CLASS[style.align] : undefined;
  const sizeClass = style.fontSize ? STYLE_TO_CLASS[style.fontSize] : undefined;
  const boldClass = style.emphasis === "bold" ? "font-semibold" : undefined;

  const labelKey = `sectionTypes.${sectionTypeKey(section.section_type)}`;
  const label = t.has(labelKey) ? t(labelKey) : section.title;

  function setItem(i: number, value: string) {
    const next = [...items];
    next[i] = value;
    onTextChange(buildListContent(next));
  }
  function addItem() {
    onTextChange(buildListContent([...items, ""]));
    onTextFlush();
  }
  function removeItem(i: number) {
    onTextChange(buildListContent(items.filter((_, idx) => idx !== i)));
    onTextFlush();
  }

  return (
    <section
      ref={setRef as React.Ref<HTMLElement>}
      role="button"
      tabIndex={0}
      aria-label={t("canvas.blockAriaLabel", { name: label })}
      aria-pressed={selected}
      onClick={onSelect}
      onFocus={onSelect}
      onKeyDown={onKeyDown}
      draggable={isArmed}
      onDragStart={(e) => {
        if (!isArmed) {
          e.preventDefault();
          return;
        }
        onDragStart();
        e.dataTransfer.effectAllowed = "move";
      }}
      onDragOver={(e) => {
        if (dragActive && !isDragging) {
          e.preventDefault();
          onDragOverBlock();
        }
      }}
      onDrop={(e) => {
        e.preventDefault();
        onDropOnBlock();
      }}
      onDragEnd={onDragEnd}
      className={cn(
        "group relative -mx-2 rounded-md px-2 py-1 outline-none transition-shadow",
        selected && "ring-2 ring-[var(--brand-primary)]/50",
        isDropTarget && !isDragging && "ring-2 ring-[var(--brand-primary)]/30",
        isDragging && "opacity-50",
        overflowing && "outline outline-1 outline-dashed outline-[var(--amber-600)]/60",
      )}
    >
      {selected && (
        <div className="absolute -left-1 -top-1 flex -translate-y-full items-center gap-1 rounded-md bg-[var(--brand-primary)] px-1.5 py-0.5 text-[10px] font-semibold text-white shadow-sm">
          <button
            type="button"
            aria-label={t("editor.dragHandle", { name: label })}
            onPointerDown={(e) => {
              e.stopPropagation();
              onArmDrag();
            }}
            className="cursor-grab touch-none rounded p-0.5 hover:bg-white/20 active:cursor-grabbing"
          >
            <DotsSixVertical aria-hidden weight="bold" className="size-3" />
          </button>
          {label}
          <button
            type="button"
            aria-label={t("editor.hide")}
            onClick={(e) => {
              e.stopPropagation();
              onHideBlock();
            }}
            className="rounded p-0.5 hover:bg-white/20"
          >
            <Trash aria-hidden weight="bold" className="size-3" />
          </button>
        </div>
      )}

      <h3 className="text-[0.7rem] font-bold uppercase tracking-[0.12em] text-[var(--brand-primary)]">
        {label}
      </h3>
      <div className="mt-1 border-t border-gray-200 pt-1.5">
        {mode === "text" ? (
          <EditableText
            value={sectionText(section.content)}
            onChange={(text) => onTextChange(buildTextContent(text))}
            onCommit={onTextFlush}
            ariaLabel={label}
            className={cn(
              "whitespace-pre-wrap text-[0.78rem] leading-relaxed text-gray-700 outline-none focus-visible:bg-[var(--brand-primary)]/5",
              alignClass,
              sizeClass,
              boldClass,
            )}
          />
        ) : items.filter((x) => x.trim()).length === 0 && !selected ? (
          <p className="text-xs italic text-gray-300">{t("preview.sectionEmpty")}</p>
        ) : (
          <ul className={cn("list-disc space-y-1 pl-4 text-[0.78rem] leading-relaxed text-gray-700", alignClass, sizeClass, boldClass)}>
            {items.map((value, i) => (
              <li key={i} className="group/item relative">
                <EditableText
                  value={value}
                  onChange={(text) => setItem(i, text)}
                  onCommit={onTextFlush}
                  ariaLabel={`${label} ${i + 1}`}
                  className="inline-block min-w-[2ch] outline-none focus-visible:bg-[var(--brand-primary)]/5"
                />
                {selected && (
                  <button
                    type="button"
                    aria-label={t("editor.removeItem")}
                    onClick={(e) => {
                      e.stopPropagation();
                      removeItem(i);
                    }}
                    className="ml-1.5 rounded p-0.5 text-gray-300 opacity-0 outline-none hover:bg-red-50 hover:text-red-500 group-hover/item:opacity-100 focus-visible:opacity-100"
                  >
                    <Trash aria-hidden weight="bold" className="size-3" />
                  </button>
                )}
              </li>
            ))}
            {selected && (
              <li className="list-none">
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    addItem();
                  }}
                  className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[0.7rem] font-medium text-[var(--brand-primary)] outline-none hover:bg-[var(--brand-primary)]/8"
                >
                  <Plus aria-hidden weight="bold" className="size-3" />
                  {t("editor.addItem")}
                </button>
              </li>
            )}
          </ul>
        )}
      </div>
    </section>
  );
}
