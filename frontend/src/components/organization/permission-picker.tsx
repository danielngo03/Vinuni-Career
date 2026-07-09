"use client";

import { useTranslations } from "next-intl";
import type { PermissionInput } from "@/lib/api";
import { PERMISSION_CATALOG, grants } from "@/lib/validation/organization";

/**
 * Permission checkbox grid for role create/edit. Implements the escalation
 * ceiling in the UI (ADR-0002 §6.4): an actor may only grant permissions that
 * are a subset of their own effective grants (unless they hold `*:*`).
 * Permissions the actor lacks are shown disabled with a hint. The backend
 * enforces this too — the UI only mirrors it.
 */
export function PermissionPicker({
  value,
  onChange,
  effective,
  holdsWildcard,
  orgType,
}: {
  value: PermissionInput[];
  onChange: (next: PermissionInput[]) => void;
  effective: ReadonlySet<string>;
  holdsWildcard: boolean;
  orgType: "partner" | "university";
}) {
  const t = useTranslations("team.permissions");

  const has = (resource: string, action: string) =>
    value.some((p) => p.resource === resource && p.action === action);

  const canGrant = (resource: string, action: string) =>
    holdsWildcard || grants(effective, resource, action);

  function toggle(resource: string, action: string) {
    if (!canGrant(resource, action)) return;
    if (has(resource, action)) {
      onChange(value.filter((p) => !(p.resource === resource && p.action === action)));
    } else {
      onChange([...value, { resource, action }]);
    }
  }

  const resources = PERMISSION_CATALOG.filter(
    (r) => !r.universityOnly || orgType === "university",
  );

  return (
    <fieldset className="space-y-4">
      <legend className="sr-only">{t("legend")}</legend>
      {resources.map((res) => (
        <div key={res.resource}>
          <p className="mb-1.5 type-small font-semibold text-foreground">
            {t(`resource.${res.resource}`)}
          </p>
          <div className="flex flex-wrap gap-2">
            {res.actions.map((action) => {
              const allowed = canGrant(res.resource, action);
              const checked = has(res.resource, action);
              return (
                <label
                  key={action}
                  className={
                    "inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors " +
                    (allowed
                      ? "cursor-pointer border-border hover:border-border-strong"
                      : "cursor-not-allowed border-dashed border-border opacity-50") +
                    (checked && allowed
                      ? " border-[var(--brand-primary)] bg-[var(--content-info-soft)] text-[var(--brand-primary)]"
                      : " text-muted-foreground")
                  }
                  title={!allowed ? t("notAllowed") : undefined}
                >
                  <input
                    type="checkbox"
                    className="size-3.5 rounded border-border text-[var(--brand-primary)] outline-none focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
                    checked={checked}
                    disabled={!allowed}
                    onChange={() => toggle(res.resource, action)}
                  />
                  {t(`action.${action}`)}
                </label>
              );
            })}
          </div>
        </div>
      ))}
      {!holdsWildcard && (
        <p className="type-caption text-muted-foreground">{t("ceilingNote")}</p>
      )}
    </fieldset>
  );
}
