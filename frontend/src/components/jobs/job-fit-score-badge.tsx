import { cn } from "@/lib/utils";

interface JobFitScoreBadgeProps {
  score: number;
  signal?: "ok" | "low_signal";
  stale?: boolean;
  size?: "sm" | "md";
  className?: string;
}

function tier(score: number) {
  if (score >= 75)
    return {
      label: "Strong",
      color:
        "text-emerald-600 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-950/30",
    };
  if (score >= 55)
    return {
      label: "Good",
      color: "text-foreground border-border bg-muted/60",
    };
  if (score >= 35)
    return {
      label: "Possible",
      color: "text-muted-foreground border-border bg-muted/30",
    };
  return {
    label: "Weak",
    color: "text-muted-foreground/60 border-border/50 bg-muted/20",
  };
}

export function JobFitScoreBadge({
  score,
  signal,
  stale,
  size = "sm",
  className,
}: JobFitScoreBadgeProps) {
  const t = tier(score);
  const isLowSignal = signal === "low_signal";

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded border font-medium tabular-nums",
        size === "sm" ? "px-1.5 py-0.5 text-[11px]" : "px-2 py-1 text-xs",
        t.color,
        stale && "opacity-60",
        className,
      )}
      title={
        isLowSignal
          ? "Low data — estimate only"
          : stale
            ? "CV may be outdated"
            : undefined
      }
    >
      <span className="font-bold">{score}</span>
      {size === "md" && (
        <span className="font-normal opacity-70">/ 100</span>
      )}
    </span>
  );
}

export function JobFitScoreSkeleton({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-block h-5 w-8 animate-pulse rounded bg-muted",
        className,
      )}
    />
  );
}
