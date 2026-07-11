"use client";

import * as React from "react";
import { useForm, useWatch } from "react-hook-form";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Eye, RotateCcw } from "lucide-react";
import { Button, EmptyState, Input, Modal, Select, useToast } from "@/components/ui";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
  CardToolbar,
  DataTable,
  type ColumnDef,
  StatusChip,
  type ChipTone,
} from "@/components/kit";
import { ApiError, organizationApi, type OrgInvitation, type OrgRole, type PermissionPreview } from "@/lib/api";
import { useApiErrorMessage, applyFieldErrors } from "@/lib/auth/use-api-error";
import { zodResolver } from "@/lib/validation/resolver";
import { grants, invitationSchema, type InvitationValues } from "@/lib/validation/organization";
import { formatDateTime } from "@/lib/format";
import { PermissionPreviewModal } from "./permission-preview-panel";

const STATUS_TONE: Record<string, ChipTone> = {
  pending: "warning",
  accepted: "success",
  revoked: "neutral",
  expired: "neutral",
};

const STATUS_LABEL_KEY: Record<string, string> = {
  pending: "statusPending",
  accepted: "statusAccepted",
  revoked: "statusRevoked",
  expired: "statusExpired",
};

function canAssignRole(role: OrgRole, effective: ReadonlySet<string>, holdsWildcard: boolean): boolean {
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

  const [createOpen, setCreateOpen] = React.useState(false);
  const [revoking, setRevoking] = React.useState<OrgInvitation | null>(null);
  const [formError, setFormError] = React.useState<string | null>(null);
  const [previewOpen, setPreviewOpen] = React.useState(false);

  const query = useQuery({ queryKey: ["org", "invitations"], queryFn: () => organizationApi.listInvitations(), retry: false });
  const rolesQuery = useQuery({ queryKey: ["org", "roles"], queryFn: () => organizationApi.listRoles(), retry: false });
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

  function openCreate(prefill?: OrgInvitation) {
    setFormError(null);
    reset({
      email: prefill?.email ?? "",
      role_id: prefill?.role_id ?? "",
      department_id: prefill?.department_id ?? "",
    });
    setCreateOpen(true);
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
        setFormError(reason === "seat_limit_reached" ? t("seatLimitError") : t("duplicateError"));
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

  const roles = rolesQuery.data ?? [];
  const depts = deptsQuery.data ?? [];
  const roleName = (id?: string | null) => (id ? (roles.find((r) => r.id === id)?.name ?? "—") : "—");

  const columns: ColumnDef<OrgInvitation, unknown>[] = [
    {
      accessorKey: "email",
      header: t("email"),
      cell: ({ row }) => <span className="font-medium text-foreground">{row.original.email}</span>,
    },
    {
      accessorKey: "role_id",
      header: t("role"),
      enableSorting: false,
      cell: ({ row }) => <span className="text-muted-foreground">{roleName(row.original.role_id)}</span>,
    },
    {
      accessorKey: "expires_at",
      header: t("expires"),
      cell: ({ row }) => (
        <span className="whitespace-nowrap tabular-nums text-muted-foreground">
          {formatDateTime(row.original.expires_at, locale)}
        </span>
      ),
    },
    {
      accessorKey: "status",
      header: t("status"),
      cell: ({ row }) => (
        <StatusChip tone={STATUS_TONE[row.original.status] ?? "info"} dot>
          {STATUS_LABEL_KEY[row.original.status] ? t(STATUS_LABEL_KEY[row.original.status]!) : row.original.status_label}
        </StatusChip>
      ),
    },
    {
      id: "actions",
      header: "",
      meta: { align: "right" },
      enableSorting: false,
      cell: ({ row }) =>
        row.original.status === "pending" ? (
          <Button variant="ghost" size="sm" className="text-[var(--content-danger)]" onClick={() => setRevoking(row.original)}>
            {t("revoke")}
          </Button>
        ) : row.original.status === "expired" || row.original.status === "revoked" ? (
          <Button variant="ghost" size="sm" onClick={() => openCreate(row.original)}>
            <RotateCcw className="size-3.5" strokeWidth={1.8} />
            {t("resend")}
          </Button>
        ) : null,
    },
  ];

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{t("title")}</CardTitle>
          <CardDescription>{t("intro")}</CardDescription>
        </div>
        <CardToolbar>
          <Button variant="primary" size="sm" onClick={() => openCreate()}>
            <Plus className="size-4" strokeWidth={2} />
            {t("invite")}
          </Button>
        </CardToolbar>
      </CardHeader>
      <CardContent>
        {query.isError && query.error instanceof ApiError ? (
          <EmptyState
            kind={query.error.isPermissionError ? "permission" : query.error.isAuthError ? "auth" : "error"}
            title={
              query.error.isPermissionError
                ? tStates("permissionTitle")
                : query.error.isAuthError
                  ? tStates("authTitle")
                  : tStates("errorTitle")
            }
            description={
              query.error.isPermissionError
                ? tStates("permissionBody")
                : query.error.isAuthError
                  ? tStates("authBody")
                  : tStates("errorBody")
            }
          />
        ) : (
          <DataTable
            columns={columns}
            data={query.data ?? []}
            getRowId={(i) => i.id}
            loading={query.isPending}
            empty={<EmptyState kind="empty" title={t("empty")} description={t("emptyBody")} />}
          />
        )}
      </CardContent>

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
            <Button variant="primary" loading={isSubmitting || create.isPending} onClick={handleSubmit((v) => create.mutate(v))}>
              {t("sendInvite")}
            </Button>
          </>
        }
      >
        <form className="space-y-4" onSubmit={handleSubmit((v) => create.mutate(v))} noValidate>
          {formError && (
            <p
              role="alert"
              className="rounded-xl px-3 py-2 text-[0.8125rem] font-medium"
              style={{ background: "var(--content-danger-soft)", color: "var(--content-danger)" }}
            >
              {formError}
            </p>
          )}
          <Input type="email" label={t("email")} required autoComplete="off" error={errors.email?.message} {...register("email")} />
          <Select
            label={t("role")}
            help={t("roleHelp")}
            options={[
              { value: "", label: t("noRole") },
              ...roles.map((r) => ({ value: r.id, label: r.name, disabled: !canAssignRole(r, effective, holdsWildcard) })),
            ]}
            {...register("role_id")}
          />
          <Select
            label={t("department")}
            options={[{ value: "", label: t("noDept") }, ...depts.map((d) => ({ value: d.id, label: d.name }))]}
            {...register("department_id")}
          />
          <Button type="button" variant="secondary" size="sm" disabled={!watchedRoleId} onClick={() => setPreviewOpen(true)}>
            <Eye className="size-4" strokeWidth={1.8} />
            {tPreview("hypotheticalTitle")}
          </Button>
          {!watchedRoleId && <p className="type-caption text-muted-foreground">{tPreview("hypotheticalEmpty")}</p>}
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
            <Button variant="danger" loading={revoke.isPending} onClick={() => revoking && revoke.mutate(revoking)}>
              {t("revokeConfirm")}
            </Button>
          </>
        }
      >
        <p className="type-small text-muted-foreground">{t("revokeNote")}</p>
      </Modal>
    </Card>
  );
}
