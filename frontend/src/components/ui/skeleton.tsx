import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      aria-hidden
      className={cn(
        "animate-pulse rounded-lg bg-[linear-gradient(90deg,#edf2f8_25%,#f8fafc_50%,#edf2f8_75%)] bg-[length:200%_100%]",
        className,
      )}
    />
  );
}

export function PanelSkeleton() {
  return (
    <div className="rounded-2xl border bg-white p-5">
      <Skeleton className="h-5 w-40" />
      <Skeleton className="mt-3 h-4 w-64 max-w-full" />
      <div className="mt-6 space-y-3">
        {Array.from({ length: 4 }, (_, index) => (
          <Skeleton key={index} className="h-16 w-full" />
        ))}
      </div>
    </div>
  );
}
