"use client";

import { useCallback, useRef, useState } from "react";

/**
 * Generic client-side undo/redo snapshot stack (`docs/CV_STUDIO_SPEC.md` —
 * canvas editor undo/redo). Scoped to whatever `T` the caller passes (canvas
 * blocks, selected photo state, etc.) for a single editing session; it never
 * persists across reloads.
 */
export interface UseHistoryResult<T> {
  value: T;
  canUndo: boolean;
  canRedo: boolean;
  /** Apply a new value and push the previous one onto the undo stack. */
  push: (next: T) => void;
  /** Replace the current value WITHOUT creating a history entry (server hydration). */
  replace: (next: T) => void;
  undo: () => void;
  redo: () => void;
  /** Reset history (optionally to a new value) — e.g. after switching documents. */
  clear: (next?: T) => void;
}

export function useHistory<T>(initial: T, limit = 100): UseHistoryResult<T> {
  const [value, setValue] = useState<T>(initial);
  const pastRef = useRef<T[]>([]);
  const futureRef = useRef<T[]>([]);
  // Forces a re-render when only the ref-backed canUndo/canRedo flags change.
  const [, bumpState] = useState(0);
  const bump = useCallback(() => bumpState((n) => n + 1), []);

  const push = useCallback(
    (next: T) => {
      setValue((prev) => {
        pastRef.current = [...pastRef.current.slice(-(limit - 1)), prev];
        futureRef.current = [];
        return next;
      });
      bump();
    },
    [limit, bump],
  );

  const replace = useCallback((next: T) => {
    setValue(next);
  }, []);

  const undo = useCallback(() => {
    setValue((current) => {
      const past = pastRef.current;
      if (past.length === 0) return current;
      const prev = past[past.length - 1]!;
      pastRef.current = past.slice(0, -1);
      futureRef.current = [current, ...futureRef.current];
      return prev;
    });
    bump();
  }, [bump]);

  const redo = useCallback(() => {
    setValue((current) => {
      const future = futureRef.current;
      if (future.length === 0) return current;
      const next = future[0]!;
      futureRef.current = future.slice(1);
      pastRef.current = [...pastRef.current, current];
      return next;
    });
    bump();
  }, [bump]);

  const clear = useCallback(
    (next?: T) => {
      pastRef.current = [];
      futureRef.current = [];
      if (next !== undefined) setValue(next);
      bump();
    },
    [bump],
  );

  return {
    value,
    canUndo: pastRef.current.length > 0,
    canRedo: futureRef.current.length > 0,
    push,
    replace,
    undo,
    redo,
    clear,
  };
}
