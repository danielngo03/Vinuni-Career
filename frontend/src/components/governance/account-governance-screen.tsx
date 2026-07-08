"use client";

import { useEffect, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import {
  ArrowCounterClockwise,
  Eye,
  Info,
  MagnifyingGlass,
  Prohibit,
  SealCheck,
  ShieldWarning,
  SignIn,
  UsersThree,
  WarningCircle,
} from "@phosphor-icons/react";
import {
  Button,
  DataTable,
  EmptyState,
  Input,
  Modal,
  SegmentedControl,
  Sheet,
  Skeleton,
  StatusBadge,
  Textarea,
  useToast,
  type Column,
} from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { ApiError } from "@/lib/api";
import {
  useGovernedAccountDetail,
  useGovernedAccounts,
  useReinstateAccount,
  useSuspendAccount,
  type GovernedAccountRow,
} from "@/lib/api/account-governance";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { formatDateTime } from "@/lib/format";
import { useAuthStore } from "@/stores/auth-store";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 30;
const REASON_MAX = 500;

type StatusFilter = "all" | "active" | "suspended";

/** The account currently targeted for a suspend/reinstate write. */
interface ActionTarget {
  id: string;
  email: string;
  /** Current state — active accounts get suspended, suspended ones reinstated. */
  active: boolean;
}

/**
 * University cross-persona account governance (Phase 5).
 *
 * A granted governor (`accounts:govern` in a university org; superadmin
 * bypasses) reviews student and partner-member accounts and suspends or
 * reinstates them. Every write requires a non-empty reason and is audited
 * backend-side. Privacy-safe throughout: no CVs, tokens, IP/UA, or AI
 * internals are ever shown.
 *
 * Gating: the list query runs with `retry:false`, so a backend 403 renders a
 * clean permission state — this is the primary access gate for staff who reach
 * the URL without the grant (the sidebar also hides the entry via
 * `requiresPermission`).
 */
export function AccountGovernanceScreen() {
  const t = useTranslations("accountGovernance");
  const tc = useTranslations("common");
  const tStates = useTranslations("states");
  const locale = useLocale();
  const toast = useToast();
  const getMessage = useApiErrorMessage();

  const currentUser = useAuthStore((s) => s.user);
  const isSuperadmin = currentUser?.isSuperadmin ?? false;

  const [persona, setPersona] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [page, setPage] = useState(1);

  const [detailId, setDetailId] = useState<string | null>(null);
  const [actionTarget, setActionTarget] = useState<ActionTarget | null>(null);
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState<string | null>(null);

  // Debounce search; reset to page 1 on every new term.
  useEffect(() => {
    const id = setTimeout(() => {
      setDebouncedQ(q);
      setPage(1);
    }, 350);
    return () => clearTimeout(id);
  }, [q]);

  const query = useGovernedAccounts({
    persona: persona || undefined,
    q: debouncedQ || undefined,
    page,
    page_size: PAGE_SIZE,
  });

  const suspendMut = useSuspendAccount();
  const reinstateMut = useReinstateAccount();
  const busy = suspendMut.isPending || reinstateMut.isPending;

  const serverItems = useMemo(() => query.data?.items ?? [], [query.data]);
  // Status has no server filter (the list endpoint takes persona + search
  // only), so refine it client-side over the loaded page. The scope hint keeps
  // this honest; a server `status` param is the recommended enhancement.
  const visibleRows = useMemo(() => {
    if (status === "all") return serverItems;
    return serverItems.filter((r) => (status === "active" ? r.is_active : !r.is_active));
  }, [serverItems, status]);

  const total = query.data?.total ?? 0;
  const totalPages = query.data?.total_pages ?? 1;

  function openAction(target: ActionTarget) {
    setActionTarget(target);
    setReason("");
    setReasonError(null);
  }

  function submitAction() {
    if (!actionTarget) return;
    const trimmed = reason.trim();
    if (!trimmed) {
      setReasonError(t("reasonRequired"));
      return;
    }
    const mut = actionTarget.active ? suspendMut : reinstateMut;
    const successMsg = actionTarget.active
      ? t("suspendSuccess")
      : t("reinstateSuccess");
    mut.mutate(
      { id: actionTarget.id, reason: trimmed },
      {
        onSuccess: () => {
          toast.show({ tone: "success", title: successMsg });
          setActionTarget(null);
          setReason("");
        },
        onError: (e) => toast.show({ tone: "error", title: getMessage(e) }),
      },
    );
  }

  function personaLabel(p: string): string {
    if (p === "student") return t("personaStudent");
    if (p === "partner_member") return t("personaPartner");
    if (p === "university_staff") return t("personaStaff");
    return p;
  }

  /* ── Whole-screen permission / auth / error gates ─────────────────────── */
  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    if (err.isPermissionError || err.isAuthError) {
      return (
        <div>
          <PageHeader title={t("title")} />
          <EmptyState
            kind={err.isPermissionError ? "permission" : "auth"}
            icon={err.isPermissionError ? ShieldWarning : SignIn}
            title={err.isPermissionError ? t("permissionTitle") : tStates("authTitle")}
            description={err.isPermissionError ? t("permissionBody") : tStates("authBody")}
          />
        </div>
      );
    }
  }

  const columns: Column<GovernedAccountRow>[] = [
    {
      key: "account",
      header: t("colAccount"),
      cell: (r) => (
        <div className="min-w-0">
          <p className="truncate font-semibold text-[var(--text-primary)]">
            {r.full_name || t("noName")}
          </p>
          <p className="truncate text-xs text-[var(--text-muted)]">{r.email}</p>
        </div>
      ),
    },
    {
      key: "persona",
      header: t("colPersona"),
      cell: (r) => (
        <span className="inline-flex items-center rounded-full border border-[var(--border-default)] bg-[var(--bg-subtle)] px-2.5 py-0.5 text-xs font-semibold text-[var(--text-secondary)]">
          {personaLabel(r.persona)}
        </span>
      ),
    },
    {
      key: "status",
      header: t("colStatus"),
      cell: (r) => (
        <StatusBadge tone={r.is_active ? "active" : "rejected"}>
          {r.is_active ? t("badgeActive") : t("badgeSuspended")}
        </StatusBadge>
      ),
    },
    {
      key: "joined",
      header: t("colJoined"),
      cell: (r) => (
        <span className="whitespace-nowrap text-xs text-[var(--text-muted)]">
          {formatDateTime(r.created_at, locale)}
        </span>
      ),
    },
    {
      key: "actions",
      header: t("colActions"),
      align: "right",
      cell: (r) => {
        const isSelf = r.id === currentUser?.id;
        const isProtected = r.is_superadmin && !isSuperadmin;
        return (
          <div className="flex items-center justify-end gap-1.5">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setDetailId(r.id)}
              aria-label={t("viewAria", { email: r.email })}
            >
              <Eye aria-hidden weight="bold" className="size-4" />
              {t("view")}
            </Button>
            {isProtected ? (
              <span className="max-w-[10rem] text-right text-xs text-[var(--text-muted)]">
                {t("protectedNote")}
              </span>
            ) : isSelf && r.is_active ? (
              <span className="max-w-[10rem] text-right text-xs text-[var(--text-muted)]">
                {t("selfNote")}
              </span>
            ) : r.is_active ? (
              <Button
                variant="ghost"
                size="sm"
                className="text-[var(--brand-red)] hover:bg-[var(--red-50)]"
                onClick={() =>
                  openAction({ id: r.id, email: r.email, active: true })
                }
                aria-label={t("suspendAria", { email: r.email })}
              >
                <Prohibit aria-hidden weight="bold" className="size-4" />
                {t("suspend")}
              </Button>
            ) : (
              <Button
                variant="ghost"
                size="sm"
                className="text-[var(--teal-600)] hover:bg-[var(--teal-50)]"
                onClick={() =>
                  openAction({ id: r.id, email: r.email, active: false })
                }
                aria-label={t("reinstateAria", { email: r.email })}
              >
                <ArrowCounterClockwise aria-hidden weight="bold" className="size-4" />
                {t("reinstate")}
              </Button>
            )}
          </div>
        );
      },
    },
  ];

  const statusFilteredEmpty = status !== "all" && serverItems.length > 0;

  return (
    <div>
      <PageHeader title={t("title")} />
      <p className="mb-4 max-w-3xl text-sm text-[var(--text-secondary)]">
        {t("subtitle")}
      </p>

      {/* Audit disclosure — governance writes are recorded. */}
      <div className="mb-5 flex items-start gap-2.5 rounded-xl border border-[var(--amber-600)]/30 bg-[var(--amber-100)] px-3.5 py-2.5 text-sm text-[var(--amber-700)]">
        <Info aria-hidden weight="fill" className="mt-0.5 size-4 shrink-0" />
        <p>{t("auditNotice")}</p>
      </div>

      {/* ── Filters ── */}
      <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div className="relative w-full lg:max-w-sm">
          <MagnifyingGlass
            aria-hidden
            className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-[var(--text-muted)]"
          />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t("searchPlaceholder")}
            aria-label={t("searchAria")}
            className="pl-9"
          />
        </div>
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          <div className="flex flex-col gap-1">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
              {t("personaFilterLabel")}
            </span>
            <SegmentedControl
              ariaLabel={t("personaFilterLabel")}
              size="sm"
              value={persona}
              onValueChange={(v) => {
                setPersona(v);
                setPage(1);
              }}
              options={[
                { value: "", label: t("personaAll") },
                { value: "student", label: t("personaStudent") },
                { value: "partner_member", label: t("personaPartner") },
                { value: "university_staff", label: t("personaStaff") },
              ]}
            />
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
              {t("statusFilterLabel")}
            </span>
            <SegmentedControl
              ariaLabel={t("statusFilterLabel")}
              size="sm"
              value={status}
              onValueChange={(v) => setStatus(v as StatusFilter)}
              options={[
                { value: "all", label: t("statusAll") },
                { value: "active", label: t("statusActive") },
                { value: "suspended", label: t("statusSuspended") },
              ]}
            />
          </div>
        </div>
      </div>

      {/* Count + scope hint */}
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        {!query.isPending && (
          <span className="text-xs font-medium text-[var(--text-muted)]">
            {t("totalCount", { count: total })}
          </span>
        )}
        {status !== "all" && (
          <span className="text-xs text-[var(--text-muted)]">
            {t("statusScopeHint")}
          </span>
        )}
      </div>

      {/* ── Table / error ── */}
      {query.isError ? (
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
      ) : (
        <DataTable
          columns={columns}
          rows={visibleRows}
          getRowId={(r) => r.id}
          loading={query.isPending}
          caption={t("title")}
          empty={{
            kind: "empty",
            icon: UsersThree,
            title: statusFilteredEmpty ? t("statusEmptyTitle", {
              status: (status === "active" ? t("statusActive") : t("statusSuspended")).toLowerCase(),
            }) : t("emptyTitle"),
            description: statusFilteredEmpty ? t("statusEmptyBody") : t("emptyBody"),
          }}
        />
      )}

      {/* ── Pagination ── */}
      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-center gap-3">
          <Button
            variant="secondary"
            size="sm"
            disabled={page <= 1 || query.isFetching}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            {t("prev")}
          </Button>
          <span className="text-xs text-[var(--text-muted)]">
            {t("pageOf", { page, totalPages })}
          </span>
          <Button
            variant="secondary"
            size="sm"
            disabled={page >= totalPages || query.isFetching}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          >
            {t("next")}
          </Button>
        </div>
      )}

      {/* ── Reason-required action modal ── */}
      <Modal
        open={actionTarget !== null}
        onClose={() => setActionTarget(null)}
        title={actionTarget?.active ? t("suspendTitle") : t("reinstateTitle")}
        description={actionTarget?.active ? t("suspendDesc") : t("reinstateDesc")}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setActionTarget(null)}>
              {tc("cancel")}
            </Button>
            <Button
              variant={actionTarget?.active ? "danger" : "primary"}
              loading={busy}
              disabled={reason.trim().length === 0}
              onClick={submitAction}
            >
              {actionTarget?.active ? t("confirmSuspend") : t("confirmReinstate")}
            </Button>
          </>
        }
      >
        {actionTarget && (
          <p className="mb-3 truncate rounded-lg border border-[var(--border-default)] bg-[var(--bg-subtle)] px-3 py-2 text-sm font-medium text-[var(--text-primary)]">
            {actionTarget.email}
          </p>
        )}
        <Textarea
          label={t("reasonLabel")}
          required
          value={reason}
          maxLength={REASON_MAX}
          placeholder={t("reasonPlaceholder")}
          error={reasonError ?? undefined}
          help={t("reasonHint")}
          rows={3}
          onChange={(e) => {
            setReason(e.target.value);
            if (e.target.value.trim()) setReasonError(null);
          }}
        />
        <p
          aria-hidden
          className="mt-1.5 text-right text-xs text-[var(--text-muted)]"
        >
          {t("charCount", { count: reason.length, max: REASON_MAX })}
        </p>
      </Modal>

      {/* ── Account detail drawer ── */}
      <AccountDetailPanel
        id={detailId}
        onClose={() => setDetailId(null)}
        onAction={openAction}
        personaLabel={personaLabel}
        canGovern={(row) =>
          row.id !== currentUser?.id && !(row.is_superadmin && !isSuperadmin)
        }
      />
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Detail drawer                                                               */
/* -------------------------------------------------------------------------- */

function AccountDetailPanel({
  id,
  onClose,
  onAction,
  personaLabel,
  canGovern,
}: {
  id: string | null;
  onClose: () => void;
  onAction: (target: ActionTarget) => void;
  personaLabel: (p: string) => string;
  canGovern: (row: { id: string; is_superadmin: boolean }) => boolean;
}) {
  const t = useTranslations("accountGovernance");
  const tc = useTranslations("common");
  const locale = useLocale();
  const detail = useGovernedAccountDetail(id);

  // A non-superadmin governor inspecting a superadmin gets 403 → show the
  // "protected account" state. Any other failure (incl. 404) is a generic error.
  const isPermission =
    detail.isError &&
    detail.error instanceof ApiError &&
    detail.error.isPermissionError;

  const core = detail.data?.core;

  return (
    <Sheet
      open={id !== null}
      onClose={onClose}
      title={t("detailTitle")}
      closeLabel={tc("close")}
    >
      {detail.isPending ? (
        <div className="space-y-3">
          <Skeleton className="h-6 w-2/3 rounded-lg" />
          <Skeleton className="h-4 w-1/2 rounded-lg" />
          <Skeleton className="h-24 w-full rounded-xl" />
          <Skeleton className="h-24 w-full rounded-xl" />
        </div>
      ) : isPermission ? (
        <EmptyState
          kind="permission"
          icon={ShieldWarning}
          title={t("detailPermissionTitle")}
          description={t("detailPermissionBody")}
        />
      ) : detail.isError || !core ? (
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={t("detailErrorTitle")}
          description={t("detailErrorBody")}
        />
      ) : (
        <div className="space-y-5">
          {/* Identity header */}
          <div>
            <p className="text-base font-bold text-[var(--text-primary)]">
              {core.full_name || t("noName")}
            </p>
            <p className="text-sm text-[var(--text-muted)]">{core.email}</p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <StatusBadge tone={core.is_active ? "active" : "rejected"}>
                {core.is_active ? t("badgeActive") : t("badgeSuspended")}
              </StatusBadge>
              {core.email_verified && (
                <span className="inline-flex items-center gap-1 rounded-full border border-[var(--teal-500)]/40 bg-[var(--teal-50)] px-2 py-0.5 text-xs font-semibold text-[var(--teal-600)]">
                  <SealCheck aria-hidden weight="fill" className="size-3" />
                  {t("badgeVerified")}
                </span>
              )}
              {core.is_superadmin && (
                <span className="inline-flex items-center rounded-full border border-[var(--border-default)] bg-[var(--bg-subtle)] px-2 py-0.5 text-xs font-semibold text-[var(--text-secondary)]">
                  {t("badgeSuperadmin")}
                </span>
              )}
            </div>
          </div>

          {/* Facts */}
          <dl className="grid grid-cols-1 gap-x-4 gap-y-3 sm:grid-cols-2">
            <Field label={t("fieldEmailVerified")}>
              {core.email_verified ? t("badgeVerified") : t("badgeUnverified")}
            </Field>
            <Field label={t("fieldSessions")}>
              {t("sessionsValue", { count: detail.data?.active_session_count ?? 0 })}
            </Field>
            <Field label={t("fieldJoined")}>
              {formatDateTime(core.created_at, locale)}
            </Field>
            <Field label={t("fieldLastLogin")}>
              {core.last_login_at
                ? formatDateTime(core.last_login_at, locale)
                : t("neverLoggedIn")}
            </Field>
          </dl>

          {/* Identities */}
          {(detail.data?.identities.length ?? 0) > 0 && (
            <div>
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                {t("identitiesTitle")}
              </p>
              <ul className="space-y-1.5">
                {detail.data!.identities.map((idn, i) => (
                  <li
                    key={`${idn.persona}-${i}`}
                    className="flex items-center justify-between rounded-lg border border-[var(--border-default)] bg-[var(--bg-subtle)] px-3 py-2 text-sm"
                  >
                    <span className="font-medium text-[var(--text-primary)]">
                      {personaLabel(idn.persona)}
                    </span>
                    {idn.is_primary && (
                      <span className="rounded-full bg-[var(--surface-card)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                        {t("primaryTag")}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Action */}
          {canGovern(core) && (
            <div className="border-t border-[var(--border-default)] pt-4">
              {core.is_active ? (
                <Button
                  variant="danger"
                  className="w-full"
                  onClick={() =>
                    onAction({ id: core.id, email: core.email, active: true })
                  }
                >
                  <Prohibit aria-hidden weight="bold" className="size-4" />
                  {t("suspend")}
                </Button>
              ) : (
                <Button
                  variant="primary"
                  className="w-full"
                  onClick={() =>
                    onAction({ id: core.id, email: core.email, active: false })
                  }
                >
                  <ArrowCounterClockwise aria-hidden weight="bold" className="size-4" />
                  {t("reinstate")}
                </Button>
              )}
            </div>
          )}
        </div>
      )}
    </Sheet>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("min-w-0")}>
      <dt className="text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        {label}
      </dt>
      <dd className="mt-0.5 truncate text-sm text-[var(--text-primary)]">
        {children}
      </dd>
    </div>
  );
}
