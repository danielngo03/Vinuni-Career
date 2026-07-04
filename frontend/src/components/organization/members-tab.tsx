"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { UsersThree, ShieldWarning, Eye, PauseCircle, PlayCircle } from "@phosphor-icons/react";
import {
  Button,
  DataTable,
  EmptyState,
  Modal,
  StatusBadge,
  useToast,
  type Column,
} from "@/components/ui";
import { SectionCard } from "@/components/settings/section-card";
import {
  ApiError,
  organizationApi,
  type OrgRole,
  type OrgMember,
  type PermissionPreview,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { grants } from "@/lib/validation/organization";
import { PermissionPreviewModal } from "./permission-preview-panel";

function sameSet(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const right = new Set(b);
  return a.every((item) => right.has(item));
}

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

export function MembersTab({
  effective,
  holdsWildcard,
  currentEmail,
}: {
  effective: ReadonlySet<string>;
  holdsWildcard: boolean;
  currentEmail: string;
}) {
  const t = useTranslations("team.members");
  const tMember = useTranslations("team.memberStatus");
  const tPreview = useTranslations("team.permissionPreview");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const toast = useToast();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();

  const canManage = holdsWildcard || effective.has("members:update") || effective.has("members:*");
  const canRemove = holdsWildcard || effective.has("members:remove") || effective.has("members:*");
  const canPreview = holdsWildcard || effective.has("members:read") || effective.has("members:*");

  const [editing, setEditing] = useState<OrgMember | null>(null);
  const [removing, setRemoving] = useState<OrgMember | null>(null);
  const [deactivating, setDeactivating] = useState<OrgMember | null>(null);
  const [previewing, setPreviewing] = useState<OrgMember | null>(null);
  const [roleIds, setRoleIds] = useState<string[]>([]);
  const [deptIds, setDeptIds] = useState<string[]>([]);

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

  // Distinct, more-specific key than the plain (non-paginated) ["org","members"]
  // queries used elsewhere (team-screen.tsx summary counts, ownership-tab.tsx
  // owner lookup) to avoid a react-query cache collision: mixing useQuery and
  // useInfiniteQuery on the exact same key corrupts the cache entry's shape
  // ({pages,pageParams} vs {data,page}) for whichever consumer reads it second,
  // crashing with "Cannot read properties of undefined (reading 'filter')".
  // invalidateQueries({queryKey:["org","members"]}) elsewhere still matches
  // this key via react-query's default prefix matching.
  const members = useInfiniteQuery({
    queryKey: ["org", "members", "paginated"],
    queryFn: ({ pageParam }) => organizationApi.listMembers(pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.page.next_cursor ?? undefined,
    retry: false,
  });

  useEffect(() => {
    if (editing) {
      setRoleIds(editing.role_ids);
      setDeptIds(editing.department_ids);
    }
  }, [editing]);

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["org", "members"] });
  }

  const save = useMutation({
    mutationFn: (m: OrgMember) => {
      const body: {
        role_ids?: string[];
        department_ids?: string[];
        version: number;
      } = { version: m.version };
      if (!sameSet(roleIds, m.role_ids)) body.role_ids = roleIds;
      if (!sameSet(deptIds, m.department_ids)) body.department_ids = deptIds;
      return organizationApi.updateMember(m.id, body);
    },
    onSuccess: () => {
      setEditing(null);
      toast.show({ tone: "success", title: t("savedToast") });
      refresh();
    },
    onError: (e) => handleError(e),
  });

  const remove = useMutation({
    mutationFn: (m: OrgMember) => organizationApi.removeMember(m.id),
    onSuccess: () => {
      setRemoving(null);
      toast.show({ tone: "success", title: t("removedToast") });
      refresh();
    },
    onError: (e) => handleError(e),
  });

  const deactivate = useMutation({
    mutationFn: (m: OrgMember) => organizationApi.deactivateMember(m.id),
    onSuccess: () => {
      setDeactivating(null);
      toast.show({ tone: "success", title: tMember("deactivatedToast") });
      refresh();
    },
    onError: (e) => handleError(e, { closeDeactivate: true }),
  });

  const reactivate = useMutation({
    mutationFn: (m: OrgMember) => organizationApi.reactivateMember(m.id),
    onSuccess: () => {
      toast.show({ tone: "success", title: tMember("reactivatedToast") });
      refresh();
    },
    onError: (e) => handleError(e),
  });

  const preview = useQuery({
    queryKey: ["org", "members", previewing?.id, "permission-preview"],
    queryFn: () => organizationApi.previewMemberPermissions(previewing!.id),
    enabled: previewing !== null,
    retry: false,
  });

  function handleError(e: unknown, opts?: { closeDeactivate?: boolean }) {
    const reason =
      e instanceof ApiError && typeof e.details?.reason === "string"
        ? e.details.reason
        : undefined;
    if (reason === "version_conflict") {
      toast.show({ tone: "error", title: t("conflictToast"), description: t("conflictBody") });
      setEditing(null);
      refresh();
      return;
    }
    if (reason === "last_admin") {
      toast.show({ tone: "error", title: t("lastAdminToast"), description: t("lastAdminBody") });
      setRemoving(null);
      if (opts?.closeDeactivate) setDeactivating(null);
      return;
    }
    if (reason === "member_left") {
      toast.show({ tone: "error", title: tMember("memberLeftError") });
      if (opts?.closeDeactivate) setDeactivating(null);
      return;
    }
    toast.show({ tone: "error", title: getMessage(e) });
  }

  if (members.isError && members.error instanceof ApiError) {
    const err = members.error;
    const isAuth = err.isAuthError;
    return (
      <SectionCard
        title={t("title")}
        description={t("intro")}
        icon={UsersThree}
        iconGradient="icon-chip-primary"
      >
        <EmptyState
          kind={isAuth ? "auth" : err.isPermissionError ? "permission" : "error"}
          icon={ShieldWarning}
          title={
            isAuth
              ? tStates("authTitle")
              : err.isPermissionError
                ? tStates("permissionTitle")
                : tStates("errorTitle")
          }
          description={
            isAuth
              ? tStates("authBody")
              : err.isPermissionError
                ? tStates("permissionBody")
                : tStates("errorBody")
          }
          action={
            !isAuth && !err.isPermissionError ? (
              <Button variant="secondary" onClick={() => members.refetch()}>
                {tc("retry")}
              </Button>
            ) : undefined
          }
        />
      </SectionCard>
    );
  }

  const roles = rolesQuery.data ?? [];
  const depts = deptsQuery.data ?? [];
  const roleName = (id: string) => roles.find((r) => r.id === id)?.name ?? id.slice(0, 8);
  const deptName = (id: string) => depts.find((d) => d.id === id)?.name ?? id.slice(0, 8);
  const rows = members.data?.pages.flatMap((p) => p.data) ?? [];

  const columns: Column<OrgMember>[] = [
    {
      key: "member",
      header: t("member"),
      cell: (m) => (
        <div className="min-w-0">
          <p className="flex items-center gap-2 truncate font-semibold text-[var(--text-primary)]">
            {m.full_name || m.user_email}
            {m.user_email.toLowerCase() === currentEmail.toLowerCase() && (
              <StatusBadge tone="info">{t("you")}</StatusBadge>
            )}
          </p>
          <p className="truncate text-xs text-[var(--text-secondary)]">{m.user_email}</p>
        </div>
      ),
    },
    {
      key: "roles",
      header: t("roles"),
      cell: (m) =>
        m.role_ids.length ? (
          <div className="flex flex-wrap gap-1">
            {m.role_ids.map((id) => (
              <span
                key={id}
                className="rounded-md bg-[var(--bg-subtle)] px-2 py-0.5 text-xs font-medium text-[var(--text-secondary)]"
              >
                {roleName(id)}
              </span>
            ))}
          </div>
        ) : (
          <span className="text-[var(--text-muted)]">—</span>
        ),
    },
    {
      key: "departments",
      header: t("departments"),
      cell: (m) =>
        m.department_ids.length
          ? m.department_ids.map(deptName).join(", ")
          : "—",
    },
    {
      key: "status",
      header: t("status"),
      cell: (m) => (
        <StatusBadge tone={m.status === "suspended" ? "closed" : "active"}>
          {m.status === "suspended" ? tMember("inactiveBadge") : m.status_label}
        </StatusBadge>
      ),
    },
    {
      key: "actions",
      header: "",
      align: "right",
      cell: (m) => (
        <div className="flex flex-wrap justify-end gap-1">
          {canPreview && m.status !== "left" && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setPreviewing(m)}
              aria-label={tPreview("action")}
            >
              <Eye aria-hidden weight="duotone" className="size-4" />
              {tPreview("action")}
            </Button>
          )}
          {canManage && m.status !== "left" && (
            <Button variant="ghost" size="sm" onClick={() => setEditing(m)}>
              {tc("edit")}
            </Button>
          )}
          {canManage && m.status === "active" && (
            <Button variant="ghost" size="sm" onClick={() => setDeactivating(m)}>
              <PauseCircle aria-hidden weight="duotone" className="size-4" />
              {tMember("deactivate")}
            </Button>
          )}
          {canManage && m.status === "suspended" && (
            <Button
              variant="ghost"
              size="sm"
              loading={reactivate.isPending && reactivate.variables?.id === m.id}
              onClick={() => reactivate.mutate(m)}
            >
              <PlayCircle aria-hidden weight="duotone" className="size-4" />
              {tMember("reactivate")}
            </Button>
          )}
          {canRemove && m.status !== "left" && (
            <Button
              variant="ghost"
              size="sm"
              className="text-[var(--brand-red)]"
              onClick={() => setRemoving(m)}
            >
              {t("remove")}
            </Button>
          )}
        </div>
      ),
    },
  ];

  return (
    <SectionCard title={t("title")} description={t("intro")}>
      <DataTable
        columns={columns}
        rows={rows}
        getRowId={(m) => m.id}
        loading={members.isPending}
        caption={t("title")}
        empty={{ kind: "empty", icon: UsersThree, title: t("empty") }}
      />
      {members.hasNextPage && (
        <div className="mt-4 flex justify-center">
          <Button
            variant="secondary"
            loading={members.isFetchingNextPage}
            onClick={() => members.fetchNextPage()}
          >
            {tc("loadMore")}
          </Button>
        </div>
      )}

      {/* Edit roles/departments */}
      <Modal
        open={editing !== null}
        onClose={() => setEditing(null)}
        title={t("editTitle")}
        description={editing?.full_name || editing?.user_email}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setEditing(null)}>
              {tc("cancel")}
            </Button>
            <Button
              variant="primary"
              loading={save.isPending}
              onClick={() => editing && save.mutate(editing)}
            >
              {tc("save")}
            </Button>
          </>
        }
      >
        <div className="space-y-5">
          <CheckGroup
            legend={t("roles")}
            empty={t("noRoles")}
            options={roles.map((r) => ({
              id: r.id,
              label: r.name,
              disabled: !canAssignRole(r, effective, holdsWildcard),
            }))}
            selected={roleIds}
            onToggle={(id) =>
              setRoleIds((prev) =>
                prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
              )
            }
          />
          <CheckGroup
            legend={t("departments")}
            empty={t("noDepts")}
            options={depts.map((d) => ({ id: d.id, label: d.name }))}
            selected={deptIds}
            onToggle={(id) =>
              setDeptIds((prev) =>
                prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
              )
            }
          />
        </div>
      </Modal>

      {/* Remove */}
      <Modal
        open={removing !== null}
        onClose={() => setRemoving(null)}
        title={t("removeTitle")}
        description={t("removeBody", {
          name: removing?.full_name || removing?.user_email || "",
        })}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setRemoving(null)}>
              {tc("cancel")}
            </Button>
            <Button
              variant="danger"
              loading={remove.isPending}
              onClick={() => removing && remove.mutate(removing)}
            >
              {t("removeConfirm")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-[var(--text-secondary)]">{t("removeNote")}</p>
      </Modal>

      {/* Deactivate (reversible, distinct from remove) */}
      <Modal
        open={deactivating !== null}
        onClose={() => setDeactivating(null)}
        title={tMember("deactivateTitle")}
        description={tMember("deactivateBody", {
          name: deactivating?.full_name || deactivating?.user_email || "",
        })}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeactivating(null)}>
              {tc("cancel")}
            </Button>
            <Button
              variant="danger"
              loading={deactivate.isPending}
              onClick={() => deactivating && deactivate.mutate(deactivating)}
            >
              {tMember("deactivateConfirm")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-[var(--text-secondary)]">{t("removeNote")}</p>
      </Modal>

      {/* Permission preview */}
      <PermissionPreviewModal
        open={previewing !== null}
        onClose={() => setPreviewing(null)}
        title={tPreview("title", {
          name: previewing?.full_name || previewing?.user_email || "",
        })}
        preview={preview.data as PermissionPreview | undefined}
        loading={preview.isPending}
        error={preview.isError}
      />
    </SectionCard>
  );
}

function CheckGroup({
  legend,
  empty,
  options,
  selected,
  onToggle,
}: {
  legend: string;
  empty: string;
  options: { id: string; label: string; disabled?: boolean }[];
  selected: string[];
  onToggle: (id: string) => void;
}) {
  return (
    <fieldset>
      <legend className="mb-1.5 text-sm font-semibold text-[var(--text-primary)]">
        {legend}
      </legend>
      {options.length === 0 ? (
        <p className="text-sm text-[var(--text-muted)]">{empty}</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {options.map((o) => {
            const checked = selected.includes(o.id);
            return (
              <label
                key={o.id}
                className={
                  "inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors " +
                  (o.disabled
                    ? "cursor-not-allowed border-dashed border-[var(--border-default)] opacity-55"
                    : "cursor-pointer ") +
                  (checked && !o.disabled
                    ? "border-[var(--brand-primary)] bg-[var(--blue-50)] text-[var(--brand-primary)]"
                    : "border-[var(--border-default)] text-[var(--text-secondary)] hover:border-[var(--brand-primary)]")
                }
              >
                <input
                  type="checkbox"
                  className="size-3.5 rounded border-[var(--border-default)] text-[var(--brand-primary)] outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
                  checked={checked}
                  disabled={o.disabled}
                  onChange={() => onToggle(o.id)}
                />
                {o.label}
              </label>
            );
          })}
        </div>
      )}
    </fieldset>
  );
}
