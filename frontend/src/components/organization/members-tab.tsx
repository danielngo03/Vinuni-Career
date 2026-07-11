"use client";

import * as React from "react";
import { useTranslations } from "next-intl";
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { PauseCircle, PlayCircle, Trash2, Check } from "lucide-react";
import { Button, EmptyState, useToast } from "@/components/ui";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
  DataTable,
  type ColumnDef,
  DetailSheet,
  DetailSheetSection,
  StatusChip,
  type ChipTone,
} from "@/components/kit";
import {
  ApiError,
  organizationApi,
  type OrgRole,
  type OrgMember,
  type PermissionPreview,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { grants } from "@/lib/validation/organization";
import { PermissionPreviewBody } from "./permission-preview-panel";

function sameSet(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const right = new Set(b);
  return a.every((item) => right.has(item));
}

function canAssignRole(role: OrgRole, effective: ReadonlySet<string>, holdsWildcard: boolean): boolean {
  if (holdsWildcard) return true;
  return role.permissions.every((perm) => {
    if (perm === "*:*") return false;
    const [resource, action] = perm.split(":", 2);
    return Boolean(resource && action && grants(effective, resource, action));
  });
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase();
  return (parts[0]![0]! + parts[parts.length - 1]![0]!).toUpperCase();
}

const STATUS_TONE: Record<string, ChipTone> = {
  active: "success",
  suspended: "warning",
  left: "neutral",
};

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

  const [selected, setSelected] = React.useState<OrgMember | null>(null);
  const [roleIds, setRoleIds] = React.useState<string[]>([]);
  const [deptIds, setDeptIds] = React.useState<string[]>([]);
  const [confirmRemove, setConfirmRemove] = React.useState(false);

  const rolesQuery = useQuery({ queryKey: ["org", "roles"], queryFn: () => organizationApi.listRoles(), retry: false });
  const deptsQuery = useQuery({
    queryKey: ["org", "departments"],
    queryFn: () => organizationApi.listDepartments(),
    retry: false,
  });

  // Distinct key from the plain ["org","members"] queries used elsewhere to
  // avoid a react-query cache-shape collision (useQuery vs useInfiniteQuery).
  const members = useInfiniteQuery({
    queryKey: ["org", "members", "paginated"],
    queryFn: ({ pageParam }) => organizationApi.listMembers(pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.page.next_cursor ?? undefined,
    retry: false,
  });

  // Sync edit buffers when the selected member changes.
  React.useEffect(() => {
    if (selected) {
      setRoleIds(selected.role_ids);
      setDeptIds(selected.department_ids);
      setConfirmRemove(false);
    }
  }, [selected]);

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["org", "members"] });
  }
  function closeSheet() {
    setSelected(null);
  }

  const save = useMutation({
    mutationFn: (m: OrgMember) => {
      const body: { role_ids?: string[]; department_ids?: string[]; version: number } = { version: m.version };
      if (!sameSet(roleIds, m.role_ids)) body.role_ids = roleIds;
      if (!sameSet(deptIds, m.department_ids)) body.department_ids = deptIds;
      return organizationApi.updateMember(m.id, body);
    },
    onSuccess: () => {
      closeSheet();
      toast.show({ tone: "success", title: t("savedToast") });
      refresh();
    },
    onError: (e) => handleError(e),
  });

  const remove = useMutation({
    mutationFn: (m: OrgMember) => organizationApi.removeMember(m.id),
    onSuccess: () => {
      closeSheet();
      toast.show({ tone: "success", title: t("removedToast") });
      refresh();
    },
    onError: (e) => handleError(e),
  });

  const deactivate = useMutation({
    mutationFn: (m: OrgMember) => organizationApi.deactivateMember(m.id),
    onSuccess: (updated) => {
      setSelected(updated);
      toast.show({ tone: "success", title: tMember("deactivatedToast") });
      refresh();
    },
    onError: (e) => handleError(e),
  });

  const reactivate = useMutation({
    mutationFn: (m: OrgMember) => organizationApi.reactivateMember(m.id),
    onSuccess: (updated) => {
      setSelected(updated);
      toast.show({ tone: "success", title: tMember("reactivatedToast") });
      refresh();
    },
    onError: (e) => handleError(e),
  });

  const preview = useQuery({
    queryKey: ["org", "members", selected?.id, "permission-preview"],
    queryFn: () => organizationApi.previewMemberPermissions(selected!.id),
    enabled: selected !== null && canPreview,
    retry: false,
  });

  function handleError(e: unknown) {
    const reason = e instanceof ApiError && typeof e.details?.reason === "string" ? e.details.reason : undefined;
    if (reason === "version_conflict") {
      toast.show({ tone: "error", title: t("conflictToast"), description: t("conflictBody") });
      closeSheet();
      refresh();
      return;
    }
    if (reason === "last_admin") {
      toast.show({ tone: "error", title: t("lastAdminToast"), description: t("lastAdminBody") });
      setConfirmRemove(false);
      return;
    }
    if (reason === "member_left") {
      toast.show({ tone: "error", title: tMember("memberLeftError") });
      return;
    }
    toast.show({ tone: "error", title: getMessage(e) });
  }

  if (members.isError && members.error instanceof ApiError) {
    const err = members.error;
    const isAuth = err.isAuthError;
    return (
      <Card>
        <CardHeader>
          <div>
            <CardTitle>{t("title")}</CardTitle>
            <CardDescription>{t("intro")}</CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          <EmptyState
            kind={isAuth ? "auth" : err.isPermissionError ? "permission" : "error"}
            title={isAuth ? tStates("authTitle") : err.isPermissionError ? tStates("permissionTitle") : tStates("errorTitle")}
            description={isAuth ? tStates("authBody") : err.isPermissionError ? tStates("permissionBody") : tStates("errorBody")}
            action={
              !isAuth && !err.isPermissionError ? (
                <Button variant="secondary" onClick={() => members.refetch()}>
                  {tc("retry")}
                </Button>
              ) : undefined
            }
          />
        </CardContent>
      </Card>
    );
  }

  const roles = rolesQuery.data ?? [];
  const depts = deptsQuery.data ?? [];
  const roleName = (id: string) => roles.find((r) => r.id === id)?.name ?? id.slice(0, 8);
  const deptName = (id: string) => depts.find((d) => d.id === id)?.name ?? id.slice(0, 8);
  const rows = members.data?.pages.flatMap((p) => p.data) ?? [];

  const columns: ColumnDef<OrgMember, unknown>[] = [
    {
      accessorKey: "full_name",
      header: t("member"),
      cell: ({ row }) => {
        const m = row.original;
        const name = m.full_name || m.user_email;
        const isYou = m.user_email.toLowerCase() === currentEmail.toLowerCase();
        return (
          <div className="flex items-center gap-3">
            <Avatar size="sm" className="size-8">
              <AvatarFallback className="bg-[var(--viz-indigo-soft)] text-[0.6875rem] font-semibold text-[var(--viz-indigo)]">
                {initials(name)}
              </AvatarFallback>
            </Avatar>
            <div className="min-w-0">
              <p className="flex items-center gap-1.5 truncate font-semibold text-foreground">
                {name}
                {isYou && (
                  <StatusChip tone="info" size="sm">
                    {t("you")}
                  </StatusChip>
                )}
              </p>
              <p className="truncate type-caption text-muted-foreground">{m.user_email}</p>
            </div>
          </div>
        );
      },
    },
    {
      accessorKey: "role_ids",
      header: t("roles"),
      enableSorting: false,
      cell: ({ row }) =>
        row.original.role_ids.length ? (
          <div className="flex flex-wrap gap-1">
            {row.original.role_ids.map((id) => (
              <StatusChip key={id} tone="neutral" size="sm">
                {roleName(id)}
              </StatusChip>
            ))}
          </div>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      accessorKey: "department_ids",
      header: t("departments"),
      enableSorting: false,
      cell: ({ row }) =>
        row.original.department_ids.length ? (
          <span className="text-[0.8125rem]">{row.original.department_ids.map(deptName).join(", ")}</span>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      accessorKey: "status",
      header: t("status"),
      cell: ({ row }) => (
        <StatusChip tone={STATUS_TONE[row.original.status] ?? "neutral"} dot>
          {row.original.status === "suspended" ? tMember("inactiveBadge") : row.original.status_label}
        </StatusChip>
      ),
    },
  ];

  const changed = selected ? !sameSet(roleIds, selected.role_ids) || !sameSet(deptIds, selected.department_ids) : false;
  const busy = save.isPending || remove.isPending || deactivate.isPending || reactivate.isPending;

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{t("title")}</CardTitle>
          <CardDescription>{t("intro")}</CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        <DataTable
          columns={columns}
          data={rows}
          getRowId={(m) => m.id}
          loading={members.isPending}
          onRowClick={(m) => setSelected(m)}
          activeRowId={selected?.id}
          empty={<EmptyState kind="empty" title={t("empty")} />}
        />
        {members.hasNextPage && (
          <div className="mt-4 flex justify-center">
            <Button variant="secondary" loading={members.isFetchingNextPage} onClick={() => members.fetchNextPage()}>
              {tc("loadMore")}
            </Button>
          </div>
        )}
      </CardContent>

      {/* Member detail / edit drawer */}
      <DetailSheet
        open={selected !== null}
        onClose={closeSheet}
        title={selected?.full_name || selected?.user_email || ""}
        subtitle={selected?.user_email}
        closeLabel={tc("close")}
        avatar={
          <Avatar size="lg" className="size-10">
            <AvatarFallback className="bg-[var(--viz-indigo-soft)] text-sm font-semibold text-[var(--viz-indigo)]">
              {initials(selected?.full_name || selected?.user_email || "?")}
            </AvatarFallback>
          </Avatar>
        }
        status={
          selected ? (
            <StatusChip tone={STATUS_TONE[selected.status] ?? "neutral"} dot>
              {selected.status === "suspended" ? tMember("inactiveBadge") : selected.status_label}
            </StatusChip>
          ) : undefined
        }
        footer={
          selected && selected.status !== "left" ? (
            confirmRemove ? (
              <>
                <span className="mr-auto type-small text-muted-foreground">{t("removeBody", { name: selected.full_name || selected.user_email })}</span>
                <Button variant="ghost" onClick={() => setConfirmRemove(false)} disabled={busy}>
                  {tc("cancel")}
                </Button>
                <Button variant="danger" loading={remove.isPending} onClick={() => remove.mutate(selected)}>
                  {t("removeConfirm")}
                </Button>
              </>
            ) : (
              <>
                {canManage && selected.status === "active" && (
                  <Button
                    variant="ghost"
                    onClick={() => deactivate.mutate(selected)}
                    loading={deactivate.isPending}
                  >
                    <PauseCircle className="size-4" strokeWidth={1.8} />
                    {tMember("deactivate")}
                  </Button>
                )}
                {canManage && selected.status === "suspended" && (
                  <Button
                    variant="ghost"
                    onClick={() => reactivate.mutate(selected)}
                    loading={reactivate.isPending}
                  >
                    <PlayCircle className="size-4" strokeWidth={1.8} />
                    {tMember("reactivate")}
                  </Button>
                )}
                {canRemove && (
                  <Button variant="ghost" className="text-[var(--content-danger)]" onClick={() => setConfirmRemove(true)}>
                    <Trash2 className="size-4" strokeWidth={1.8} />
                    {t("remove")}
                  </Button>
                )}
                {canManage && changed && (
                  <Button variant="primary" loading={save.isPending} onClick={() => save.mutate(selected)}>
                    <Check className="size-4" strokeWidth={2} />
                    {tc("save")}
                  </Button>
                )}
              </>
            )
          ) : undefined
        }
      >
        {selected && (
          <>
            <DetailSheetSection title={t("roles")}>
              {roles.length === 0 ? (
                <p className="type-small text-muted-foreground">{t("noRoles")}</p>
              ) : canManage && selected.status !== "left" ? (
                <ChipToggleGroup
                  options={roles.map((r) => ({
                    id: r.id,
                    label: r.name,
                    disabled: !canAssignRole(r, effective, holdsWildcard),
                  }))}
                  selected={roleIds}
                  onToggle={(id) => setRoleIds((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]))}
                />
              ) : (
                <ReadonlyChips ids={selected.role_ids} label={roleName} empty="—" />
              )}
            </DetailSheetSection>

            <DetailSheetSection title={t("departments")}>
              {depts.length === 0 ? (
                <p className="type-small text-muted-foreground">{t("noDepts")}</p>
              ) : canManage && selected.status !== "left" ? (
                <ChipToggleGroup
                  options={depts.map((d) => ({ id: d.id, label: d.name }))}
                  selected={deptIds}
                  onToggle={(id) => setDeptIds((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]))}
                />
              ) : (
                <ReadonlyChips ids={selected.department_ids} label={deptName} empty="—" />
              )}
            </DetailSheetSection>

            {canPreview && (
              <DetailSheetSection title={tPreview("action")}>
                <PermissionPreviewBody
                  preview={preview.data as PermissionPreview | undefined}
                  loading={preview.isPending}
                  error={preview.isError}
                />
              </DetailSheetSection>
            )}
          </>
        )}
      </DetailSheet>
    </Card>
  );
}

function ReadonlyChips({
  ids,
  label,
  empty,
}: {
  ids: string[];
  label: (id: string) => string;
  empty: string;
}) {
  if (ids.length === 0) return <p className="type-small text-muted-foreground">{empty}</p>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {ids.map((id) => (
        <StatusChip key={id} tone="neutral" size="sm">
          {label(id)}
        </StatusChip>
      ))}
    </div>
  );
}

function ChipToggleGroup({
  options,
  selected,
  onToggle,
}: {
  options: { id: string; label: string; disabled?: boolean }[];
  selected: string[];
  onToggle: (id: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((o) => {
        const checked = selected.includes(o.id);
        return (
          <label
            key={o.id}
            className={
              "inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors " +
              (o.disabled
                ? "cursor-not-allowed border-dashed border-border opacity-55"
                : "cursor-pointer ") +
              (checked && !o.disabled
                ? "border-[var(--brand-primary)] bg-[var(--content-info-soft)] text-[var(--brand-primary)]"
                : "border-border text-muted-foreground hover:border-border-strong")
            }
          >
            <input
              type="checkbox"
              className="size-3.5 rounded border-border text-[var(--brand-primary)] outline-none focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
              checked={checked}
              disabled={o.disabled}
              onChange={() => onToggle(o.id)}
            />
            {o.label}
          </label>
        );
      })}
    </div>
  );
}
