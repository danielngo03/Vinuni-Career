"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Simple second-resolution countdown for resend/rate-limit cooldowns. Starts
 * counting down from a backend-provided `retry_after_seconds` value and
 * reaches 0 on its own; never re-derives or guesses a value itself.
 */
export function useCooldown() {
  const [seconds, setSeconds] = useState(0);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, []);

  function start(initialSeconds: number) {
    if (timer.current) clearInterval(timer.current);
    setSeconds(initialSeconds);
    timer.current = setInterval(() => {
      setSeconds((s) => {
        if (s <= 1) {
          if (timer.current) clearInterval(timer.current);
          return 0;
        }
        return s - 1;
      });
    }, 1000);
  }

  return { seconds, start, active: seconds > 0 };
}
