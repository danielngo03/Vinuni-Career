"use client";

import type { NodeTypeDef } from "./flow-canvas";

export function NodePalette({ defs, title }: { defs: NodeTypeDef[]; title: string }) {
  return (
    <aside className="w-48 shrink-0 space-y-2" data-testid="node-palette">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        {title}
      </h3>
      {defs.map((def) => (
        <div
          key={def.type}
          draggable
          onDragStart={(e) => e.dataTransfer.setData("application/workflow-node-type", def.type)}
          className="cursor-grab rounded-xl border border-[var(--border-subtle)] bg-white/90 px-3 py-2 text-sm font-medium shadow-sm active:cursor-grabbing"
          data-testid={`palette-node-${def.type}`}
        >
          {def.label}
        </div>
      ))}
    </aside>
  );
}
