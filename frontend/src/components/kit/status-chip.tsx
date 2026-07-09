import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * StatusChip — soft-tinted status/category pill (v10). Two token families:
 *  - Semantic: neutral · success · warning · danger · info · ai
 *  - Categorical: the data-viz hues (indigo · teal · amber · rose · sky ·
 *    emerald · violet · orange) for non-semantic category labels.
 * Soft tint background + saturated text; optional leading dot. Use semantic
 * tones for state, categorical hues only for genuine categories.
 */
export type ChipTone =
  | "neutral"
  | "success"
  | "warning"
  | "danger"
  | "info"
  | "ai"
  | "indigo"
  | "teal"
  | "amber"
  | "rose"
  | "sky"
  | "emerald"
  | "violet"
  | "orange";

const TONE: Record<ChipTone, { bg: string; fg: string }> = {
  neutral: { bg: "var(--bg-muted)", fg: "var(--text-secondary)" },
  success: { bg: "var(--content-success-soft)", fg: "var(--content-success)" },
  warning: { bg: "var(--content-warning-soft)", fg: "var(--content-warning)" },
  danger: { bg: "var(--content-danger-soft)", fg: "var(--content-danger)" },
  info: { bg: "var(--content-info-soft)", fg: "var(--content-info)" },
  ai: { bg: "var(--content-ai-soft)", fg: "var(--content-ai)" },
  indigo: { bg: "var(--viz-indigo-soft)", fg: "var(--viz-indigo)" },
  teal: { bg: "var(--viz-teal-soft)", fg: "var(--viz-teal)" },
  amber: { bg: "var(--viz-amber-soft)", fg: "var(--viz-amber)" },
  rose: { bg: "var(--viz-rose-soft)", fg: "var(--viz-rose)" },
  sky: { bg: "var(--viz-sky-soft)", fg: "var(--viz-sky)" },
  emerald: { bg: "var(--viz-emerald-soft)", fg: "var(--viz-emerald)" },
  violet: { bg: "var(--viz-violet-soft)", fg: "var(--viz-violet)" },
  orange: { bg: "var(--viz-orange-soft)", fg: "var(--viz-orange)" },
};

export interface StatusChipProps extends React.ComponentProps<"span"> {
  tone?: ChipTone;
  /** Show a leading colored dot. */
  dot?: boolean;
  size?: "sm" | "md";
}

export function StatusChip({
  tone = "neutral",
  dot = false,
  size = "md",
  className,
  children,
  ...props
}: StatusChipProps) {
  const t = TONE[tone];
  return (
    <span
      className={cn(
        "inline-flex w-fit shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full font-medium",
        size === "sm" ? "px-2 py-0.5 text-[0.6875rem]" : "px-2.5 py-0.5 text-xs",
        className,
      )}
      style={{ background: t.bg, color: t.fg }}
      {...props}
    >
      {dot && (
        <span aria-hidden className="size-1.5 shrink-0 rounded-full" style={{ background: t.fg }} />
      )}
      {children}
    </span>
  );
}

/** Bare colored dot for use in lists/legends. */
export function ToneDot({
  tone = "neutral",
  className,
}: {
  tone?: ChipTone;
  className?: string;
}) {
  return (
    <span
      aria-hidden
      className={cn("inline-block size-2 shrink-0 rounded-full", className)}
      style={{ background: TONE[tone].fg }}
    />
  );
}
