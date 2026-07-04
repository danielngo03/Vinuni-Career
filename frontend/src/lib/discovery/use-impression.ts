"use client";

import { useEffect, useRef } from "react";
import type { DiscoveryEventInput } from "@/lib/api";
import { recordDiscoveryEvent } from "./analytics";

/**
 * Fire a single `impression` event the first time the referenced element is
 * meaningfully visible (>= 40% in view), using IntersectionObserver so we never
 * record on every scroll pixel. The element keeps its place in the accessibility
 * tree — the observer is purely passive and never alters focus or DOM order, so
 * screen readers are unaffected.
 *
 * Pass `null` to disable (e.g. while data is loading). The effect re-arms only
 * when the stable `idempotency_key` changes, so re-renders never re-observe.
 * When IntersectionObserver is unavailable the impression is recorded eagerly.
 */
export function useImpression<T extends HTMLElement>(
  input: DiscoveryEventInput | null,
): React.RefObject<T | null> {
  const ref = useRef<T | null>(null);
  // Hold the latest input so the effect can read it without re-subscribing on
  // every render; the effect's identity is keyed only by the idempotency key.
  const inputRef = useRef(input);
  inputRef.current = input;
  const key = input?.idempotency_key ?? null;

  useEffect(() => {
    const el = ref.current;
    const current = inputRef.current;
    if (!el || !current) return;

    if (typeof IntersectionObserver === "undefined") {
      recordDiscoveryEvent(current);
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting && entry.intersectionRatio >= 0.4) {
            const latest = inputRef.current;
            if (latest) recordDiscoveryEvent(latest);
            observer.disconnect();
            break;
          }
        }
      },
      { threshold: [0.4] },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [key]);

  return ref;
}
