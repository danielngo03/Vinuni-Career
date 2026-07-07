"use client";

import { useCallback, useMemo, useState } from "react";

export interface RowSelection<Id extends string = string> {
  /** Currently selected ids. */
  ids: Id[];
  count: number;
  isSelected: (id: Id) => boolean;
  toggle: (id: Id) => void;
  clear: () => void;
  /** Add or remove a whole page of ids (header select-all). */
  setMany: (ids: Id[], selected: boolean) => void;
  /** True when every id in `ids` is selected (and there is at least one). */
  allSelected: (ids: Id[]) => boolean;
  /** True when some—but not all—of `ids` are selected (indeterminate). */
  someSelected: (ids: Id[]) => boolean;
}

/**
 * Framework-agnostic multi-row selection state for tables/lists. Pairs with
 * `Checkbox` (indeterminate) and `BulkActionBar`. Selection survives filtering
 * (ids not on the current page stay selected); callers clear() after a bulk
 * mutation. Generalizes the ad-hoc selection state in pipeline/moderation.
 */
export function useRowSelection<Id extends string = string>(): RowSelection<Id> {
  const [selected, setSelected] = useState<ReadonlySet<Id>>(() => new Set<Id>());

  const toggle = useCallback((id: Id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const setMany = useCallback((ids: Id[], on: boolean) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (on) ids.forEach((id) => next.add(id));
      else ids.forEach((id) => next.delete(id));
      return next;
    });
  }, []);

  const clear = useCallback(() => setSelected(new Set<Id>()), []);

  const isSelected = useCallback((id: Id) => selected.has(id), [selected]);
  const allSelected = useCallback(
    (ids: Id[]) => ids.length > 0 && ids.every((id) => selected.has(id)),
    [selected],
  );
  const someSelected = useCallback(
    (ids: Id[]) => {
      const anySel = ids.some((id) => selected.has(id));
      return anySel && !ids.every((id) => selected.has(id));
    },
    [selected],
  );

  const ids = useMemo(() => Array.from(selected), [selected]);

  return { ids, count: ids.length, isSelected, toggle, clear, setMany, allSelected, someSelected };
}
