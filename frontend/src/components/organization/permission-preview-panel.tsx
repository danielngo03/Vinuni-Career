"use client";

import { useTranslations } from "next-intl";
import { Eye, CheckCircle, ShieldWarning } from "@phosphor-icons/react";
import { Modal, Skeleton, EmptyState } from "@/components/ui";
import type { PermissionPreview } from "@/lib/api";

/**
 * Human-readable label for a single `resource:action` grant. Falls back to a
 * humanized version of the raw code when no i18n key exists yet, so newly
 * added catalog resources never leak raw enum codes (CLAUDE.md "no raw enum
 * codes" rule) while still rendering something useful.
 */
function humanize(token: string): string {
  return token
    .split("_")
    .map((w) => (w.length ? w[0]!.toUpperCase() + w.slice(1) : w))
    .join(" ");
}

export function useGrantLabels() {
  const t = useTranslations("team.permissions");

  function resourceLabel(resource: string): string {
    const key = `resource.${resource}`;
    return t.has(key) ? t(key) : humanize(resource);
  }

  function actionLabel(action: string): string {
    const key = `action.${action}`;
    return t.has(key) ? t(key) : humanize(action);
  }

  function grantLabel(grant: string): string {
    if (grant === "*:*") return t.has("wildcard") ? t("wildcard") : "Full access";
    const [resource, action] = grant.split(":", 2);
    if (!resource || !action) return grant;
    return `${resourceLabel(resource)} — ${actionLabel(action)}`;
  }

  return { resourceLabel, actionLabel, grantLabel };
}

/**
 * Grouped, plain-language rendering of an effective-grants preview
 * (`docs/PARTNER_RBAC_ANALYTICS_SPEC.md` permission preview). Shared by the
 * per-member "Preview access" action and the hypothetical role/department
 * preview used before sending an invite.
 */
export function PermissionPreviewBody({
  preview,
  loading,
  error,
}: {
  preview: PermissionPreview | undefined;
  loading: boolean;
  error: boolean;
}) {
  const t = useTranslations("team.permissionPreview");
  const { resourceLabel, actionLabel } = useGrantLabels();

  if (loading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-8 w-full" />
        ))}
      </div>
    );
  }

  if (error || !preview) {
    return (
      <EmptyState
        kind="error"
        icon={ShieldWarning}
        title={t("errorTitle")}
      />
    );
  }

  if (preview.is_admin) {
    return (
      <div className="flex items-start gap-2 rounded-xl border border-[var(--teal-500)]/30 bg-[var(--teal-50)] px-3.5 py-3 text-sm text-[var(--teal-700)]">
        <CheckCircle aria-hidden weight="fill" className="mt-0.5 size-4 shrink-0" />
        {t("isAdmin")}
      </div>
    );
  }

  const entries = Object.entries(preview.by_resource);
  if (entries.length === 0) {
    return <p className="text-sm text-[var(--text-muted)]">{t("noGrants")}</p>;
  }

  return (
    <div className="space-y-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        {t("grantCount", { count: preview.grants.length })}
      </p>
      {entries.map(([resource, actions]) => (
        <div key={resource}>
          <p className="mb-1.5 text-sm font-semibold text-[var(--text-primary)]">
            {resourceLabel(resource)}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {actions.map((action) => (
              <span
                key={action}
                className="inline-flex items-center rounded-md bg-[var(--bg-subtle)] px-2 py-1 text-xs font-medium text-[var(--text-secondary)]"
              >
                {actionLabel(action)}
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export function PermissionPreviewModal({
  open,
  onClose,
  title,
  preview,
  loading,
  error,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  preview: PermissionPreview | undefined;
  loading: boolean;
  error: boolean;
}) {
  const t = useTranslations("team.permissionPreview");
  return (
    <Modal open={open} onClose={onClose} title={title} size="sm" closeLabel={t("close")}>
      <PermissionPreviewBody preview={preview} loading={loading} error={error} />
    </Modal>
  );
}

export { Eye as PermissionPreviewIcon };
