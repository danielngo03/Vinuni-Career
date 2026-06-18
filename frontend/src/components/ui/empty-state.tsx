import type { Icon } from "@phosphor-icons/react";
import { Button } from "./button";

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  onAction,
}: {
  icon: Icon;
  title: string;
  description: string;
  action?: string;
  onAction?: () => void;
}) {
  return (
    <div className="flex min-h-52 flex-col items-center justify-center rounded-2xl border border-dashed bg-slate-50/70 px-6 py-10 text-center">
      <div className="flex size-12 items-center justify-center rounded-2xl bg-white text-primary shadow-sm ring-1 ring-slate-200">
        <Icon className="size-6" weight="duotone" />
      </div>
      <h3 className="mt-4 font-semibold">{title}</h3>
      <p className="mt-2 max-w-sm text-sm leading-6 text-muted">{description}</p>
      {action && onAction ? (
        <Button className="mt-5" size="sm" onClick={onAction}>
          {action}
        </Button>
      ) : null}
    </div>
  );
}
