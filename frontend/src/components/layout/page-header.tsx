/**
 * Shared workspace page header (partner + university operating shells).
 *
 * - `eyebrow`: optional uppercase kicker above the title (`--kicker`, tracked).
 * - `title`: primary heading — unchanged type scale.
 * - `description`: optional subtitle rendered under the title.
 * - Brand signature: a thin 3px `--accent-bar` (VinUni red) rule running down
 *   the left of the title block — subtle, premium, theme-aware.
 *
 * All text is caller-translated; this component never hardcodes copy.
 */
export function PageHeader({
  title,
  description,
  eyebrow,
  actions,
}: {
  title: string;
  description?: string;
  eyebrow?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-stretch gap-3">
        <span
          aria-hidden
          className="w-[3px] shrink-0 rounded-full bg-[var(--accent-bar)]"
        />
        <div className="min-w-0">
          {eyebrow && (
            <p className="mb-0.5 text-[0.6875rem] font-semibold uppercase tracking-[0.12em] text-[var(--kicker)]">
              {eyebrow}
            </p>
          )}
          <h1 className="text-[1rem] font-bold tracking-tight text-[var(--text-primary)] sm:text-[1.3rem]">
            {title}
          </h1>
          {description && (
            <p className="mt-1 text-sm leading-relaxed text-[var(--text-secondary)]">
              {description}
            </p>
          )}
        </div>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
