"use client";

import { SessionList, type SessionListProps } from "./session-list";

/**
 * Persistent conversation-history rail shown on the expanded desktop layout
 * (>= lg). On smaller/collapsed layouts the same {@link SessionList} is surfaced
 * through the in-panel history overlay instead.
 */
export function SessionRail(props: SessionListProps) {
  return (
    <aside className="hidden min-h-0 border-r border-[var(--glass-border)] bg-[var(--glass-surface-light)] p-3 lg:flex lg:flex-col">
      <SessionList {...props} />
    </aside>
  );
}
