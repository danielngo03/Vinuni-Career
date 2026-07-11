"use client";

import * as React from "react";
import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  pointerWithin,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { GripVertical } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Kanban — the v10 drag-and-drop board primitive (dnd-kit). Powers the partner
 * recruiting pipeline: cards are dragged between stage columns, and each drop
 * emits a {@link KanbanMoveEvent} the caller turns into a real backend mutation
 * (advance / rollback). The board is a VISUAL enhancement over an accessible
 * button fallback — never the only way to move a card.
 *
 * Composition:
 *   <KanbanBoard onMove={…} renderOverlay={(id) => …}>
 *     <KanbanColumn id="__new__" title="New" count={3}>
 *       <KanbanCard id={appId} columnId="__new__">…</KanbanCard>
 *     </KanbanColumn>
 *   </KanbanBoard>
 *
 * Drop semantics are the CALLER's business: `onMove` reports source + target
 * column ids; the pipeline decides adjacent-forward = advance, backward =
 * rollback modal, etc. The primitive itself is domain-agnostic.
 */

export interface KanbanMoveEvent {
  cardId: string;
  fromColumnId: string;
  toColumnId: string;
}

interface KanbanContextValue {
  activeId: string | null;
  usingOverlay: boolean;
}

const KanbanContext = React.createContext<KanbanContextValue>({
  activeId: null,
  usingOverlay: false,
});

export function KanbanBoard({
  onMove,
  renderOverlay,
  ariaLabel,
  disabled = false,
  children,
  className,
}: {
  /** Fired when a card is dropped over a column different from its source. */
  onMove?: (event: KanbanMoveEvent) => void;
  /** Renders the floating drag preview for the active card id. */
  renderOverlay?: (cardId: string) => React.ReactNode;
  ariaLabel?: string;
  /** Fully disable dragging (e.g. read-only board / mutation in flight). */
  disabled?: boolean;
  children: React.ReactNode;
  className?: string;
}) {
  const [activeId, setActiveId] = React.useState<string | null>(null);
  const usingOverlay = Boolean(renderOverlay);

  const sensors = useSensors(
    // 6px activation distance so clicking a card's buttons still works.
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor),
  );

  function handleStart(event: DragStartEvent) {
    setActiveId(String(event.active.id));
  }

  function handleEnd(event: DragEndEvent) {
    setActiveId(null);
    const { active, over } = event;
    if (!over) return;
    const fromColumnId = active.data.current?.columnId as string | undefined;
    const toColumnId = String(over.id);
    const cardId = String(active.id);
    if (!fromColumnId || fromColumnId === toColumnId) return;
    onMove?.({ cardId, fromColumnId, toColumnId });
  }

  if (disabled) {
    return (
      <div
        role="list"
        aria-label={ariaLabel}
        className={cn("scrollbar-thin flex gap-4 overflow-x-auto pb-4", className)}
      >
        <KanbanContext.Provider value={{ activeId: null, usingOverlay: false }}>
          {children}
        </KanbanContext.Provider>
      </div>
    );
  }

  return (
    <KanbanContext.Provider value={{ activeId, usingOverlay }}>
      <DndContext
        sensors={sensors}
        collisionDetection={pointerWithin}
        onDragStart={handleStart}
        onDragEnd={handleEnd}
        onDragCancel={() => setActiveId(null)}
      >
        <div
          role="list"
          aria-label={ariaLabel}
          className={cn("scrollbar-thin flex gap-4 overflow-x-auto pb-4", className)}
        >
          {children}
        </div>
        {usingOverlay && (
          <DragOverlay dropAnimation={null}>
            {activeId ? (
              <div className="w-72 rotate-1 cursor-grabbing opacity-95 shadow-[var(--shadow-xl)]">
                {renderOverlay?.(activeId)}
              </div>
            ) : null}
          </DragOverlay>
        )}
      </DndContext>
    </KanbanContext.Provider>
  );
}

export function KanbanColumn({
  id,
  title,
  count,
  meta,
  aside,
  /** Filled-progress strip on the top edge (0–1); omit to hide. */
  progress,
  accent = "var(--viz-indigo)",
  empty,
  children,
  className,
}: {
  id: string;
  title: React.ReactNode;
  count?: number;
  meta?: React.ReactNode;
  aside?: React.ReactNode;
  progress?: number;
  accent?: string;
  empty?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  const { setNodeRef, isOver } = useDroppable({ id });
  const hasChildren = React.Children.count(children) > 0;

  return (
    <section
      ref={setNodeRef}
      role="listitem"
      className={cn(
        "flex w-72 shrink-0 flex-col overflow-hidden rounded-xl border bg-card transition-colors",
        isOver ? "border-[var(--field-focus-border)] ring-2 ring-[var(--field-focus-border)]/40" : "border-border",
        className,
      )}
    >
      {progress != null && (
        <span aria-hidden className="block h-0.5 w-full bg-[var(--bg-muted)]">
          <span
            className="block h-full transition-[width] duration-500"
            style={{ width: `${Math.max(0, Math.min(1, progress)) * 100}%`, background: accent }}
          />
        </span>
      )}
      <header className="flex items-start justify-between gap-2 border-b border-border px-3.5 py-3">
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-2">
            <span aria-hidden className="size-2 shrink-0 rounded-full" style={{ background: accent }} />
            <h3 className="truncate text-[0.8125rem] font-semibold text-foreground">{title}</h3>
            {count != null && (
              <span className="shrink-0 rounded-full bg-[var(--bg-muted)] px-1.5 py-0.5 text-[0.6875rem] font-semibold tabular-nums text-muted-foreground">
                {count}
              </span>
            )}
          </div>
          {meta && <div className="mt-1">{meta}</div>}
        </div>
        {aside && <div className="shrink-0">{aside}</div>}
      </header>
      <div className="flex flex-1 flex-col gap-2.5 p-2.5">
        {hasChildren ? children : empty}
      </div>
    </section>
  );
}

export function KanbanCard({
  id,
  columnId,
  disabled = false,
  selected = false,
  dragLabel,
  children,
  className,
}: {
  id: string;
  columnId: string;
  /** When true the card is not draggable (e.g. terminal / no valid move). */
  disabled?: boolean;
  selected?: boolean;
  dragLabel?: string;
  children: React.ReactNode;
  className?: string;
}) {
  const { activeId, usingOverlay } = React.useContext(KanbanContext);
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id,
    data: { columnId },
    disabled,
  });

  const isActive = activeId === id;
  // With an overlay the source card only dims; without one it translates.
  const style: React.CSSProperties =
    !usingOverlay && transform
      ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` }
      : {};
  if (usingOverlay && isActive) style.opacity = 0.4;

  return (
    <article
      ref={setNodeRef}
      style={style}
      data-selected={selected || undefined}
      className={cn(
        "relative rounded-lg border bg-card p-3 shadow-[var(--shadow-sm)] transition-colors",
        selected
          ? "border-[var(--field-focus-border)] ring-1 ring-[var(--field-focus-border)]"
          : "border-border",
        isDragging && "z-10",
        className,
      )}
    >
      <div className="flex items-start gap-1.5">
        {!disabled && (
          <button
            type="button"
            aria-label={dragLabel}
            {...attributes}
            {...listeners}
            className="mt-0.5 shrink-0 cursor-grab touch-none rounded p-0.5 text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)] active:cursor-grabbing"
          >
            <GripVertical aria-hidden className="size-4" strokeWidth={1.8} />
          </button>
        )}
        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </article>
  );
}
