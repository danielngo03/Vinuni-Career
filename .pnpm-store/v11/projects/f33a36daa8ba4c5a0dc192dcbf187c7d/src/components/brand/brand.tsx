import Image from "next/image";
import Link from "next/link";
import { cn } from "@/lib/utils";

export function Brand({
  locale,
  compact = false,
  inverse = false,
  variant = "platform",
  className,
}: {
  locale: string;
  compact?: boolean;
  inverse?: boolean;
  variant?: "platform" | "wordmark" | "mark";
  className?: string;
}) {
  const wordmark = variant === "wordmark";
  const mark = variant === "mark";

  return (
    <Link
      href={`/${locale}`}
      className={cn(
        "focus-ring flex items-center gap-3 rounded-lg",
        className,
      )}
      aria-label="VinUniversity"
    >
      <Image
        src={
          wordmark
            ? "/brand/vinuni-logo-text.png"
            : "/brand/vinuni-logo.png"
        }
        alt="VinUniversity"
        width={wordmark ? 478 : 161}
        height={wordmark ? 108 : 152}
        className={cn(
          "w-auto object-contain",
          wordmark ? "h-11 xl:h-13" : mark ? "h-10" : "h-8",
          wordmark && !inverse && "brightness-0",
          !wordmark && inverse && "brightness-0 invert",
        )}
        priority
      />
      {variant === "platform" && !compact ? (
        <span
          className={cn(
            "whitespace-nowrap border-l pl-3 text-[10px] font-semibold uppercase tracking-[0.12em] text-muted",
            inverse && "border-white/20 text-white/65",
          )}
        >
          Career Platform
        </span>
      ) : null}
    </Link>
  );
}
