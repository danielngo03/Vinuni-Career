"use client";

import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { EnvelopeSimple, ShieldWarning, Plus, Eye } from "@phosphor-icons/react";
import {
  Button,
  DataTable,
  EmptyState,
  Input,
  Modal,
  Select,
  StatusBadge,
  useToast,
  type Column,
  type StatusTone,
} from "@/components/ui";
import { SectionCard } from "@/components/settings/section-card";
import { ApiError, organizationApi, type OrgInvitation, type OrgRole, type PermissionPreview } from "@/lib/api";
import { useApiErrorMessage, applyFieldErrors } from "@/lib/auth/use-api-error";
import { zodResolver } from "@/lib/validation/resolver";
import { grants, invitationSchema, type InvitationValues } from "@/lib/validation/organization";
import { formatDateTime } from "@/lib/format";
import { PermissionPreviewModal } from "./permission-preview-panel";

const STATUS_TONE: Record<string, StatusTone> = {
  pending: "pending",
  accepted: "accepted",
  revoked: "closed",
  expired: "closed",
};

const STATUS_LABEL_KEY: Record<string, string> = {
  pending: "statusPending",
  accepted: "statusAccepted",
  revoked: "statusRevoked",
  expired: "statusExpired",
};

function canAssignRole(
  role: OrgRole,
  effective: ReadonlySet<string>,
  holdsWildcard: boolean,
): boolean {
  if (holdsWildcard) return true;
  return role.permissions.every((perm) => {
    if (perm === "*:*") return false;
    const [resource, action] = perm.split(":", 2);
    return Boolean(resource && action && grants(effective, resource, action));
  });
}

export function InvitationsTab({
  effective,
  holdsWildcard,
}: {
  effective: ReadonlySet<string>;
  holdsWildcard: boolean;
}) {
  const t = useTranslations("team.invitations");
  const tv = useTranslations("auth.validation");
  const tPreview = useTranslations("team.permissionPreview");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const toast = useToast();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();

  const [createOpen, setCreateOpen] = useState(false);
  const [revoking, setRevoking] = useState<OrgInvitation | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);

  const query = useQuery({
    queryKey: ["org", "invitations"],
    queryFn: () => organizationApi.listInvitations(),
    retry: false,
  });
  const rolesQuery = useQuery({
    queryKey: ["org", "roles"],
    queryFn: () => organizationApi.listRoles(),
    retry: false,
  });
  const deptsQuery = useQuery({
    queryKey: ["org", "departments"],
    queryFn: () => organizationApi.listDepartments(),
    retry: false,
  });

  const {
    register,
    handleSubmit,
    reset,
    setError,
    control,
    formState: { errors, isSubmitting },
  } = useForm<InvitationValues>({
    resolver: zodResolver(invitationSchema(tv)),
    defaultValues: { email: "", role_id: "", department_id: "" },
  });

  const watchedRoleId = useWatch({ control, name: "role_id" });
  const watchedDeptId = useWatch({ control, name: "department_id" });

  const hypotheticalPreview = useQuery({
    queryKey: ["org", "permission-preview", "hypothetical", watchedRoleId, watchedDeptId],
    queryFn: () =>
      organizationApi.previewHypotheticalPermissions({
        role_ids: watchedRoleId ? [watchedRoleId] : [],
        department_ids: watchedDeptId ? [watchedDeptId] : [],
      }),
    enabled: previewOpen && Boolean(watchedRoleId),
    retry: false,
  });

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["org", "invitations"] });
  }

  const create = useMutation({
    mutationFn: (values: InvitationValues) =>
      organizationApi.createInvitation({
        email: values.email,
        role_id: values.role_id || null,
        department_id: values.department_id || null,
      }),
    onSuccess: () => {
      setCreateOpen(false);
      reset();
      toast.show({ tone: "success", title: t("sentToast") });
      refresh();
    },
    onError: (e) => {
      if (applyFieldErrors(e, setError)) return;
      if (e instanceof ApiError && e.code === "CONFLICT") {
        const reason = e.details?.reason;
        if (reason === "seat_limit_reached") {
          setFormError(t("seatLimitError"));
        } else {
          setFormError(t("duplicateError"));
        }
        return;
      }
      setFormError(getMessage(e));
    },
  });

  const revoke = useMutation({
    mutationFn: (inv: OrgInvitation) => organizationApi.revokeInvitation(inv.id),
    onSuccess: () => {
      setRevoking(null);
      toast.show({ tone: "success", title: t("revokedToast") });
      refresh();
    },
    onError: (e) => {
      setRevoking(null);
      toast.show({ tone: "error", title: getMessage(e) });
    },
  });

  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    return (
      <SectionCard
        title={t("title")}
        description={t("intro")}
        icon={EnvelopeSimple}
        iconGradient="icon-chip-warning"
      >
        <EmptyState
          kind={err.isPermissionError ? "permission" : err.isAuthError ? "auth" : "error"}
          icon={ShieldWarning}
          title={
            err.isPermissionError
              ? tStates("permissionTitle")
              : err.isAuthError
                ? tStates("authTitle")
                : tStates("errorTitle")
          }
          description={
            err.isPermissionError
              ? tStates("permissionBody")
              : err.isAuthError
                ? tStates("authBody")
                : tStates("errorBody")
          }
        />
      </SectionCard>
    );
  }

  const rows = query.data ?? [];
  const roles = rolesQuery.data ?? [];
  const depts = deptsQuery.data ?? [];
  const roleName = (id?: string | null) => (id ? (roles.find((r) => r.id === id)?.name ?? "—") : "—");

  const columns: Column<OrgInvitation>[] = [
    {
      key: "email",
      header: t("email"),
      cell: (i) => <span className="font-medium text-[var(--text-primary)]">{i.email}</span>,
    },
    {
      key: "role",
      header: t("role"),
      cell: (i) => roleName(i.role_id),
    },
    {
      key: "expires",
      header: t("expires"),
      cell: (i) => formatDateTime(i.expires_at, locale),
    },
    {
      key: "status",
      header: t("status"),
      cell: (i) => (
        <StatusBadge tone={STATUS_TONE[i.status] ?? "info"}>
          {STATUS_LABEL_KEY[i.status] ? t(STATUS_LABEL_KEY[i.status]!) : i.status_label}
        </StatusBadge>
      ),
    },
    {
      key: "actions",
      header: "",
      align: "right",
      cell: (i) =>
        i.status === "pending" ? (
          <Button
            variant="ghost"
            size="sm"
            className="text-[var(--brand-red)]"
            onClick={() => setRevoking(i)}
          >
            {t("revoke")}
          </Button>
        ) : null,
    },
  ];

  return (
    <SectionCard title={t("title")} description={t("intro")}>
      <div className="mb-4 flex justify-end">
        <Button
          variant="primary"
          size="sm"
          onClick={() => {
            setFormError(null);
            reset();
            setCreateOpen(true);
          }}
        >
          <Plus aria-hidden weight="bold" className="size-4" />
          {t("invite")}
        </Button>
      </div>
      <DataTable
        columns={columns}
        rows={rows}
        getRowId={(i) => i.id}
        loading={query.isPending}
        caption={t("title")}
        empty={{ kind: "empty", icon: EnvelopeSimple, title: t("empty"), description: t("emptyBody") }}
      />

      <Modal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title={t("inviteTitle")}
        description={t("inviteBody")}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setCreateOpen(false)}>
              {tc("cancel")}
            </Button>
            <Button
              variant="primary"
              loading={isSubmitting || create.isPending}
              onClick={handleSubmit((v) => create.mutate(v))}
            >
              {t("sendInvite")}
            </Button>
          </>
        }
      >
        <form
          className="space-y-4"
          onSubmit={handleSubmit((v) => create.mutate(v))}
          noValidate
        >
          {formError && (
            <p
              role="alert"
              className="rounded-xl border border-[var(--red-400)]/40 bg-[var(--red-50)] px-3 py-2 text-sm font-medium text-[var(--brand-red)]"
            >
              {formError}
            </p>
          )}
          <Input
            type="email"
            label={t("email")}
            required
            autoComplete="off"
            error={errors.email?.message}
            {...register("email")}
          />
          <Select
            label={t("role")}
            help={t("roleHelp")}
            options={[
              { value: "", label: t("noRole") },
              ...roles.map((r) => ({
                value: r.id,
                label: r.name,
                disabled: !canAssignRole(r, effective, holdsWildcard),
              })),
            ]}
            {...register("role_id")}
          />
          <Select
            label={t("department")}
            options={[
              { value: "", label: t("noDept") },
              ...depts.map((d) => ({ value: d.id, label: d.name })),
            ]}
            {...register("department_id")}
          />
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={!watchedRoleId}
            onClick={() => setPreviewOpen(true)}
          >
            <Eye aria-hidden weight="duotone" className="size-4" />
            {tPreview("hypotheticalTitle")}
          </Button>
          {!watchedRoleId && (
            <p className="text-xs text-[var(--text-muted)]">
              {tPreview("hypotheticalEmpty")}
            </p>
          )}
        </form>
      </Modal>

      <PermissionPreviewModal
        open={previewOpen}
        onClose={() => setPreviewOpen(false)}
        title={tPreview("hypotheticalTitle")}
        preview={hypotheticalPreview.data as PermissionPreview | undefined}
        loading={hypotheticalPreview.isPending}
        error={hypotheticalPreview.isError}
      />

      <Modal
        open={revoking !== null}
        onClose={() => setRevoking(null)}
        title={t("revokeTitle")}
        description={t("revokeBody", { email: revoking?.email ?? "" })}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setRevoking(null)}>
              {tc("cancel")}
            </Button>
            <Button
              variant="danger"
              loading={revoke.isPending}
              onClick={() => revoking && revoke.mutate(revoking)}
            >
              {t("revokeConfirm")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-[var(--text-secondary)]">{t("revokeNote")}</p>
      </Modal>
    </SectionCard>
  );
}
