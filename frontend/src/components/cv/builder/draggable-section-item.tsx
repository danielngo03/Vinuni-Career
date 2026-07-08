"use client";

import { cn } from "@/lib/utils";
import type { CvSection, CvSectionContent } from "@/lib/api";
import { CvSectionEditor } from "../cv-section-editor";

/**
 * One reorderable section row in the builder's editor column. Drag state
 * (`armedId`/`dragId`/`overId`) lives in the parent screen; this component is
 * a thin, controlled wrapper around the drag events + `CvSectionEditor`.
 */
export function DraggableSectionItem({
  section,
  index,
  total,
  dragActive,
  isDragging,
  isDropTarget,
  isArmed,
  onArmDrag,
  onDragStart,
  onDragOverSection,
  onDropOnSection,
  onDragEnd,
  onContentChange,
  onFlush,
  onToggleVisible,
  onMove,
}: {
  section: CvSection;
  index: number;
  total: number;
  /** True while ANY section in the list is being dragged (including this one). */
  dragActive: boolean;
  /** True while THIS section is the one being dragged. */
  isDragging: boolean;
  isDropTarget: boolean;
  isArmed: boolean;
  onArmDrag: () => void;
  onDragStart: () => void;
  onDragOverSection: () => void;
  onDropOnSection: () => void;
  onDragEnd: () => void;
  onContentChange: (content: CvSectionContent) => void;
  onFlush: () => void;
  onToggleVisible: (visible: boolean) => void;
  onMove: (direction: "up" | "down") => void;
}) {
  return (
    <div
      id={`cv-sec-${section.id}`}
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
          onDragOverSection();
        }
      }}
      onDrop={(e) => {
        e.preventDefault();
        onDropOnSection();
      }}
      onDragEnd={onDragEnd}
      className={cn(
        "scroll-mt-24 rounded-2xl transition-shadow",
        isDragging && "opacity-50",
        isDropTarget && !isDragging && "ring-2 ring-[var(--brand-primary)]/50",
      )}
    >
      <CvSectionEditor
        section={section}
        index={index}
        total={total}
        onContentChange={onContentChange}
        onFlush={onFlush}
        onToggleVisible={onToggleVisible}
        onMove={onMove}
        onArmDrag={onArmDrag}
      />
    </div>
  );
}
