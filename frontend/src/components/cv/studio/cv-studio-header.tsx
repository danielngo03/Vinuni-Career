export function CvStudioHeader({
  title,
  description,
  sideTitle,
  sideBody,
  actions,
}: {
  title: string;
  description: string;
  sideTitle?: string;
  sideBody?: string;
  actions?: React.ReactNode;
}) {
  return (
    <section className="mb-6 overflow-hidden rounded-[18px] border border-[var(--border-default)] bg-[var(--surface-card)] shadow-[0_14px_44px_rgba(11,34,57,0.09)]">
      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="relative bg-[var(--brand-navy)] p-6 sm:p-8">
          <div
            aria-hidden
            className="absolute inset-0 opacity-[0.16]"
            style={{
              backgroundImage:
                "linear-gradient(135deg, rgba(255,255,255,0.16) 1px, transparent 1px)",
              backgroundSize: "28px 28px",
            }}
          />
          <div className="relative max-w-2xl">
            <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-[var(--blue-200)]">
              CV Studio
            </p>
            <h1 className="mt-3 text-3xl font-extrabold leading-tight tracking-tight text-white sm:text-4xl">
              {title}
            </h1>
            <p className="mt-3 max-w-xl text-sm leading-6 text-[var(--blue-100)]/86">
              {description}
            </p>
          </div>
        </div>
        <div className="flex items-center border-t border-[var(--border-default)] bg-[var(--surface-card)] p-6 lg:border-l lg:border-t-0">
          <div className="w-full">
            {sideTitle && (
              <p className="text-sm font-bold text-[var(--brand-navy)]">
                {sideTitle}
              </p>
            )}
            {sideBody && (
              <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
                {sideBody}
              </p>
            )}
            {actions && (
              <div className="mt-4 flex flex-wrap gap-2">
                {actions}
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
