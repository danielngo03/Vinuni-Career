import type { Icon } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";

/**
 * Single-level settings section container. Not nested inside another card
 * (frontend rule: no cards inside cards).
 */
export function SectionCard({
  title,
  description,
  icon: IconCmp,
  iconGradient,
  children,
  className,
}: {
  title: string;
  description?: string;
  /** Optional phosphor icon displayed in a gradient square before the title. */
  icon?: Icon;
  /** Tailwind gradient classes for the icon square, e.g. "icon-chip-info". */
  iconGradient?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "rounded-[22px] border border-[var(--border-default)] bg-white p-6 shadow-[0_8px_28px_rgba(0,0,0,0.045)]",
        className,
      )}
    >
      <div className={cn("flex items-start gap-3", description ? "mb-2" : "mb-5")}>
        {IconCmp && iconGradient && (
          <span
            className={cn(
              "flex size-8 shrink-0 items-center justify-center rounded-xl shadow-sm",
              iconGradient,
            )}
          >
            <IconCmp aria-hidden weight="duotone" className="size-4 text-white" />
          </span>
        )}
        <h2 className={cn("text-lg font-semibold text-[var(--text-primary)]", IconCmp && iconGradient && "pt-0.5")}>
          {title}
        </h2>
      </div>
      {description && (
        <p className="mb-6 max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">
          {description}
        </p>
      )}
      {children}
    </section>
  );
}
