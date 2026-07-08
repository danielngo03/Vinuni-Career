import { cn } from "@/lib/utils";

interface CvLanguageBadgeProps {
  language: string | null | undefined;
  className?: string;
}

const LANG_LABELS: Record<string, string> = {
  vi: "VI",
  en: "EN",
};

export function CvLanguageBadge({ language, className }: CvLanguageBadgeProps) {
  const label = language ? LANG_LABELS[language.toLowerCase()] : null;
  if (!label) return null;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold tracking-wide",
        "border border-[var(--border-default)] text-[var(--text-muted)] bg-[var(--bg-subtle)]",
        className,
      )}
      aria-label={language?.toUpperCase()}
    >
      {label}
    </span>
  );
}
