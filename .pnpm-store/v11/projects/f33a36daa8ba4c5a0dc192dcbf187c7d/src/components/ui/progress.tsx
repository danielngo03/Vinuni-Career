"use client";

import * as ProgressPrimitive from "@radix-ui/react-progress";
import { cn } from "@/lib/utils";

export function Progress({
  value,
  className,
  indicatorClassName,
}: {
  value: number;
  className?: string;
  indicatorClassName?: string;
}) {
  return (
    <ProgressPrimitive.Root
      className={cn("h-2 overflow-hidden rounded-full bg-slate-100", className)}
      value={value}
    >
      <ProgressPrimitive.Indicator
        className={cn(
          "h-full rounded-full bg-primary transition-transform duration-500",
          indicatorClassName,
        )}
        style={{ transform: `translateX(-${100 - Math.min(100, value)}%)` }}
      />
    </ProgressPrimitive.Root>
  );
}
