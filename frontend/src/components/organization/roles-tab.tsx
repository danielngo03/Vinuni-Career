"use client";

import * as React from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { Button, EmptyState, Input, Modal, useToast } from "@/components/ui";
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
} from "@/components/kit";
import { ApiError, organizationApi, type OrgRole, type PermissionInput } from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { PermissionPicker } from "./permission-picker";

type EditState = { mode: "create" } | { mode: "edit"; role: OrgRole } | null;

function toInputs(perms: string[]): PermissionInput[] {
  return perms
    .filter((p) => p !== "*:*")
    .map((p) => {
      const [resource, action] = p.split(":");
      return { resource: resource ?? "", action: action ?? "" };
    });
}

export function RolesTab({
  effective,
  holdsWildcard,
  orgType,
}: {
  effective: ReadonlySet<string>;
  holdsWildcard: boolean;
  orgType: "partner" | "university";
}) {
  const t = useTranslations("team.roles");
  const tv = useTranslations("team.validation");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const toast = useToast();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();

  const canCreate = holdsWildcard || effective.has("roles:create") || effective.has("roles:*");
  const canUpdate = holdsWildcard || effective.has("roles:update") || effective.has("roles:*");
  const canDelete = holdsWildcard || effective.has("roles:delete") || effective.has("roles:*");

  const [edit, setEdit] = React.useState<EditState>(null);
  const [deleting, setDeleting] = React.useState<OrgRole | null>(null);
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [perms, setPerms] = React.useState<PermissionInput[]>([]);
  const [nameError, setNameError] = React.useState<string | null>(null);

  const query = useQuery({ queryKey: ["org", "roles"], queryFn: () => organizationApi.listRoles(), retry: false });

  React.useEffect(() => {
    if (edit?.mode === "edit") {
      setName(edit.role.name);
      setDescription(edit.role.description ?? "");
      setPerms(toInputs(edit.role.permissions));
    } else if (edit?.mode === "create") {
      setName("");
      setDescription("");
      setPerms([]);
    }
    setNameError(null);
  }, [edit]);

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["org", "roles"] });
    void qc.invalidateQueries({ queryKey: ["org", "members"] });
  }

  const isSystemEdit = edit?.mode === "edit" && edit.role.is_system;

  const save = useMutation({
    mutationFn: () => {
      if (edit?.mode === "edit") {
        return organizationApi.updateRole(edit.role.id, {
          name: edit.role.is_system ? undefined : name,
          description: description || null,
          permissions: edit.role.is_system ? undefined : perms,
        });
      }
      return organizationApi.createRole({ name, description: description || null, permissions: perms });
    },
    onSuccess: () => {
      setEdit(null);
      toast.show({ tone: "success", title: t("savedToast") });
      refresh();
    },
    onError: (e) => handleError(e),
  });

  const del = useMutation({
    mutationFn: (r: OrgRole) => organizationApi.deleteRole(r.id),
    onSuccess: () => {
      setDeleting(null);
      toast.show({ tone: "success", title: t("deletedToast") });
      refresh();
    },
    onError: (e) => handleError(e),
  });

  function handleError(e: unknown) {
    const reason = e instanceof ApiError && typeof e.details?.reason === "string" ? e.details.reason : undefined;
    if (reason === "last_admin") {
      toast.show({ tone: "error", title: t("lastAdminToast"), description: t("lastAdminBody") });
      setDeleting(null);
      return;
    }
    if (reason === "permission_escalation") {
      toast.show({ tone: "error", title: t("escalationToast"), description: t("escalationBody") });
      return;
    }
    if (reason === "version_conflict") {
      toast.show({ tone: "error", title: tc("conflictReload") });
      refresh();
      return;
    }
    toast.show({ tone: "error", title: getMessage(e) });
  }

  const columns: ColumnDef<OrgRole, unknown>[] = [
    {
      accessorKey: "name",
      header: t("name"),
      cell: ({ row }) => (
        <div className="flex items-center gap-2">
          <span className="font-semibold text-foreground">{row.original.name}</span>
          {row.original.is_system && (
            <StatusChip tone="info" size="sm">
              {t("system")}
            </StatusChip>
          )}
        </div>
      ),
    },
    {
      accessorKey: "permissions",
      header: t("permissions"),
      enableSorting: false,
      cell: ({ row }) =>
        row.original.permissions.includes("*:*") ? (
          <StatusChip tone="sky" size="sm">
            {t("fullAccess")}
          </StatusChip>
        ) : (
          <span className="type-small text-muted-foreground">{t("permCount", { count: row.original.permissions.length })}</span>
        ),
    },
    {
      id: "actions",
      header: "",
      meta: { align: "right" },
      enableSorting: false,
      cell: ({ row }) => (
        <div className="flex justify-end gap-1">
          {canUpdate && (
            <Button variant="ghost" size="sm" onClick={() => setEdit({ mode: "edit", role: row.original })}>
              {tc("edit")}
            </Button>
          )}
          {canDelete && !row.original.is_system && (
            <Button
              variant="ghost"
              size="sm"
              className="text-[var(--content-danger)]"
              onClick={() => setDeleting(row.original)}
            >
              {tc("delete")}
            </Button>
          )}
        </div>
      ),
    },
  ];

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{t("title")}</CardTitle>
          <CardDescription>{t("intro")}</CardDescription>
        </div>
        {canCreate && (
          <CardToolbar>
            <Button variant="primary" size="sm" onClick={() => setEdit({ mode: "create" })}>
              <Plus className="size-4" strokeWidth={2} />
              {t("create")}
            </Button>
          </CardToolbar>
        )}
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
            getRowId={(r) => r.id}
            loading={query.isPending}
            empty={<EmptyState kind="empty" title={t("empty")} />}
          />
        )}
      </CardContent>

      <Modal
        open={edit !== null}
        onClose={() => setEdit(null)}
        title={edit?.mode === "edit" ? t("editTitle") : t("createTitle")}
        size="md"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setEdit(null)}>
              {tc("cancel")}
            </Button>
            <Button
              variant="primary"
              loading={save.isPending}
              onClick={() => {
                if (!isSystemEdit && name.trim().length < 2) {
                  setNameError(tv("roleNameMin"));
                  return;
                }
                save.mutate();
              }}
            >
              {tc("save")}
            </Button>
          </>
        }
      >
        <div className="space-y-5">
          {isSystemEdit && (
            <p
              className="rounded-xl px-3 py-2 text-[0.8125rem]"
              style={{ background: "var(--content-warning-soft)", color: "var(--content-warning)" }}
            >
              {t("systemRoleNote")}
            </p>
          )}
          <Input
            label={t("name")}
            required
            value={name}
            disabled={isSystemEdit}
            onChange={(e) => {
              setName(e.target.value);
              if (nameError) setNameError(null);
            }}
            error={nameError ?? undefined}
          />
          <Input label={t("description")} value={description} onChange={(e) => setDescription(e.target.value)} />
          {isSystemEdit ? (
            <div>
              <p className="mb-1.5 type-small font-semibold text-foreground">{t("permissions")}</p>
              <StatusChip tone="sky">{t("fullAccess")}</StatusChip>
            </div>
          ) : (
            <PermissionPicker value={perms} onChange={setPerms} effective={effective} holdsWildcard={holdsWildcard} orgType={orgType} />
          )}
        </div>
      </Modal>

      <Modal
        open={deleting !== null}
        onClose={() => setDeleting(null)}
        title={t("deleteTitle")}
        description={t("deleteBody", { name: deleting?.name ?? "" })}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeleting(null)}>
              {tc("cancel")}
            </Button>
            <Button variant="danger" loading={del.isPending} onClick={() => deleting && del.mutate(deleting)}>
              {tc("delete")}
            </Button>
          </>
        }
      >
        <p className="type-small text-muted-foreground">{t("deleteNote")}</p>
      </Modal>
    </Card>
  );
}
