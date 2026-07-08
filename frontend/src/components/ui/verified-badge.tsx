"use client";

import { SealCheck } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";

export function VerifiedBadge({
  label,
  className,
}: {
  label: string;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "group/verified relative inline-flex shrink-0 items-center align-middle",
        className,
      )}
      title={label}
    >
      <SealCheck
        aria-hidden
        weight="fill"
        className="size-4 text-[var(--brand-teal)]"
      />
      <span className="sr-only">{label}</span>
      <span
        aria-hidden
        className="pointer-events-none absolute left-full top-1/2 z-30 ml-1.5 -translate-y-1/2 whitespace-nowrap rounded-full bg-[var(--brand-teal)] px-2.5 py-1 text-[11px] font-bold text-white opacity-0 shadow-[0_8px_22px_rgba(14,156,142,0.24)] transition-opacity duration-150 group-hover/verified:opacity-100 group-focus-within/verified:opacity-100"
      >
        {label}
      </span>
    </span>
  );
}
