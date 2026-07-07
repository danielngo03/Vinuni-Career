"use client";

import { useCallback, useState } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type Provenance = "filled" | "review";

export interface FieldProvenanceProps {
  state: Provenance | null;
  label: string;
  onClear?: () => void;
}

// ---------------------------------------------------------------------------
// FieldProvenance — presentational chip
// ---------------------------------------------------------------------------

export function FieldProvenance({ state, label, onClear }: FieldProvenanceProps) {
  if (state === null) return null;

  if (state === "filled") {
    return (
      <span
        className="inline-flex items-center gap-0.5 font-mono text-[11px] rounded-full px-1.5 py-0.5 motion-safe:transition-opacity"
        style={{
          color: "var(--color-success)",
          backgroundColor: "var(--ai-accent-soft)",
        }}
      >
        {/* check glyph — inline SVG keeps the bundle clean with no icon import */}
        <svg
          width="9"
          height="9"
          viewBox="0 0 9 9"
          fill="none"
          aria-hidden="true"
          focusable="false"
        >
          <path
            d="M1.5 4.5L3.5 6.5L7.5 2.5"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        {label}
      </span>
    );
  }

  // state === "review"
  const chipClass =
    "inline-flex items-center gap-0.5 font-mono text-[11px] rounded-full px-1.5 py-0.5 motion-safe:transition-opacity";
  const chipStyle = {
    color: "var(--color-warning)",
    backgroundColor: "color-mix(in srgb, var(--color-warning) 10%, transparent)",
  };

  if (onClear) {
    return (
      <button
        type="button"
        onClick={onClear}
        aria-label={label}
        className={`${chipClass} cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-warning)] focus-visible:ring-offset-1`}
        style={chipStyle}
      >
        {/* warning triangle glyph */}
        <svg
          width="9"
          height="9"
          viewBox="0 0 9 9"
          fill="none"
          aria-hidden="true"
          focusable="false"
        >
          <path
            d="M4.5 1.5L8 7.5H1L4.5 1.5Z"
            stroke="currentColor"
            strokeWidth="1.2"
            strokeLinejoin="round"
          />
          <line
            x1="4.5"
            y1="4"
            x2="4.5"
            y2="5.5"
            stroke="currentColor"
            strokeWidth="1.2"
            strokeLinecap="round"
          />
        </svg>
        {label}
      </button>
    );
  }

  return (
    <span className={chipClass} style={chipStyle}>
      <svg
        width="9"
        height="9"
        viewBox="0 0 9 9"
        fill="none"
        aria-hidden="true"
        focusable="false"
      >
        <path
          d="M4.5 1.5L8 7.5H1L4.5 1.5Z"
          stroke="currentColor"
          strokeWidth="1.2"
          strokeLinejoin="round"
        />
        <line
          x1="4.5"
          y1="4"
          x2="4.5"
          y2="5.5"
          stroke="currentColor"
          strokeWidth="1.2"
          strokeLinecap="round"
        />
      </svg>
      {label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// useProvenance — controller hook
// ---------------------------------------------------------------------------

export function useProvenance(): {
  get: (field: string) => Provenance | null;
  setAll: (map: Record<string, Provenance>) => void;
  set: (field: string, state: Provenance) => void;
  clear: (field: string) => void;
  clearAll: () => void;
} {
  const [map, setMap] = useState<Record<string, Provenance>>({});

  const get = useCallback(
    (field: string): Provenance | null => map[field] ?? null,
    [map],
  );

  const setAll = useCallback((incoming: Record<string, Provenance>) => {
    setMap(incoming);
  }, []);

  const set = useCallback((field: string, state: Provenance) => {
    setMap((prev) => ({ ...prev, [field]: state }));
  }, []);

  const clear = useCallback((field: string) => {
    setMap((prev) => {
      if (!(field in prev)) return prev;
      const next = { ...prev };
      delete next[field];
      return next;
    });
  }, []);

  const clearAll = useCallback(() => {
    setMap({});
  }, []);

  return { get, setAll, set, clear, clearAll };
}
