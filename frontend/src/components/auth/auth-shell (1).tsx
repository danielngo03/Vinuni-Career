/**
 * Centered card layout for the standalone auth pages (login/register/etc).
 * Single-level card (no nested cards) on the subtle app background. The public
 * header (with the brand mark) is provided by the surrounding public shell.
 */
export function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <div className="flex min-h-[calc(100dvh-60px)] w-full flex-col items-center justify-center px-4 py-10">
      <div className="w-full max-w-md">
        <div className="rounded-2xl border border-white/60 bg-white/82 p-6 shadow-[0_8px_32px_rgba(11,34,57,0.12),0_2px_8px_rgba(11,34,57,0.06)] backdrop-blur-md sm:p-8">
          <h1 className="text-2xl font-bold tracking-tight text-[var(--text-primary)]">
            {title}
          </h1>
          {subtitle && (
            <p className="mt-1.5 text-sm text-[var(--text-secondary)]">
              {subtitle}
            </p>
          )}
          <div className="mt-6">{children}</div>
        </div>
        {footer && (
          <p className="mt-5 text-center text-sm text-[var(--text-secondary)]">
            {footer}
          </p>
        )}
      </div>
    </div>
  );
}
