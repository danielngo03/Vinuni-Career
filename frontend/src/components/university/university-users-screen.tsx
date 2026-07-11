"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Ban,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  RotateCcw,
  ShieldCheck,
  UserCog,
  Users,
} from "lucide-react";
import { Button, useToast, SegmentedControl } from "@/components/ui";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { PageHeader } from "@/components/layout/page-header";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  DataTable,
  type ColumnDef,
  DetailSheet,
  DetailSheetSection,
  DetailRow,
  EmptyState,
  FilterBar,
  KpiRow,
  KpiTile,
  StatusChip,
  type ChipTone,
} from "@/components/kit";
import { ApiError, adminUsersApi } from "@/lib/api";
import type { AdminUserRow } from "@/lib/api/admin-users";
import { formatDateTime } from "@/lib/format";

const PAGE_SIZE = 30;

const PERSONA_CHIP: Record<string, ChipTone> = {
  student: "indigo",
  partner_member: "violet",
  university_staff: "teal",
};

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase();
  return (parts[0]![0]! + parts[parts.length - 1]![0]!).toUpperCase();
}

export function UniversityUsersScreen() {
  const t = useTranslations("universityUsers");
  const tc = useTranslations("common");
  const tStates = useTranslations("states");
  const locale = useLocale();
  const toast = useToast();
  const qc = useQueryClient();

  const [persona, setPersona] = React.useState<string>("");
  const [q, setQ] = React.useState("");
  const [debouncedQ, setDebouncedQ] = React.useState("");
  const [page, setPage] = React.useState(1);
  const [selected, setSelected] = React.useState<AdminUserRow | null>(null);

  // Debounce the search box; reset to page 1 on new term.
  React.useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQ(q);
      setPage(1);
    }, 400);
    return () => clearTimeout(timer);
  }, [q]);

  const query = useQuery({
    queryKey: ["admin", "users", { persona, q: debouncedQ, page }] as const,
    queryFn: () =>
      adminUsersApi.listUsers({
        persona: persona || undefined,
        q: debouncedQ || undefined,
        page,
        page_size: PAGE_SIZE,
      }),
    staleTime: 30_000,
    retry: false,
  });

  const suspendMut = useMutation({
    mutationFn: (userId: string) => adminUsersApi.suspendUser(userId),
    onSuccess: (updated) => {
      void qc.invalidateQueries({ queryKey: ["admin", "users"] });
      setSelected((cur) => (cur && cur.id === updated.id ? { ...cur, is_active: updated.is_active } : cur));
      toast.show({ tone: "success", title: t("suspendSuccess") });
    },
    onError: () => toast.show({ tone: "error", title: t("suspendError") }),
  });

  const unsuspendMut = useMutation({
    mutationFn: (userId: string) => adminUsersApi.unsuspendUser(userId),
    onSuccess: (updated) => {
      void qc.invalidateQueries({ queryKey: ["admin", "users"] });
      setSelected((cur) => (cur && cur.id === updated.id ? { ...cur, is_active: updated.is_active } : cur));
      toast.show({ tone: "success", title: t("unsuspendSuccess") });
    },
    onError: () => toast.show({ tone: "error", title: t("unsuspendError") }),
  });

  const personaLabel = React.useCallback(
    (p: string) =>
      p === "student"
        ? t("personaStudent")
        : p === "partner_member"
          ? t("personaPartner")
          : p === "university_staff"
            ? t("personaStaff")
            : p,
    [t],
  );

  const data = query.data;
  const items = data?.items ?? [];
  const totalPages = data?.total_pages ?? 1;
  const total = data?.total ?? 0;
  const busy = suspendMut.isPending || unsuspendMut.isPending;

  const pageActive = items.filter((u) => u.is_active).length;
  const pageSuspended = items.filter((u) => !u.is_active).length;
  const pageUnverified = items.filter((u) => !u.email_verified).length;

  const columns: ColumnDef<AdminUserRow, unknown>[] = [
    {
      accessorKey: "full_name",
      header: t("colUser"),
      cell: ({ row }) => {
        const u = row.original;
        const name = u.full_name || u.email;
        return (
          <div className="flex min-w-0 items-center gap-3">
            <Avatar size="sm" className="size-8">
              <AvatarFallback className="bg-[var(--viz-indigo-soft)] text-[0.6875rem] font-semibold text-[var(--viz-indigo)]">
                {initials(name)}
              </AvatarFallback>
            </Avatar>
            <div className="min-w-0">
              <p className="truncate font-semibold text-foreground">{name}</p>
              <p className="truncate type-caption text-muted-foreground">{u.email}</p>
            </div>
          </div>
        );
      },
    },
    {
      accessorKey: "persona",
      header: t("colPersona"),
      cell: ({ row }) => (
        <StatusChip tone={PERSONA_CHIP[row.original.persona] ?? "neutral"}>
          {personaLabel(row.original.persona)}
        </StatusChip>
      ),
    },
    {
      accessorKey: "is_active",
      header: t("colStatus"),
      cell: ({ row }) => {
        const u = row.original;
        return (
          <div className="flex flex-wrap items-center gap-1.5">
            <StatusChip tone={u.is_active ? "success" : "danger"} dot>
              {u.is_active ? t("active") : t("suspended")}
            </StatusChip>
            {u.email_verified && (
              <StatusChip tone="neutral" size="sm">
                <ShieldCheck className="size-3" strokeWidth={2} />
                {t("verified")}
              </StatusChip>
            )}
          </div>
        );
      },
    },
    {
      accessorKey: "created_at",
      header: t("colJoined"),
      cell: ({ row }) => (
        <span className="whitespace-nowrap type-small text-muted-foreground">
          {row.original.created_at ? formatDateTime(row.original.created_at, locale) : "—"}
        </span>
      ),
    },
  ];

  const header = <PageHeader title={t("title")} subtitle={t("subtitle")} />;

  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    if (err.isPermissionError || err.isAuthError) {
      return (
        <>
          {header}
          <EmptyState
            kind={err.isPermissionError ? "permission" : "auth"}
            title={err.isPermissionError ? tStates("permissionTitle") : tStates("authTitle")}
            description={err.isPermissionError ? tStates("permissionBody") : tStates("authBody")}
          />
        </>
      );
    }
  }

  const isHardError =
    query.isError &&
    !(query.error instanceof ApiError && (query.error.isPermissionError || query.error.isAuthError));

  return (
    <>
      {header}

      <div className="space-y-4">
        <KpiRow cols={4}>
          <KpiTile label={t("kpiTotal")} value={query.isPending ? "—" : String(total)} icon={Users} />
          <KpiTile
            label={t("kpiActive")}
            value={query.isPending ? "—" : String(pageActive)}
            icon={CheckCircle2}
            hint={t("kpiPageHint")}
          />
          <KpiTile
            label={t("kpiSuspended")}
            value={query.isPending ? "—" : String(pageSuspended)}
            icon={Ban}
            hint={t("kpiPageHint")}
          />
          <KpiTile
            label={t("kpiUnverified")}
            value={query.isPending ? "—" : String(pageUnverified)}
            icon={UserCog}
            hint={t("kpiPageHint")}
          />
        </KpiRow>

        <Card>
          <CardHeader>
            <div>
              <CardTitle>{t("title")}</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <FilterBar search={{ value: q, onChange: setQ, placeholder: t("searchPlaceholder") }}>
              <SegmentedControl
                ariaLabel={t("personaFilter")}
                value={persona}
                onValueChange={(v) => {
                  setPersona(v);
                  setPage(1);
                }}
                size="sm"
                options={[
                  { value: "", label: t("allPersonas") },
                  { value: "student", label: t("personaStudent") },
                  { value: "partner_member", label: t("personaPartner") },
                  { value: "university_staff", label: t("personaStaff") },
                ]}
              />
            </FilterBar>

            {isHardError ? (
              <EmptyState
                kind="error"
                title={tStates("errorTitle")}
                description={tStates("errorBody")}
                action={
                  <Button variant="secondary" onClick={() => void query.refetch()}>
                    {tc("retry")}
                  </Button>
                }
              />
            ) : (
              <>
                <DataTable
                  columns={columns}
                  data={items}
                  getRowId={(u) => u.id}
                  loading={query.isPending}
                  onRowClick={(u) => setSelected(u)}
                  activeRowId={selected?.id}
                  empty={<EmptyState kind="empty" title={t("emptyTitle")} description={t("emptyBody")} />}
                />

                {totalPages > 1 && (
                  <div className="flex items-center justify-center gap-3">
                    <button
                      type="button"
                      disabled={page <= 1}
                      onClick={() => setPage((p) => p - 1)}
                      aria-label={tc("tablePrev")}
                      className="inline-flex size-8 items-center justify-center rounded-lg border border-border text-muted-foreground outline-none transition-colors hover:bg-[var(--bg-subtle)] hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40 focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
                    >
                      <ChevronLeft className="size-4" strokeWidth={1.8} />
                    </button>
                    <span className="type-small tabular-nums text-muted-foreground">
                      {t("pageOf", { page, totalPages })}
                    </span>
                    <button
                      type="button"
                      disabled={page >= totalPages}
                      onClick={() => setPage((p) => p + 1)}
                      aria-label={tc("tableNext")}
                      className="inline-flex size-8 items-center justify-center rounded-lg border border-border text-muted-foreground outline-none transition-colors hover:bg-[var(--bg-subtle)] hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40 focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
                    >
                      <ChevronRight className="size-4" strokeWidth={1.8} />
                    </button>
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* User detail drawer */}
      <DetailSheet
        open={selected !== null}
        onClose={() => setSelected(null)}
        title={selected?.full_name || selected?.email || ""}
        subtitle={selected?.full_name ? selected.email : undefined}
        closeLabel={tc("close")}
        avatar={
          <Avatar size="lg" className="size-10">
            <AvatarFallback className="bg-[var(--viz-indigo-soft)] text-sm font-semibold text-[var(--viz-indigo)]">
              {initials(selected?.full_name || selected?.email || "?")}
            </AvatarFallback>
          </Avatar>
        }
        status={
          selected ? (
            <>
              <StatusChip tone={selected.is_active ? "success" : "danger"} dot>
                {selected.is_active ? t("active") : t("suspended")}
              </StatusChip>
              <StatusChip tone={PERSONA_CHIP[selected.persona] ?? "neutral"}>
                {personaLabel(selected.persona)}
              </StatusChip>
            </>
          ) : undefined
        }
        footer={
          selected ? (
            selected.is_active ? (
              <Button
                variant="ghost"
                size="sm"
                className="text-[var(--content-danger)]"
                loading={suspendMut.isPending}
                disabled={busy}
                onClick={() => suspendMut.mutate(selected.id)}
              >
                <Ban className="size-4" strokeWidth={1.8} />
                {t("suspend")}
              </Button>
            ) : (
              <Button
                variant="primary"
                size="sm"
                loading={unsuspendMut.isPending}
                disabled={busy}
                onClick={() => unsuspendMut.mutate(selected.id)}
              >
                <RotateCcw className="size-4" strokeWidth={1.8} />
                {t("unsuspend")}
              </Button>
            )
          ) : undefined
        }
      >
        {selected && (
          <DetailSheetSection title={t("detailTitle")}>
            <dl className="space-y-0.5">
              <DetailRow label={t("labelEmail")}>{selected.email}</DetailRow>
              <DetailRow label={t("labelPersona")}>{personaLabel(selected.persona)}</DetailRow>
              <DetailRow label={t("labelOrg")}>{selected.org_id ?? t("noOrg")}</DetailRow>
              <DetailRow label={t("labelJoined")}>
                {selected.created_at ? formatDateTime(selected.created_at, locale) : "—"}
              </DetailRow>
              <DetailRow label={t("labelVerified")}>{selected.email_verified ? t("yes") : t("no")}</DetailRow>
            </dl>
          </DetailSheetSection>
        )}
      </DetailSheet>
    </>
  );
}
