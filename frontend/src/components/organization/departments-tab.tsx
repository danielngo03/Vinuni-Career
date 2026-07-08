"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { TreeStructure, ShieldWarning, Plus } from "@phosphor-icons/react";
import {
  Button,
  DataTable,
  EmptyState,
  Input,
  Modal,
  Select,
  useToast,
  type Column,
} from "@/components/ui";
import { SectionCard } from "@/components/settings/section-card";
import { ApiError, organizationApi, type OrgDepartment } from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";

type EditState = { mode: "create" } | { mode: "edit"; dept: OrgDepartment } | null;

export function DepartmentsTab() {
  const t = useTranslations("team.departments");
  const tv = useTranslations("team.validation");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const toast = useToast();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();

  const [edit, setEdit] = useState<EditState>(null);
  const [deleting, setDeleting] = useState<OrgDepartment | null>(null);
  const [name, setName] = useState("");
  const [parentId, setParentId] = useState("");
  const [nameError, setNameError] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ["org", "departments"],
    queryFn: () => organizationApi.listDepartments(),
    retry: false,
  });

  // Departments are managed by org admins; we surface backend errors for
  // missing permissions rather than guessing here. Superadmin always allowed.
  const canManage = true;

  useEffect(() => {
    if (edit?.mode === "edit") {
      setName(edit.dept.name);
      setParentId(edit.dept.parent_id ?? "");
    } else if (edit?.mode === "create") {
      setName("");
      setParentId("");
    }
    setNameError(null);
  }, [edit]);

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["org", "departments"] });
  }

  const save = useMutation({
    mutationFn: () => {
      if (edit?.mode === "edit") {
        return organizationApi.updateDepartment(edit.dept.id, {
          name,
          parent_id: parentId || null,
          clear_parent: !parentId,
        });
      }
      return organizationApi.createDepartment({ name, parent_id: parentId || null });
    },
    onSuccess: () => {
      setEdit(null);
      toast.show({ tone: "success", title: t("savedToast") });
      refresh();
    },
    onError: (e) => toast.show({ tone: "error", title: getMessage(e) }),
  });

  const del = useMutation({
    mutationFn: (d: OrgDepartment) => organizationApi.deleteDepartment(d.id),
    onSuccess: () => {
      setDeleting(null);
      toast.show({ tone: "success", title: t("deletedToast") });
      refresh();
    },
    onError: (e) => {
      setDeleting(null);
      toast.show({ tone: "error", title: getMessage(e) });
    },
  });

  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    return (
      <SectionCard
        title={t("title")}
        description={t("intro")}
        icon={TreeStructure}
        iconGradient="icon-chip-success"
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
  const deptName = (id?: string | null) =>
    id ? (rows.find((d) => d.id === id)?.name ?? "—") : "—";

  const columns: Column<OrgDepartment>[] = [
    {
      key: "name",
      header: t("name"),
      cell: (d) => <span className="font-semibold text-[var(--text-primary)]">{d.name}</span>,
    },
    {
      key: "parent",
      header: t("parent"),
      cell: (d) => deptName(d.parent_id),
    },
    {
      key: "actions",
      header: "",
      align: "right",
      cell: (d) => (
        <div className="flex justify-end gap-1">
          <Button variant="ghost" size="sm" onClick={() => setEdit({ mode: "edit", dept: d })}>
            {tc("edit")}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="text-[var(--brand-red)]"
            onClick={() => setDeleting(d)}
          >
            {tc("delete")}
          </Button>
        </div>
      ),
    },
  ];

  // Parent options exclude the dept being edited (no self-parent).
  const parentOptions = [
    { value: "", label: t("noParent") },
    ...rows
      .filter((d) => !(edit?.mode === "edit" && d.id === edit.dept.id))
      .map((d) => ({ value: d.id, label: d.name })),
  ];

  return (
    <SectionCard title={t("title")} description={t("intro")}>
      {canManage && (
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
        getRowId={(d) => d.id}
        loading={query.isPending}
        caption={t("title")}
        empty={{ kind: "empty", icon: TreeStructure, title: t("empty") }}
      />

      <Modal
        open={edit !== null}
        onClose={() => setEdit(null)}
        title={edit?.mode === "edit" ? t("editTitle") : t("createTitle")}
        size="sm"
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
                if (name.trim().length < 2) {
                  setNameError(tv("deptNameMin"));
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
        <div className="space-y-4">
          <Input
            label={t("name")}
            required
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              if (nameError) setNameError(null);
            }}
            error={nameError ?? undefined}
          />
          <Select
            label={t("parent")}
            value={parentId}
            onChange={(e) => setParentId(e.target.value)}
            options={parentOptions}
          />
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
