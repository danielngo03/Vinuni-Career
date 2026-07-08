import { CheckCircle, Info, WarningCircle } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";

type Tone = "error" | "success" | "info";

const TONE = {
  error: {
    icon: WarningCircle,
    box: "border-[var(--red-400)]/40 bg-[var(--red-50)] text-[var(--brand-red)]",
  },
  success: {
    icon: CheckCircle,
    box: "border-[var(--teal-500)]/40 bg-[var(--teal-50)] text-[var(--teal-600)]",
  },
  info: {
    icon: Info,
    box: "border-[var(--blue-200)] bg-[var(--blue-50)] text-[var(--brand-primary)]",
  },
} as const;

/**
 * Inline form-level feedback banner. Pairs an icon with text so color is never
 * the only signal. Errors use role=alert; others role=status.
 */
export function FormBanner({
  tone = "error",
  title,
  children,
  className,
}: {
  tone?: Tone;
  title?: string;
  children?: React.ReactNode;
  className?: string;
}) {
  const { icon: Icon, box } = TONE[tone];
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cn(
        "flex items-start gap-2.5 rounded-xl border px-3.5 py-3 text-sm",
        box,
        className,
      )}
    >
      <Icon aria-hidden weight="duotone" className="mt-0.5 size-5 shrink-0" />
      <div className="min-w-0">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className={cn(title && "mt-0.5")}>{children}</div>}
      </div>
    </div>
  );
}
