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
  Select,
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
  type RoleAssignment,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { grants } from "@/lib/validation/organization";
import { PermissionPreviewModal } from "./permission-preview-panel";
import { useOrgScope, orgScopedKey } from "./org-scope";

function sameSet(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const right = new Set(b);
  return a.every((item) => right.has(item));
}

/**
 * Normalize a member's role assignments to `[{role_id, department_id}]`. Older
 * projections may omit `role_assignments`; fall back to `role_ids` treated as
 * org-wide (department_id null) so the editor always has a canonical shape.
 */
function memberAssignments(m: OrgMember): RoleAssignment[] {
  if (m.role_assignments && m.role_assignments.length > 0) {
    return m.role_assignments.map((a) => ({
      role_id: a.role_id,
      department_id: a.department_id ?? null,
    }));
  }
  return m.role_ids.map((id) => ({ role_id: id, department_id: null }));
}

/** Compare two assignment sets by (role_id, department_id) pairs, order-free. */
function sameAssignments(a: RoleAssignment[], b: RoleAssignment[]): boolean {
  if (a.length !== b.length) return false;
  const key = (x: RoleAssignment) => `${x.role_id}::${x.department_id ?? ""}`;
  const right = new Set(b.map(key));
  return a.every((x) => right.has(key(x)));
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
  const { orgId } = useOrgScope();

  const canManage = holdsWildcard || effective.has("members:update") || effective.has("members:*");
  const canRemove = holdsWildcard || effective.has("members:remove") || effective.has("members:*");
  const canPreview = holdsWildcard || effective.has("members:read") || effective.has("members:*");

  const [editing, setEditing] = useState<OrgMember | null>(null);
  const [removing, setRemoving] = useState<OrgMember | null>(null);
  const [deactivating, setDeactivating] = useState<OrgMember | null>(null);
  const [previewing, setPreviewing] = useState<OrgMember | null>(null);
  // Per-role assignments (role_id + optional department scope). Replaces the old
  // flat role-id list so each assigned role can be scoped to a department.
  const [assignments, setAssignments] = useState<RoleAssignment[]>([]);
  const [deptIds, setDeptIds] = useState<string[]>([]);

  const rolesQuery = useQuery({
    queryKey: orgScopedKey(["org", "roles"], orgId),
    queryFn: () => organizationApi.listRoles(orgId),
    retry: false,
  });
  const deptsQuery = useQuery({
    queryKey: orgScopedKey(["org", "departments"], orgId),
    queryFn: () => organizationApi.listDepartments(orgId),
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
    queryKey: orgScopedKey(["org", "members", "paginated"], orgId),
    queryFn: ({ pageParam }) => organizationApi.listMembers(pageParam, orgId),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.page.next_cursor ?? undefined,
    retry: false,
  });

  useEffect(() => {
    if (editing) {
      setAssignments(memberAssignments(editing));
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
        role_assignments?: RoleAssignment[];
        department_ids?: string[];
        version: number;
      } = { version: m.version };
      // Only send a role field when the assignment set actually changed. When
      // any assigned role carries a department scope, send the authoritative
      // `role_assignments`; otherwise keep the legacy org-wide `role_ids` path
      // (the two are mutually exclusive per the backend contract).
      if (!sameAssignments(assignments, memberAssignments(m))) {
        const anyScoped = assignments.some((a) => a.department_id != null);
        if (anyScoped) {
          body.role_assignments = assignments.map((a) => ({
            role_id: a.role_id,
            department_id: a.department_id ?? null,
          }));
        } else {
          body.role_ids = assignments.map((a) => a.role_id);
        }
      }
      if (!sameSet(deptIds, m.department_ids)) body.department_ids = deptIds;
      return organizationApi.updateMember(m.id, body, orgId);
    },
    onSuccess: () => {
      setEditing(null);
      toast.show({ tone: "success", title: t("savedToast") });
      refresh();
    },
    onError: (e) => handleError(e),
  });

  const remove = useMutation({
    mutationFn: (m: OrgMember) => organizationApi.removeMember(m.id, orgId),
    onSuccess: () => {
      setRemoving(null);
      toast.show({ tone: "success", title: t("removedToast") });
      refresh();
    },
    onError: (e) => handleError(e),
  });

  const deactivate = useMutation({
    mutationFn: (m: OrgMember) => organizationApi.deactivateMember(m.id, orgId),
    onSuccess: () => {
      setDeactivating(null);
      toast.show({ tone: "success", title: tMember("deactivatedToast") });
      refresh();
    },
    onError: (e) => handleError(e, { closeDeactivate: true }),
  });

  const reactivate = useMutation({
    mutationFn: (m: OrgMember) => organizationApi.reactivateMember(m.id, orgId),
    onSuccess: () => {
      toast.show({ tone: "success", title: tMember("reactivatedToast") });
      refresh();
    },
    onError: (e) => handleError(e),
  });

  const preview = useQuery({
    queryKey: orgScopedKey(
      ["org", "members", previewing?.id, "permission-preview"],
      orgId,
    ),
    queryFn: () => organizationApi.previewMemberPermissions(previewing!.id, orgId),
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
      cell: (m) => {
        const list = memberAssignments(m);
        return list.length ? (
          <div className="flex flex-wrap gap-1">
            {list.map((a) => (
              <span
                key={`${a.role_id}::${a.department_id ?? ""}`}
                className="inline-flex items-center gap-1 rounded-md bg-[var(--bg-subtle)] px-2 py-0.5 text-xs font-medium text-[var(--text-secondary)]"
              >
                {roleName(a.role_id)}
                {a.department_id && (
                  <span className="text-[var(--text-muted)]">
                    · {deptName(a.department_id)}
                  </span>
                )}
              </span>
            ))}
          </div>
        ) : (
          <span className="text-[var(--text-muted)]">—</span>
        );
      },
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
          <RoleScopeEditor
            legend={t("roles")}
            empty={t("noRoles")}
            hint={t("roleScopeHint")}
            orgWideLabel={t("orgWide")}
            scopeAriaLabel={(role) => t("roleScopeFor", { role })}
            roles={roles.map((r) => ({
              id: r.id,
              label: r.name,
              disabled: !canAssignRole(r, effective, holdsWildcard),
            }))}
            depts={depts.map((d) => ({ id: d.id, name: d.name }))}
            assignments={assignments}
            onToggle={(id) =>
              setAssignments((prev) =>
                prev.some((a) => a.role_id === id)
                  ? prev.filter((a) => a.role_id !== id)
                  : [...prev, { role_id: id, department_id: null }],
              )
            }
            onScope={(id, deptId) =>
              setAssignments((prev) =>
                prev.map((a) =>
                  a.role_id === id ? { ...a, department_id: deptId } : a,
                ),
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

/**
 * Role assignment editor with an optional per-role department scope. Each role
 * is a checkbox; once assigned, a department dropdown ("Org-wide" default)
 * appears next to it so the role can be scoped to a single department (or left
 * org-wide). Disabled roles exceed the actor's own permission ceiling.
 */
function RoleScopeEditor({
  legend,
  empty,
  hint,
  orgWideLabel,
  scopeAriaLabel,
  roles,
  depts,
  assignments,
  onToggle,
  onScope,
}: {
  legend: string;
  empty: string;
  hint: string;
  orgWideLabel: string;
  scopeAriaLabel: (role: string) => string;
  roles: { id: string; label: string; disabled?: boolean }[];
  depts: { id: string; name: string }[];
  assignments: RoleAssignment[];
  onToggle: (id: string) => void;
  onScope: (id: string, deptId: string | null) => void;
}) {
  const anyScoped = assignments.some((a) => a.department_id != null);
  return (
    <fieldset>
      <legend className="mb-1.5 text-sm font-semibold text-[var(--text-primary)]">
        {legend}
      </legend>
      {roles.length === 0 ? (
        <p className="text-sm text-[var(--text-muted)]">{empty}</p>
      ) : (
        <>
          <ul className="space-y-1.5">
            {roles.map((r) => {
              const assignment = assignments.find((a) => a.role_id === r.id);
              const checked = assignment !== undefined;
              return (
                <li
                  key={r.id}
                  className={
                    "flex flex-wrap items-center gap-2 rounded-lg border px-2.5 py-1.5 transition-colors " +
                    (checked
                      ? "border-[var(--brand-primary)]/40 bg-[var(--blue-50)]/40"
                      : "border-[var(--border-default)]")
                  }
                >
                  <label
                    className={
                      "inline-flex min-w-0 flex-1 items-center gap-2 text-sm font-medium " +
                      (r.disabled
                        ? "cursor-not-allowed opacity-55"
                        : "cursor-pointer")
                    }
                  >
                    <input
                      type="checkbox"
                      className="size-4 shrink-0 rounded border-[var(--border-default)] text-[var(--brand-primary)] outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
                      checked={checked}
                      disabled={r.disabled}
                      onChange={() => onToggle(r.id)}
                    />
                    <span
                      className={
                        "min-w-0 truncate " +
                        (checked
                          ? "text-[var(--text-primary)]"
                          : "text-[var(--text-secondary)]")
                      }
                    >
                      {r.label}
                    </span>
                  </label>
                  {checked && depts.length > 0 && (
                    <div className="w-full sm:w-48">
                      <Select
                        aria-label={scopeAriaLabel(r.label)}
                        value={assignment?.department_id ?? ""}
                        onChange={(e) => onScope(r.id, e.target.value || null)}
                        className="py-1.5 text-xs"
                        options={[
                          { value: "", label: orgWideLabel },
                          ...depts.map((d) => ({ value: d.id, label: d.name })),
                        ]}
                      />
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
          {anyScoped && (
            <p className="mt-1.5 text-xs text-[var(--text-muted)]">{hint}</p>
          )}
        </>
      )}
    </fieldset>
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
