import type { Icon } from "@phosphor-icons/react";

export function PageHeading({
  icon: Icon,
  eyebrow,
  title,
  description,
  actions,
}: {
  icon: Icon;
  eyebrow: string;
  title: string;
  description: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-5 rounded-2xl border bg-white p-5 shadow-[0_12px_30px_-28px_rgba(15,46,96,.7)] sm:p-6 lg:flex-row lg:items-center">
      <div className="flex min-w-0 items-start gap-4">
        <div className="flex size-12 shrink-0 items-center justify-center rounded-2xl bg-blue-50 text-primary ring-1 ring-blue-100">
          <Icon className="size-6" weight="duotone" />
        </div>
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-primary">
            {eyebrow}
          </p>
          <h1 className="mt-1 text-2xl font-semibold tracking-[-0.03em] sm:text-3xl">
            {title}
          </h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted">{description}</p>
        </div>
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap gap-2 lg:ml-auto">{actions}</div> : null}
    </div>
  );
}
