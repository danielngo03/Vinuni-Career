"use client";

import { useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  PlusCircle,
  Trash,
  UserPlus,
  UsersThree,
  X,
} from "@phosphor-icons/react";
import {
  Button,
  EmptyState,
  Input,
  Modal,
  SkeletonCard,
  StatusBadge,
  Textarea,
  useToast,
} from "@/components/ui";
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

  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const [membersFor, setMembersFor] = useState<CareerServicesCohort | null>(null);
  const [newStudentId, setNewStudentId] = useState("");

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

  const cohorts = useMemo(() => query.data ?? [], [query.data]);
  const permissionState =
    query.isError && query.error instanceof ApiError ? (
      <CareerServicesPermissionGate error={query.error} bodyOverride={t("cohorts.permissionBody")} />
    ) : null;

  return (
    <CareerServicesShell
      title={t("cohorts.title")}
      description={t("cohorts.subtitle")}
      actions={
        !permissionState && (
          <Button onClick={() => setCreateOpen(true)}>
            <PlusCircle aria-hidden weight="bold" className="size-4" />
            {t("cohorts.create")}
          </Button>
        )
      }
    >
      {permissionState ?? (
        <>
          {query.isLoading ? (
            <div className="grid gap-4 md:grid-cols-2">
              <SkeletonCard />
              <SkeletonCard />
            </div>
          ) : query.isError ? (
            <EmptyState
              kind="error"
              title={t("cohorts.loadFailed")}
              description={getErrorMessage(query.error)}
            />
          ) : cohorts.length === 0 ? (
            <EmptyState
              kind="empty"
              icon={UsersThree}
              title={t("cohorts.emptyTitle")}
              description={t("cohorts.emptyBody")}
              action={
                <Button onClick={() => setCreateOpen(true)}>
                  <PlusCircle aria-hidden weight="bold" className="size-4" />
                  {t("cohorts.create")}
                </Button>
              }
            />
          ) : (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {cohorts.map((cohort) => (
                <article
                  key={cohort.id}
                  className="rounded-xl border border-white/70 bg-white/85 p-4 shadow-sm backdrop-blur"
                >
                  <div className="mb-2 flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <h2 className="truncate text-base font-bold text-[var(--text-primary)]">
                        {cohort.name}
                      </h2>
                      <StatusBadge tone={cohort.status === "active" ? "active" : "closed"}>
                        {cohort.status_label}
                      </StatusBadge>
                    </div>
                  </div>
                  {cohort.description && (
                    <p className="mb-3 line-clamp-2 text-sm text-[var(--text-secondary)]">
                      {cohort.description}
                    </p>
                  )}
                  <p className="mb-3 text-xs text-[var(--text-muted)]">
                    {t("cohorts.createdAt", { date: formatDateTime(cohort.created_at, locale) })}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <Button variant="secondary" size="sm" onClick={() => setMembersFor(cohort)}>
                      <UserPlus aria-hidden weight="bold" className="size-4" />
                      {t("cohorts.manageMembers")}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      loading={archive.isPending && archive.variables?.id === cohort.id}
                      onClick={() => archive.mutate(cohort)}
                    >
                      <Archive aria-hidden weight="bold" className="size-4" />
                      {cohort.status === "active" ? t("cohorts.archive") : t("cohorts.reactivate")}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      loading={remove.isPending && remove.variables?.id === cohort.id}
                      onClick={() => {
                        if (window.confirm(t("cohorts.deleteConfirm"))) remove.mutate(cohort);
                      }}
                    >
                      <Trash aria-hidden weight="bold" className="size-4 text-[var(--brand-red)]" />
                    </Button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </>
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
            <Button
              loading={create.isPending}
              disabled={!name.trim()}
              onClick={() => create.mutate()}
            >
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

          {membersQuery.isLoading ? (
            <SkeletonCard />
          ) : (membersQuery.data ?? []).length === 0 ? (
            <p className="text-sm text-[var(--text-muted)]">{t("cohorts.noMembers")}</p>
          ) : (
            <ul className="divide-y divide-white/60 rounded-xl border border-white/60">
              {(membersQuery.data ?? []).map((m: CohortMembership) => (
                <li key={m.id} className="flex items-center justify-between gap-3 px-3.5 py-2.5">
                  <span className="truncate font-mono text-xs text-[var(--text-primary)]">
                    {m.student_id}
                  </span>
                  <button
                    type="button"
                    aria-label={t("cohorts.removeMember")}
                    onClick={() => removeMember.mutate(m.student_id)}
                    className="rounded-md p-1 text-[var(--text-muted)] hover:bg-[var(--bg-subtle)] hover:text-[var(--brand-red)]"
                  >
                    <X aria-hidden weight="bold" className="size-4" />
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
