"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, Plus, Trash2, UserPlus, Users, X } from "lucide-react";
import { Button, Input, Modal, Textarea, useToast } from "@/components/ui";
import {
  DataTable,
  EmptyState,
  StatusChip,
  type ChipTone,
  type ColumnDef,
} from "@/components/kit";
import { CareerServicesShell } from "./career-services-shell";
import { CareerServicesPermissionGate } from "./permission-gate";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import {
  ApiError,
  careerServicesApi,
  type CareerServicesCohort,
  type CohortMembership,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";

export function CohortsScreen() {
  const t = useTranslations("careerServices");
  const locale = useLocale();
  const toast = useToast();
  const getErrorMessage = useApiErrorMessage();
  const qc = useQueryClient();

  const [createOpen, setCreateOpen] = React.useState(false);
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");

  const [membersFor, setMembersFor] = React.useState<CareerServicesCohort | null>(null);
  const [newStudentId, setNewStudentId] = React.useState("");

  const query = useQuery({
    queryKey: ["career-services", "cohorts", locale],
    queryFn: () => careerServicesApi.listCohorts(locale),
    retry: false,
  });

  const membersQuery = useQuery({
    queryKey: ["career-services", "cohort-members", membersFor?.id],
    queryFn: () => careerServicesApi.listMembers(membersFor!.id),
    enabled: !!membersFor,
  });

  const refresh = () => qc.invalidateQueries({ queryKey: ["career-services", "cohorts"] });

  const create = useMutation({
    mutationFn: () =>
      careerServicesApi.createCohort(
        { name: name.trim(), description: description.trim() || null },
        locale,
      ),
    onSuccess: () => {
      toast.show({ tone: "success", title: t("cohorts.createdToast") });
      setCreateOpen(false);
      setName("");
      setDescription("");
      refresh();
    },
    onError: (error) => toast.show({ tone: "error", title: getErrorMessage(error) }),
  });

  const archive = useMutation({
    mutationFn: (cohort: CareerServicesCohort) =>
      careerServicesApi.updateCohort(
        cohort.id,
        { status: cohort.status === "active" ? "archived" : "active" },
        locale,
      ),
    onSuccess: () => {
      toast.show({ tone: "success", title: t("cohorts.updatedToast") });
      refresh();
    },
    onError: (error) => toast.show({ tone: "error", title: getErrorMessage(error) }),
  });

  const remove = useMutation({
    mutationFn: (cohort: CareerServicesCohort) => careerServicesApi.deleteCohort(cohort.id),
    onSuccess: () => {
      toast.show({ tone: "success", title: t("cohorts.deletedToast") });
      refresh();
    },
    onError: (error) => toast.show({ tone: "error", title: getErrorMessage(error) }),
  });

  const addMember = useMutation({
    mutationFn: () => careerServicesApi.addMember(membersFor!.id, newStudentId.trim()),
    onSuccess: () => {
      setNewStudentId("");
      qc.invalidateQueries({
        queryKey: ["career-services", "cohort-members", membersFor?.id],
      });
    },
    onError: (error) => toast.show({ tone: "error", title: getErrorMessage(error) }),
  });

  const removeMember = useMutation({
    mutationFn: (studentId: string) =>
      careerServicesApi.removeMember(membersFor!.id, studentId),
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: ["career-services", "cohort-members", membersFor?.id],
      });
    },
    onError: (error) => toast.show({ tone: "error", title: getErrorMessage(error) }),
  });

  const cohorts = query.data ?? [];
  const permissionState =
    query.isError && query.error instanceof ApiError ? (
      <CareerServicesPermissionGate error={query.error} bodyOverride={t("cohorts.permissionBody")} />
    ) : null;

  const createButton = (
    <Button onClick={() => setCreateOpen(true)} size="sm">
      <Plus className="size-4" strokeWidth={2} />
      {t("cohorts.create")}
    </Button>
  );

  const columns: ColumnDef<CareerServicesCohort, unknown>[] = [
    {
      accessorKey: "name",
      header: t("cohorts.colName"),
      cell: ({ row }) => (
        <div className="min-w-0">
          <span className="block truncate font-semibold text-foreground">{row.original.name}</span>
          {row.original.description && (
            <span className="type-caption block max-w-sm truncate text-muted-foreground">
              {row.original.description}
            </span>
          )}
        </div>
      ),
    },
    {
      accessorKey: "status",
      header: t("cohorts.colStatus"),
      cell: ({ row }) => (
        <StatusChip tone={row.original.status === "active" ? ("success" as ChipTone) : "neutral"} dot>
          {row.original.status_label}
        </StatusChip>
      ),
    },
    {
      id: "created",
      header: t("cohorts.colCreated"),
      meta: { align: "right" },
      cell: ({ row }) => (
        <span className="type-small tabular-nums text-muted-foreground">
          {formatDateTime(row.original.created_at, locale)}
        </span>
      ),
    },
    {
      id: "actions",
      header: "",
      enableSorting: false,
      meta: { align: "right" },
      cell: ({ row }) => {
        const cohort = row.original;
        return (
          <div className="flex items-center justify-end gap-1">
            <Button variant="ghost" size="sm" onClick={() => setMembersFor(cohort)}>
              <UserPlus className="size-4" strokeWidth={1.8} />
              {t("cohorts.manageMembers")}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              loading={archive.isPending && archive.variables?.id === cohort.id}
              onClick={() => archive.mutate(cohort)}
            >
              <Archive className="size-4" strokeWidth={1.8} />
              {cohort.status === "active" ? t("cohorts.archive") : t("cohorts.reactivate")}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              aria-label={t("cohorts.delete")}
              loading={remove.isPending && remove.variables?.id === cohort.id}
              onClick={() => {
                if (window.confirm(t("cohorts.deleteConfirm"))) remove.mutate(cohort);
              }}
            >
              <Trash2 className="size-4 text-[var(--content-danger)]" strokeWidth={1.8} />
            </Button>
          </div>
        );
      },
    },
  ];

  return (
    <CareerServicesShell
      title={t("cohorts.title")}
      description={t("cohorts.subtitle")}
      actions={!permissionState ? createButton : undefined}
    >
      {permissionState ?? (
        <DataTable
          columns={columns}
          data={cohorts}
          getRowId={(r) => r.id}
          loading={query.isPending}
          empty={
            <EmptyState
              kind="empty"
              icon={Users}
              title={t("cohorts.emptyTitle")}
              description={t("cohorts.emptyBody")}
              action={createButton}
            />
          }
        />
      )}

      {/* Create cohort */}
      <Modal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title={t("cohorts.createTitle")}
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setCreateOpen(false)} disabled={create.isPending}>
              {t("cancel")}
            </Button>
            <Button loading={create.isPending} disabled={!name.trim()} onClick={() => create.mutate()}>
              {t("save")}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input
            label={t("cohorts.nameLabel")}
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <Textarea
            label={t("cohorts.descriptionLabel")}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
          />
        </div>
      </Modal>

      {/* Manage members */}
      <Modal
        open={!!membersFor}
        onClose={() => setMembersFor(null)}
        title={t("cohorts.membersTitle", { name: membersFor?.name ?? "" })}
        size="md"
      >
        <div className="space-y-4">
          <div className="flex items-end gap-2">
            <Input
              label={t("cohorts.addStudentLabel")}
              placeholder={t("cohorts.studentIdPlaceholder")}
              help={t("cohorts.studentIdHelp")}
              value={newStudentId}
              onChange={(e) => setNewStudentId(e.target.value)}
              className="flex-1"
            />
            <Button
              loading={addMember.isPending}
              disabled={!newStudentId.trim()}
              onClick={() => addMember.mutate()}
            >
              {t("cohorts.add")}
            </Button>
          </div>

          {membersQuery.isPending ? (
            <div className="h-24 animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
          ) : (membersQuery.data ?? []).length === 0 ? (
            <p className="type-small text-muted-foreground">{t("cohorts.noMembers")}</p>
          ) : (
            <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border">
              {(membersQuery.data ?? []).map((m: CohortMembership) => (
                <li key={m.id} className="flex items-center justify-between gap-3 px-3.5 py-2.5">
                  <span className="truncate font-mono text-xs text-foreground">{m.student_id}</span>
                  <button
                    type="button"
                    aria-label={t("cohorts.removeMember")}
                    onClick={() => removeMember.mutate(m.student_id)}
                    className="rounded-md p-1 text-muted-foreground outline-none transition-colors hover:bg-[var(--bg-subtle)] hover:text-[var(--content-danger)] focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
                  >
                    <X className="size-4" strokeWidth={1.8} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Modal>
    </CareerServicesShell>
  );
}
