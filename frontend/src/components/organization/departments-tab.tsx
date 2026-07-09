"use client";

import * as React from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
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
} from "@/components/kit";
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

  const [edit, setEdit] = React.useState<EditState>(null);
  const [deleting, setDeleting] = React.useState<OrgDepartment | null>(null);
  const [name, setName] = React.useState("");
  const [parentId, setParentId] = React.useState("");
  const [nameError, setNameError] = React.useState<string | null>(null);

  const query = useQuery({
    queryKey: ["org", "departments"],
    queryFn: () => organizationApi.listDepartments(),
    retry: false,
  });

  React.useEffect(() => {
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

  const rows = query.data ?? [];
  const deptName = (id?: string | null) => (id ? (rows.find((d) => d.id === id)?.name ?? "—") : "—");

  const columns: ColumnDef<OrgDepartment, unknown>[] = [
    {
      accessorKey: "name",
      header: t("name"),
      cell: ({ row }) => <span className="font-semibold text-foreground">{row.original.name}</span>,
    },
    {
      accessorKey: "parent_id",
      header: t("parent"),
      enableSorting: false,
      cell: ({ row }) => <span className="text-muted-foreground">{deptName(row.original.parent_id)}</span>,
    },
    {
      id: "actions",
      header: "",
      meta: { align: "right" },
      enableSorting: false,
      cell: ({ row }) => (
        <div className="flex justify-end gap-1">
          <Button variant="ghost" size="sm" onClick={() => setEdit({ mode: "edit", dept: row.original })}>
            {tc("edit")}
          </Button>
          <Button variant="ghost" size="sm" className="text-[var(--content-danger)]" onClick={() => setDeleting(row.original)}>
            {tc("delete")}
          </Button>
        </div>
      ),
    },
  ];

  const parentOptions = [
    { value: "", label: t("noParent") },
    ...rows
      .filter((d) => !(edit?.mode === "edit" && d.id === edit.dept.id))
      .map((d) => ({ value: d.id, label: d.name })),
  ];

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{t("title")}</CardTitle>
          <CardDescription>{t("intro")}</CardDescription>
        </div>
        <CardToolbar>
          <Button variant="primary" size="sm" onClick={() => setEdit({ mode: "create" })}>
            <Plus className="size-4" strokeWidth={2} />
            {t("create")}
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
            data={rows}
            getRowId={(d) => d.id}
            loading={query.isPending}
            empty={<EmptyState kind="empty" title={t("empty")} />}
          />
        )}
      </CardContent>

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
          <Select label={t("parent")} value={parentId} onChange={(e) => setParentId(e.target.value)} options={parentOptions} />
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
