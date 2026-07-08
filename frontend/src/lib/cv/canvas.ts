/**
 * Pure helpers for the CV Studio canvas editor (`docs/CV_STUDIO_SPEC.md`).
 *
 * The canvas is presentation-only layout metadata (`PATCH /cvs/{id}/canvas`):
 * block order, visibility, and style. CV facts always stay in the referenced
 * section's `content` (edited via the existing section endpoints). These
 * helpers never touch section content — only block layout.
 */

import type { CvCanvasBlock, CvCanvasBlockStyle, CvSection } from "@/lib/api";

/** Deterministic block id for a section-backed block (stable across reloads). */
export function blockIdForSection(sectionId: string): string {
  return `block-section-${sectionId}`;
}

/**
 * Build a default one-block-per-section canvas layout when the CV has no
 * saved canvas yet (fresh CVs, or CVs created before canvas existed).
 */
export function defaultBlocksFromSections(sections: CvSection[]): CvCanvasBlock[] {
  return [...sections]
    .sort((a, b) => a.sort_order - b.sort_order)
    .map((s, i) => ({
      id: blockIdForSection(s.id),
      type: "section",
      section_id: s.id,
      order: i,
      visible: s.is_visible,
      style: null,
    }));
}

/**
 * Reconcile saved canvas blocks with the CV's live sections: keep a block for
 * every current section (new sections are appended, blocks whose section was
 * deleted are dropped), sorted and renumbered by `order`. Non-section block
 * types (e.g. `photo`) are preserved and sorted alongside section blocks.
 */
export function reconcileBlocks(
  blocks: CvCanvasBlock[] | undefined,
  sections: CvSection[],
): CvCanvasBlock[] {
  const sectionIds = new Set(sections.map((s) => s.id));
  const bySection = new Map<string, CvCanvasBlock>();
  const other: CvCanvasBlock[] = [];
  for (const b of blocks ?? []) {
    if (b.type === "section" && b.section_id) {
      if (sectionIds.has(b.section_id)) bySection.set(b.section_id, b);
    } else {
      other.push(b);
    }
  }
  const known = [...bySection.values()];
  const missing = sections
    .filter((s) => !bySection.has(s.id))
    .sort((a, b) => a.sort_order - b.sort_order)
    .map((s) => ({
      id: blockIdForSection(s.id),
      type: "section",
      section_id: s.id,
      order: 0,
      visible: s.is_visible,
      style: null,
    }));
  const merged = [...other, ...known, ...missing].sort((a, b) => a.order - b.order);
  return merged.map((b, i) => ({ ...b, order: i }));
}

/** Move `fromId` to the position of `toId`, renumbering `order` densely. */
export function moveBlock(
  blocks: CvCanvasBlock[],
  fromId: string,
  toId: string,
): CvCanvasBlock[] {
  const fromIdx = blocks.findIndex((b) => b.id === fromId);
  const toIdx = blocks.findIndex((b) => b.id === toId);
  if (fromIdx < 0 || toIdx < 0 || fromIdx === toIdx) return blocks;
  const next = [...blocks];
  const [moved] = next.splice(fromIdx, 1);
  next.splice(toIdx, 0, moved!);
  return next.map((b, i) => ({ ...b, order: i }));
}

/** Move a block up/down by one position (keyboard reorder path). */
export function shiftBlock(
  blocks: CvCanvasBlock[],
  blockId: string,
  direction: "up" | "down",
): CvCanvasBlock[] {
  const idx = blocks.findIndex((b) => b.id === blockId);
  const j = direction === "up" ? idx - 1 : idx + 1;
  if (idx < 0 || j < 0 || j >= blocks.length) return blocks;
  const next = [...blocks];
  [next[idx], next[j]] = [next[j]!, next[idx]!];
  return next.map((b, i) => ({ ...b, order: i }));
}

export function toggleBlockVisible(
  blocks: CvCanvasBlock[],
  blockId: string,
  visible: boolean,
): CvCanvasBlock[] {
  return blocks.map((b) => (b.id === blockId ? { ...b, visible } : b));
}

export function setBlockStyle(
  blocks: CvCanvasBlock[],
  blockId: string,
  style: CvCanvasBlockStyle,
): CvCanvasBlock[] {
  return blocks.map((b) =>
    b.id === blockId ? { ...b, style: { ...(b.style ?? {}), ...style } } : b,
  );
}

/** True when two block layouts are equal in order/visibility/style (ignores object identity). */
export function blocksEqual(a: CvCanvasBlock[], b: CvCanvasBlock[]): boolean {
  if (a.length !== b.length) return false;
  return a.every((block, i) => {
    const other = b[i];
    return (
      !!other &&
      block.id === other.id &&
      block.type === other.type &&
      block.section_id === other.section_id &&
      block.order === other.order &&
      block.visible === other.visible &&
      JSON.stringify(block.style ?? null) === JSON.stringify(other.style ?? null)
    );
  });
}

/** A4 page geometry at the editor's fixed render width (96dpi CSS px, 210x297mm). */
export const CANVAS_WIDTH_PX = 794;
export const CANVAS_PAGE_HEIGHT_PX = 1123;
/** Fraction of page height on each side reserved as margin (matches the render padding). */
export const CANVAS_PADDING_FRACTION = 0.06;

/**
 * Given cumulative block heights (px, in render order) measured inside the
 * page's content box, return the set of block indices that would spill past
 * the first A4 page — a real layout measurement, not a line-count heuristic.
 */
export function computeOverflowingIndices(
  blockHeightsPx: number[],
  pageContentHeightPx: number,
): Set<number> {
  const overflowing = new Set<number>();
  let cumulative = 0;
  for (let i = 0; i < blockHeightsPx.length; i += 1) {
    cumulative += blockHeightsPx[i]!;
    if (cumulative > pageContentHeightPx) overflowing.add(i);
  }
  return overflowing;
}
