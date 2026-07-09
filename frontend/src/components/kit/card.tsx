import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Card — the fundamental content container of the v10 design system: a clean
 * card surface with a subtle 1px border, soft shadow, and rounded-xl geometry
 * (Linear/Vercel admin feel). Every content panel is a Card. The shell (header/
 * sidebar) is deliberately NOT a Card — it stays mono/flat.
 *
 * Compose freely:
 *   <Card>
 *     <CardHeader>
 *       <div><CardTitle>…</CardTitle><CardDescription>…</CardDescription></div>
 *       <CardToolbar>…actions…</CardToolbar>
 *     </CardHeader>
 *     <CardContent>…</CardContent>
 *     <CardFooter>…</CardFooter>
 *   </Card>
 */
export function Card({
  className,
  padded = false,
  interactive = false,
  ...props
}: React.ComponentProps<"div"> & {
  /** Apply default inner padding directly on the card (skip CardHeader/Content). */
  padded?: boolean;
  /** Add hover elevation + border emphasis (for clickable cards). */
  interactive?: boolean;
}) {
  return (
    <div
      data-slot="card"
      className={cn(
        "rounded-xl border border-border bg-card text-card-foreground shadow-[var(--shadow-sm)]",
        interactive &&
          "transition-[border-color,box-shadow] duration-200 hover:border-border-strong hover:shadow-[var(--shadow-md)]",
        padded && "p-5",
        className,
      )}
      {...props}
    />
  );
}

export function CardHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-header"
      className={cn(
        "flex items-start justify-between gap-3 px-5 pt-5 pb-3",
        className,
      )}
      {...props}
    />
  );
}

export function CardTitle({ className, ...props }: React.ComponentProps<"h3">) {
  return (
    <h3
      data-slot="card-title"
      className={cn("type-h3 text-foreground", className)}
      {...props}
    />
  );
}

export function CardDescription({
  className,
  ...props
}: React.ComponentProps<"p">) {
  return (
    <p
      data-slot="card-description"
      className={cn("type-small mt-0.5 text-muted-foreground", className)}
      {...props}
    />
  );
}

/** Right-aligned header slot for actions / filters / view toggles. */
export function CardToolbar({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-toolbar"
      className={cn("flex shrink-0 items-center gap-2", className)}
      {...props}
    />
  );
}

export function CardContent({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div data-slot="card-content" className={cn("px-5 pb-5", className)} {...props} />
  );
}

export function CardFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-footer"
      className={cn(
        "flex items-center gap-2 border-t border-border px-5 py-3",
        className,
      )}
      {...props}
    />
  );
}

/** Section label used inside cards/sheets — small-caps eyebrow. */
export function SectionLabel({ className, ...props }: React.ComponentProps<"p">) {
  return (
    <p
      className={cn(
        "text-[0.6875rem] font-semibold uppercase tracking-[0.08em] text-muted-foreground",
        className,
      )}
      {...props}
    />
  );
}
