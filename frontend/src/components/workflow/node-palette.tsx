"use client";

import { GripVertical } from "lucide-react";
import { Card, SectionLabel } from "@/components/kit";
import type { NodeTypeDef } from "./flow-canvas";
import { nodeSoft, nodeVisual } from "./node-visuals";

/**
 * Draggable node palette (v10). A mono Card of category-coded, lucide-iconed
 * rows; each row is an HTML5 drag source that hands its node type to the canvas
 * drop target. Read-only flows still show the palette (the canvas rejects
 * structural edits), so authors keep a stable reference of available steps.
 */
export function NodePalette({ defs, title }: { defs: NodeTypeDef[]; title: string }) {
  return (
    <Card className="lg:sticky lg:top-4 lg:self-start" data-testid="node-palette">
      <div className="px-4 pb-2 pt-4">
        <SectionLabel>{title}</SectionLabel>
      </div>
      <div className="space-y-1.5 px-3 pb-3">
        {defs.map((def) => {
          const { icon: Icon, accent } = nodeVisual(def.type);
          return (
            <div
              key={def.type}
              draggable
              onDragStart={(e) => e.dataTransfer.setData("application/workflow-node-type", def.type)}
              className="group flex cursor-grab items-center gap-2.5 rounded-lg border border-border bg-card px-2.5 py-2 outline-none transition-colors hover:border-border-strong hover:bg-[var(--bg-subtle)] active:cursor-grabbing"
              data-testid={`palette-node-${def.type}`}
            >
              <span
                aria-hidden
                className="flex size-7 shrink-0 items-center justify-center rounded-md"
                style={{ background: nodeSoft(accent), color: accent }}
              >
                <Icon className="size-4" strokeWidth={1.9} />
              </span>
              <span className="type-small min-w-0 flex-1 truncate font-semibold text-foreground">
                {def.label}
              </span>
              <GripVertical
                aria-hidden
                className="size-4 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100"
                strokeWidth={1.8}
              />
            </div>
          );
        })}
      </div>
    </Card>
  );
}
