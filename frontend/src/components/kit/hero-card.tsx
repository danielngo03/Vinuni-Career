import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * GradientHeroCard — the ONE restrained indigo→violet gradient tile per surface
 * (v10 rule). Reserved for a top forecast / weighted-pipeline / headline summary
 * (à la Pipeline-OS). Do NOT use more than one per screen and never as a page
 * background. White foreground; content stays legible on the gradient.
 */
export function GradientHeroCard({
  eyebrow,
  title,
  value,
  caption,
  icon: Icon,
  footer,
  aside,
  className,
}: {
  /** Small-caps eyebrow label. */
  eyebrow?: string;
  /** Headline (e.g. "Weighted pipeline forecast"). */
  title: string;
  /** Big hero metric. */
  value: string;
  /** Supporting line under the metric. */
  caption?: string;
  icon?: React.ElementType;
  /** Optional footer row (chips, secondary stats). */
  footer?: React.ReactNode;
  /** Optional right-side slot (mini chart / breakdown). */
  aside?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-xl p-5 text-white shadow-[var(--shadow-md)]",
        className,
      )}
      style={{ background: "var(--hero-gradient)" }}
    >
      {/* subtle sheen */}
      <div
        aria-hidden
        className="pointer-events-none absolute -right-16 -top-16 size-52 rounded-full opacity-25"
        style={{ background: "radial-gradient(circle, rgba(255,255,255,0.5), transparent 70%)" }}
      />
      <div className="relative flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            {Icon && (
              <span className="flex size-8 items-center justify-center rounded-lg bg-white/15 backdrop-blur-sm">
                <Icon aria-hidden className="size-4 text-white" strokeWidth={1.9} />
              </span>
            )}
            {eyebrow && (
              <span className="text-[0.6875rem] font-semibold uppercase tracking-[0.1em] text-white/70">
                {eyebrow}
              </span>
            )}
          </div>
          <p className="mt-3 text-sm font-medium text-white/85">{title}</p>
          <p className="type-display mt-1 tabular-nums text-white">{value}</p>
          {caption && <p className="mt-1 max-w-md text-sm text-white/75">{caption}</p>}
        </div>
        {aside && <div className="shrink-0">{aside}</div>}
      </div>
      {footer && (
        <div className="relative mt-4 flex flex-wrap items-center gap-2 border-t border-white/15 pt-3">
          {footer}
        </div>
      )}
    </div>
  );
}
