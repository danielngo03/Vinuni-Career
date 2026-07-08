"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { IdentificationBadge, ShieldWarning, Plus } from "@phosphor-icons/react";
import {
  Button,
  DataTable,
  EmptyState,
  Input,
  Modal,
  StatusBadge,
  useToast,
  type Column,
} from "@/components/ui";
import { SectionCard } from "@/components/settings/section-card";
import { ApiError, organizationApi, type OrgRole, type PermissionInput } from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { PermissionPicker } from "./permission-picker";

type EditState =
  | { mode: "create" }
  | { mode: "edit"; role: OrgRole }
  | null;

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

  const [edit, setEdit] = useState<EditState>(null);
  const [deleting, setDeleting] = useState<OrgRole | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [perms, setPerms] = useState<PermissionInput[]>([]);
  const [nameError, setNameError] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ["org", "roles"],
    queryFn: () => organizationApi.listRoles(),
    retry: false,
  });

  useEffect(() => {
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
    const reason =
      e instanceof ApiError && typeof e.details?.reason === "string"
        ? e.details.reason
        : undefined;
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

  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    return (
      <SectionCard
        title={t("title")}
        description={t("intro")}
        icon={IdentificationBadge}
        iconGradient="icon-chip-info"
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

  const columns: Column<OrgRole>[] = [
    {
      key: "name",
      header: t("name"),
      cell: (r) => (
        <div className="flex items-center gap-2">
          <span className="font-semibold text-[var(--text-primary)]">{r.name}</span>
          {r.is_system && <StatusBadge tone="verified">{t("system")}</StatusBadge>}
        </div>
      ),
    },
    {
      key: "permissions",
      header: t("permissions"),
      cell: (r) =>
        r.permissions.includes("*:*") ? (
          <StatusBadge tone="featured">{t("fullAccess")}</StatusBadge>
        ) : (
          <span className="text-sm text-[var(--text-secondary)]">
            {t("permCount", { count: r.permissions.length })}
          </span>
        ),
    },
    {
      key: "actions",
      header: "",
      align: "right",
      cell: (r) => (
        <div className="flex justify-end gap-1">
          {canUpdate && (
            <Button variant="ghost" size="sm" onClick={() => setEdit({ mode: "edit", role: r })}>
              {tc("edit")}
            </Button>
          )}
          {canDelete && !r.is_system && (
            <Button
              variant="ghost"
              size="sm"
              className="text-[var(--brand-red)]"
              onClick={() => setDeleting(r)}
            >
              {tc("delete")}
            </Button>
          )}
        </div>
      ),
    },
  ];

  return (
    <SectionCard title={t("title")} description={t("intro")}>
      {canCreate && (
        <div className="mb-4 flex justify-end">
          <Button variant="primary" size="sm" onClick={() => setEdit({ mode: "create" })}>
            <Plus aria-hidden weight="bold" className="size-4" />
            {t("create")}
          </Button>
        </div>
      )}
      <DataTable
        columns={columns}
        rows={rows}
        getRowId={(r) => r.id}
        loading={query.isPending}
        caption={t("title")}
        empty={{ kind: "empty", icon: IdentificationBadge, title: t("empty") }}
      />

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
            <p className="rounded-xl bg-[var(--amber-100)] px-3 py-2 text-sm text-[var(--amber-700)]">
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
          <Input
            label={t("description")}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          {isSystemEdit ? (
            <div>
              <p className="mb-1.5 text-sm font-semibold text-[var(--text-primary)]">
                {t("permissions")}
              </p>
              <StatusBadge tone="featured">{t("fullAccess")}</StatusBadge>
            </div>
          ) : (
            <PermissionPicker
              value={perms}
              onChange={setPerms}
              effective={effective}
              holdsWildcard={holdsWildcard}
              orgType={orgType}
            />
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
            <Button
              variant="danger"
              loading={del.isPending}
              onClick={() => deleting && del.mutate(deleting)}
            >
              {tc("delete")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-[var(--text-secondary)]">{t("deleteNote")}</p>
      </Modal>
    </SectionCard>
  );
}
