import { describe, expect, it } from "vitest";
import {
  blockIdForSection,
  blocksEqual,
  computeOverflowingIndices,
  defaultBlocksFromSections,
  moveBlock,
  reconcileBlocks,
  setBlockStyle,
  shiftBlock,
  toggleBlockVisible,
} from "../canvas";
import type { CvCanvasBlock, CvSection } from "@/lib/api";

function section(id: string, sortOrder: number, visible = true): CvSection {
  return {
    id,
    section_type: "custom",
    title: `Section ${id}`,
    sort_order: sortOrder,
    content: { items: [] },
    is_visible: visible,
  };
}

describe("defaultBlocksFromSections", () => {
  it("creates one ordered block per section, sorted by sort_order", () => {
    const sections = [section("b", 1), section("a", 0)];
    const blocks = defaultBlocksFromSections(sections);
    expect(blocks.map((b) => b.section_id)).toEqual(["a", "b"]);
    expect(blocks.map((b) => b.order)).toEqual([0, 1]);
    expect(blocks.every((b) => b.type === "section")).toBe(true);
    expect(blocks[0]!.id).toBe(blockIdForSection("a"));
  });
});

describe("reconcileBlocks", () => {
  it("keeps saved order, drops blocks for deleted sections", () => {
    const saved: CvCanvasBlock[] = [
      { id: blockIdForSection("a"), type: "section", section_id: "a", order: 0, visible: true },
      { id: blockIdForSection("b"), type: "section", section_id: "b", order: 1, visible: true },
    ];
    const sections = [section("a", 0)]; // "b" was deleted
    const result = reconcileBlocks(saved, sections);
    expect(result).toHaveLength(1);
    expect(result[0]!.section_id).toBe("a");
    expect(result[0]!.order).toBe(0);
  });

  it("appends newly added sections at the end", () => {
    const saved: CvCanvasBlock[] = [
      { id: blockIdForSection("a"), type: "section", section_id: "a", order: 0, visible: true },
    ];
    const sections = [section("a", 0), section("c", 1)];
    const result = reconcileBlocks(saved, sections);
    expect(result.map((b) => b.section_id)).toEqual(["a", "c"]);
    expect(result.map((b) => b.order)).toEqual([0, 1]);
  });

  it("synthesizes a default layout when no canvas was ever saved", () => {
    const sections = [section("a", 0), section("b", 1)];
    const result = reconcileBlocks(undefined, sections);
    expect(result.map((b) => b.section_id)).toEqual(["a", "b"]);
  });
});

describe("moveBlock / shiftBlock", () => {
  const blocks: CvCanvasBlock[] = [
    { id: "x", type: "section", section_id: "x", order: 0, visible: true },
    { id: "y", type: "section", section_id: "y", order: 1, visible: true },
    { id: "z", type: "section", section_id: "z", order: 2, visible: true },
  ];

  it("moves a block to another block's position and renumbers order", () => {
    const result = moveBlock(blocks, "x", "z");
    expect(result.map((b) => b.id)).toEqual(["y", "z", "x"]);
    expect(result.map((b) => b.order)).toEqual([0, 1, 2]);
  });

  it("is a no-op for an unknown id", () => {
    expect(moveBlock(blocks, "x", "missing")).toBe(blocks);
  });

  it("shifts a block up/down by one position", () => {
    const up = shiftBlock(blocks, "y", "up");
    expect(up.map((b) => b.id)).toEqual(["y", "x", "z"]);
    const down = shiftBlock(blocks, "y", "down");
    expect(down.map((b) => b.id)).toEqual(["x", "z", "y"]);
  });

  it("does not shift past the boundary", () => {
    expect(shiftBlock(blocks, "x", "up")).toBe(blocks);
    expect(shiftBlock(blocks, "z", "down")).toBe(blocks);
  });
});

describe("toggleBlockVisible / setBlockStyle", () => {
  const blocks: CvCanvasBlock[] = [
    { id: "x", type: "section", section_id: "x", order: 0, visible: true, style: null },
  ];

  it("toggles only the targeted block", () => {
    const result = toggleBlockVisible(blocks, "x", false);
    expect(result[0]!.visible).toBe(false);
  });

  it("merges style keys without clobbering others", () => {
    const withAlign = setBlockStyle(blocks, "x", { align: "center" });
    const withBoth = setBlockStyle(withAlign, "x", { fontSize: "lg" });
    expect(withBoth[0]!.style).toEqual({ align: "center", fontSize: "lg" });
  });
});

describe("blocksEqual", () => {
  it("is true for structurally identical arrays with different object identity", () => {
    const a: CvCanvasBlock[] = [
      { id: "x", type: "section", section_id: "x", order: 0, visible: true, style: { align: "left" } },
    ];
    const b: CvCanvasBlock[] = [
      { id: "x", type: "section", section_id: "x", order: 0, visible: true, style: { align: "left" } },
    ];
    expect(blocksEqual(a, b)).toBe(true);
  });

  it("is false when order or visibility differs", () => {
    const a: CvCanvasBlock[] = [
      { id: "x", type: "section", section_id: "x", order: 0, visible: true },
    ];
    const b: CvCanvasBlock[] = [
      { id: "x", type: "section", section_id: "x", order: 0, visible: false },
    ];
    expect(blocksEqual(a, b)).toBe(false);
  });
});

describe("computeOverflowingIndices", () => {
  it("flags blocks whose cumulative height exceeds the page content height", () => {
    const heights = [300, 300, 300, 300]; // cumulative: 300,600,900,1200
    const overflowing = computeOverflowingIndices(heights, 1000);
    expect([...overflowing]).toEqual([3]);
  });

  it("returns an empty set when content fits on one page", () => {
    const overflowing = computeOverflowingIndices([100, 100], 1000);
    expect(overflowing.size).toBe(0);
  });
});
