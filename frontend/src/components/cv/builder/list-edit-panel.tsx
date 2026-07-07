"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { CaretDown, ListBullets, Plus } from "@phosphor-icons/react";
import { Button } from "@/components/ui";
import type { CvSection, CvSectionContent } from "@/lib/api";
import { DraggableSectionItem } from "./draggable-section-item";
import { cn } from "@/lib/utils";

/**
 * The list-edit fallback (design spec §6, "the old form-based section editor is
 * retired as the primary surface, kept only as a fallback for accessibility /
 * bulk edit"). Collapsed by default; when opened it renders the full keyboard-
 * accessible section form list (the same `CvSectionEditor` rows, with move /
 * hide / drag). All edits flow through the parent's autosave machinery — this
 * panel is a controlled shell.
 */
export function ListEditPanel({
  sections,
  addingSection,
  drag,
  onContentChange,
  onFlush,
  onToggleVisible,
  onMove,
  onAddSection,
}: {
  sections: CvSection[];
  addingSection: boolean;
  drag: {
    armedId: string | null;
    dragId: string | null;
    overId: string | null;
    setArmedId: (id: string | null) => void;
    setDragId: (id: string | null) => void;
    setOverId: (id: string | null) => void;
    dropOnto: (id: string) => void;
  };
  onContentChange: (sectionId: string, content: CvSectionContent) => void;
  onFlush: (sectionId: string) => void;
  onToggleVisible: (sectionId: string, visible: boolean) => void;
  onMove: (sectionId: string, direction: "up" | "down") => void;
  onAddSection: () => void;
}) {
  const t = useTranslations("cv");
  const [open, setOpen] = useState(false);

  return (
    <section className="rounded-2xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] shadow-[var(--shadow-sm)] backdrop-blur-md">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 rounded-2xl px-4 py-3 text-left outline-none transition-colors hover:bg-[var(--glass-surface-light)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
      >
        <span className="flex items-center gap-2">
          <span className="flex size-6 shrink-0 items-center justify-center rounded-lg icon-chip-neutral shadow-sm">
            <ListBullets aria-hidden weight="duotone" className="size-3.5 text-white" />
          </span>
          <span>
            <span className="block text-sm font-bold text-[var(--text-primary)]">
              {t("builder.listEditTitle")}
            </span>
            <span className="block text-xs text-[var(--text-muted)]">
              {t("builder.listEditHint")}
            </span>
          </span>
        </span>
        <CaretDown
          aria-hidden
          weight="bold"
          className={cn(
            "size-4 shrink-0 text-[var(--text-muted)] transition-transform",
            open && "rotate-180",
          )}
        />
      </button>

      {open && (
        <div className="space-y-3 border-t border-[var(--glass-border)] p-4">
          {sections.map((s, i) => (
            <DraggableSectionItem
              key={s.id}
              section={s}
              index={i}
              total={sections.length}
              dragActive={drag.dragId !== null}
              isDragging={drag.dragId === s.id}
              isDropTarget={drag.overId === s.id}
              isArmed={drag.armedId === s.id}
              onArmDrag={() => drag.setArmedId(s.id)}
              onDragStart={() => drag.setDragId(s.id)}
              onDragOverSection={() => drag.setOverId(s.id)}
              onDropOnSection={() => {
                drag.dropOnto(s.id);
                drag.setDragId(null);
                drag.setOverId(null);
                drag.setArmedId(null);
              }}
              onDragEnd={() => {
                drag.setDragId(null);
                drag.setOverId(null);
                drag.setArmedId(null);
              }}
              onContentChange={(content) => onContentChange(s.id, content)}
              onFlush={() => onFlush(s.id)}
              onToggleVisible={(v) => onToggleVisible(s.id, v)}
              onMove={(dir) => onMove(s.id, dir)}
            />
          ))}
          <Button
            variant="secondary"
            fullWidth
            loading={addingSection}
            onClick={onAddSection}
          >
            <Plus aria-hidden weight="bold" className="size-4" />
            {t("builder.addSection")}
          </Button>
        </div>
      )}
    </section>
  );
}
