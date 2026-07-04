"use client";

import { useState, useCallback } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle,
  LightbulbFilament,
  MagnifyingGlass,
  ProhibitInset,
  ShieldWarning,
  SignIn,
  Sparkle,
  Student,
  UserCircle,
  UserGear,
  WarningCircle,
  XCircle,
} from "@phosphor-icons/react";
import {
  Button,
  EmptyState,
  Input,
  Skeleton,
  useToast,
} from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { ApiError, adminUsersApi } from "@/lib/api";
import type { AdminUserRow } from "@/lib/api/admin-users";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 30;

const PERSONA_ICONS: Record<string, React.ElementType> = {
  student: Student,
  partner_member: UserGear,
  university_staff: UserCircle,
};

export function UniversityUsersScreen() {
  const t = useTranslations("universityUsers");
  const tc = useTranslations("common");
  const tStates = useTranslations("states");
  const toast = useToast();
  const qc = useQueryClient();

  const [persona, setPersona] = useState<string>("");
  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [page, setPage] = useState(1);

  const handleSearchChange = useCallback(
    (val: string) => {
      setQ(val);
      const timer = setTimeout(() => {
        setDebouncedQ(val);
        setPage(1);
      }, 400);
      return () => clearTimeout(timer);
    },
    []
  );

  const queryKey = ["admin", "users", { persona, q: debouncedQ, page }] as const;

  const query = useQuery({
    queryKey,
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
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["admin", "users"] });
      toast.show({ tone: "success", title: t("suspendSuccess") });
    },
    onError: () => toast.show({ tone: "error", title: t("suspendError") }),
  });

  const unsuspendMut = useMutation({
    mutationFn: (userId: string) => adminUsersApi.unsuspendUser(userId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["admin", "users"] });
      toast.show({ tone: "success", title: t("unsuspendSuccess") });
    },
    onError: () => toast.show({ tone: "error", title: t("unsuspendError") }),
  });

  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    if (err.isPermissionError || err.isAuthError) {
      return (
        <>
          <PageHeader title={t("title")} description={t("subtitle")} />
          <EmptyState
            kind={err.isPermissionError ? "permission" : "auth"}
            icon={err.isPermissionError ? ShieldWarning : SignIn}
            title={err.isPermissionError ? tStates("permissionTitle") : tStates("authTitle")}
            description={err.isPermissionError ? tStates("permissionBody") : tStates("authBody")}
          />
        </>
      );
    }
    return (
      <>
        <PageHeader title={t("title")} description={t("subtitle")} />
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={tStates("errorTitle")}
          description={tStates("errorBody")}
          action={
            <Button variant="secondary" onClick={() => void query.refetch()}>
              {tc("retry")}
            </Button>
          }
        />
      </>
    );
  }

  const data = query.data;
  const items = data?.items ?? [];
  const totalPages = data?.total_pages ?? 1;
  const total = data?.total ?? 0;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={t("title")} description={t("subtitle")} />

      {/* ── Filters ── */}
      <div className="rounded-2xl border border-[var(--border-default)] bg-white p-4 shadow-[0_2px_12px_rgba(11,34,57,0.05)] ">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-48">
            <MagnifyingGlass
              aria-hidden
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 size-4 text-[var(--text-muted)]"
            />
            <Input
              value={q}
              onChange={(e) => handleSearchChange(e.target.value)}
              placeholder={t("searchPlaceholder")}
              className="pl-9"
              aria-label={t("searchPlaceholder")}
            />
          </div>
          {[
            { value: "", label: t("allPersonas"), active: "border-[var(--brand-primary)]/30 bg-[var(--brand-primary)] text-white shadow-sm shadow-[var(--brand-primary)]/20" },
            { value: "student", label: t("personaStudent"), active: "border-teal-500/30 bg-teal-600 text-white shadow-sm" },
            { value: "partner_member", label: t("personaPartner"), active: "border-violet-500/30 bg-violet-600 text-white shadow-sm" },
            { value: "university_staff", label: t("personaStaff"), active: "border-[var(--amber-500)]/30 bg-[var(--amber-600)] text-white shadow-sm" },
          ].map(({ value, label, active }) => (
            <button
              key={value}
              onClick={() => { setPersona(value); setPage(1); }}
              aria-pressed={persona === value}
              className={cn(
                "inline-flex items-center rounded-full border px-3.5 py-1.5 text-xs font-semibold transition-all focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-primary)]",
                persona === value
                  ? active
                  : "border-[var(--border-default)] bg-white text-[var(--text-secondary)] hover:bg-white hover:text-[var(--text-primary)]",
              )}
            >
              {label}
            </button>
          ))}
          {!query.isPending && (
            <span className="ml-auto shrink-0 rounded-full bg-[var(--brand-primary)]/10 px-3 py-1 text-xs font-semibold text-[var(--brand-primary)]">
              {t("totalCount", { count: total })}
            </span>
          )}
        </div>
      </div>

      {/* ── AI Platform Overview panel ── */}
      {!query.isPending && items.length > 0 && (() => {
        const suspendedCount = items.filter((u) => !u.is_active).length;
        const unverifiedCount = items.filter((u) => !u.email_verified).length;
        const insights: string[] = [];
        insights.push(t("aiInsightTotal", { count: total }));
        if (suspendedCount > 0) insights.push(t("aiInsightSuspended", { count: suspendedCount }));
        if (unverifiedCount > 0) insights.push(t("aiInsightUnverified", { count: unverifiedCount }));
        if (suspendedCount === 0 && unverifiedCount === 0) insights.push(t("aiInsightAllClear"));
        return (
          <div className={cn(
            "rounded-2xl border p-4",
            "border-[var(--ai-accent)]/25 bg-gradient-to-br from-[var(--ai-accent-soft)] to-white/60 ",
          )}>
            <p className="mb-2.5 flex items-center gap-2 text-sm font-bold text-[var(--text-primary)]">
              <span className="flex size-6 shrink-0 items-center justify-center rounded-lg icon-chip-info shadow-sm">
                <Sparkle aria-hidden weight="duotone" className="size-3.5 text-white" />
              </span>
              {t("aiInsightsTitle")}
            </p>
            <ul className="space-y-1.5">
              {insights.map((text, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-[var(--text-secondary)]">
                  <LightbulbFilament aria-hidden weight="duotone" className="mt-px size-3.5 shrink-0 text-[var(--ai-accent)]" />
                  {text}
                </li>
              ))}
            </ul>
          </div>
        );
      })()}

      {/* ── User list ── */}
      <div className="flex flex-col gap-2">
        {query.isPending
          ? Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-16 w-full rounded-xl" />
            ))
          : items.length === 0
            ? (
              <EmptyState
                kind="empty"
                icon={UserCircle}
                title={t("emptyTitle")}
                description={t("emptyBody")}
              />
            )
            : items.map((user) => (
              <UserRow
                key={user.id}
                user={user}
                onSuspend={() => suspendMut.mutate(user.id)}
                onUnsuspend={() => unsuspendMut.mutate(user.id)}
                busy={suspendMut.isPending || unsuspendMut.isPending}
                t={t}
              />
            ))}
      </div>

      {/* ── Pagination ── */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 pt-2">
          <Button
            variant="secondary"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            {tc("previous")}
          </Button>
          <span className="text-xs text-[var(--text-muted)]">
            {t("pageOf", { page, totalPages })}
          </span>
          <Button
            variant="secondary"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            {tc("next")}
          </Button>
        </div>
      )}
    </div>
  );
}

/* ─── User row ──────────────────────────────────────────────────────────── */

function UserRow({
  user,
  onSuspend,
  onUnsuspend,
  busy,
  t,
}: {
  user: AdminUserRow;
  onSuspend: () => void;
  onUnsuspend: () => void;
  busy: boolean;
  t: ReturnType<typeof useTranslations>;
}) {
  const PersonaIcon = PERSONA_ICONS[user.persona] ?? UserCircle;

  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-xl border px-4 py-3 transition-all",
        user.is_active
          ? "border-[var(--border-default)] bg-white"
          : "border-red-200/60 bg-red-50/40"
      )}
    >
      <PersonaIcon
        aria-hidden
        weight="duotone"
        className={cn(
          "size-9 shrink-0 rounded-full p-1.5",
          user.is_active
            ? "bg-[var(--brand-primary)]/10 text-[var(--brand-primary)]"
            : "bg-red-100 text-red-400"
        )}
      />

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="truncate font-semibold text-sm text-[var(--text-primary)]">
            {user.full_name || user.email}
          </span>
          {user.full_name && (
            <span className="truncate text-xs text-[var(--text-muted)]">
              {user.email}
            </span>
          )}
          {/* Active / Suspended badge */}
          {user.is_active ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-green-100/80 px-2 py-0.5 text-[10px] font-semibold text-green-700">
              <CheckCircle aria-hidden weight="fill" className="size-3" />
              {t("active")}
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 rounded-full bg-red-100/80 px-2 py-0.5 text-[10px] font-semibold text-red-700">
              <XCircle aria-hidden weight="fill" className="size-3" />
              {t("suspended")}
            </span>
          )}
          {/* Verified badge */}
          {user.email_verified && (
            <span className="inline-flex items-center gap-1 rounded-full bg-blue-100/60 px-2 py-0.5 text-[10px] font-medium text-blue-700">
              {t("verified")}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 mt-0.5">
          <PersonaBadge persona={user.persona} t={t} />
          {user.created_at && (
            <span className="text-[10px] text-[var(--text-muted)]">
              {new Date(user.created_at).toLocaleDateString()}
            </span>
          )}
        </div>
      </div>

      {/* Action */}
      <div className="shrink-0">
        {user.is_active ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={onSuspend}
            disabled={busy}
            aria-label={t("suspendAria", { email: user.email })}
            className="text-red-600 hover:bg-red-50"
          >
            <ProhibitInset aria-hidden weight="duotone" className="size-4 mr-1" />
            {t("suspend")}
          </Button>
        ) : (
          <Button
            variant="ghost"
            size="sm"
            onClick={onUnsuspend}
            disabled={busy}
            aria-label={t("unsuspendAria", { email: user.email })}
            className="text-green-700 hover:bg-green-50"
          >
            <CheckCircle aria-hidden weight="duotone" className="size-4 mr-1" />
            {t("unsuspend")}
          </Button>
        )}
      </div>
    </div>
  );
}

function PersonaBadge({
  persona,
  t,
}: {
  persona: string;
  t: ReturnType<typeof useTranslations>;
}) {
  const label =
    persona === "student"
      ? t("personaStudent")
      : persona === "partner_member"
        ? t("personaPartner")
        : persona === "university_staff"
          ? t("personaStaff")
          : persona;

  const cls =
    persona === "student"
      ? "bg-purple-100/60 text-purple-700"
      : persona === "partner_member"
        ? "bg-blue-100/60 text-blue-700"
        : "bg-teal-100/60 text-teal-700";

  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-medium ${cls}`}>
      {label}
    </span>
  );
}
