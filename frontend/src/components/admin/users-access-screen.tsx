"use client";

import { useState, useRef } from "react";
import { useTranslations, useLocale } from "next-intl";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  WarningCircle,
  UserCircle,
  ShieldCheck,
  IdentificationCard,
  Check,
} from "@phosphor-icons/react";
import { PageHeader } from "@/components/layout/page-header";
import {
  Tabs,
  TabPanel,
  StatusBadge,
  Skeleton,
  EmptyState,
  DataTable,
  Input,
  Select,
  Sheet,
  Modal,
  Button,
  useToast,
  type Column,
  type StatusTone,
} from "@/components/ui";
import {
  platformUsersApi,
  type PlatformUserRow,
  type AdminSession,
} from "@/lib/api/platform-users";
import { ApiError } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/format";

/* -------------------------------------------------------------------------- */
/* Helpers                                                                     */
/* -------------------------------------------------------------------------- */

function dash(v: string | null | undefined): string {
  return v?.trim() ? v : "—";
}

function useDebounce<T>(value: T, delay = 350): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  if (timerRef.current) clearTimeout(timerRef.current);
  timerRef.current = setTimeout(() => setDebouncedValue(value), delay);

  return debouncedValue;
}

/* -------------------------------------------------------------------------- */
/* Detail row in Sheet                                                         */
/* -------------------------------------------------------------------------- */

function DetailRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-0.5 border-b border-[var(--border-subtle)] py-2.5 last:border-0">
      <span className="text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        {label}
      </span>
      <span className="break-all text-sm text-[var(--text-primary)]">
        {children}
      </span>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Confirm dialog                                                               */
/* -------------------------------------------------------------------------- */

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  body: string;
  confirmLabel: string;
  cancelLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  dangerous?: boolean;
}

function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel,
  cancelLabel,
  onConfirm,
  onCancel,
  dangerous = false,
}: ConfirmDialogProps) {
  return (
    <Modal
      open={open}
      onClose={onCancel}
      title={title}
      size="sm"
      footer={
        <>
          <Button variant="ghost" onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button
            variant={dangerous ? "danger" : "primary"}
            onClick={onConfirm}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      <p className="text-sm text-[var(--text-secondary)]">{body}</p>
    </Modal>
  );
}

/* -------------------------------------------------------------------------- */
/* User 360 Sheet                                                              */
/* -------------------------------------------------------------------------- */

type PendingAction =
  | "suspend"
  | "unsuspend"
  | "grantSuperadmin"
  | "revokeSuperadmin"
  | null;

function User360Sheet({
  userId,
  onClose,
}: {
  userId: string | null;
  onClose: () => void;
}) {
  const t = useTranslations("adminConsole.usersAccess");
  const locale = useLocale();
  const qc = useQueryClient();
  const { show: showToast } = useToast();

  const [pendingAction, setPendingAction] = useState<PendingAction>(null);
  // Inline error for revoke-last-superadmin 409
  const [revokeError, setRevokeError] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ["platform-user-360", userId],
    queryFn: () => platformUsersApi.get360(userId!),
    enabled: Boolean(userId),
    staleTime: 30_000,
  });

  const suspendMutation = useMutation({
    mutationFn: (id: string) => platformUsersApi.suspend(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["platform-users"] });
      void qc.invalidateQueries({ queryKey: ["platform-user-360", userId] });
      showToast({ tone: "success", title: t("actions.suspendSuccess") });
    },
    onError: () => {
      showToast({ tone: "error", title: t("actions.suspendError") });
    },
  });

  const unsuspendMutation = useMutation({
    mutationFn: (id: string) => platformUsersApi.unsuspend(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["platform-users"] });
      void qc.invalidateQueries({ queryKey: ["platform-user-360", userId] });
      showToast({ tone: "success", title: t("actions.unsuspendSuccess") });
    },
    onError: () => {
      showToast({ tone: "error", title: t("actions.unsuspendError") });
    },
  });

  const grantSuperadminMutation = useMutation({
    mutationFn: (id: string) => platformUsersApi.grantSuperadmin(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["platform-users"] });
      void qc.invalidateQueries({ queryKey: ["platform-user-360", userId] });
      showToast({ tone: "success", title: t("actions.grantSuperadminSuccess") });
    },
    onError: () => {
      showToast({ tone: "error", title: t("actions.grantSuperadminError") });
    },
  });

  const revokeSuperadminMutation = useMutation({
    mutationFn: (id: string) => platformUsersApi.revokeSuperadmin(id),
    onSuccess: () => {
      setRevokeError(null);
      void qc.invalidateQueries({ queryKey: ["platform-users"] });
      void qc.invalidateQueries({ queryKey: ["platform-user-360", userId] });
      showToast({
        tone: "success",
        title: t("actions.revokeSuperadminSuccess"),
      });
    },
    onError: (err) => {
      // Surface 409 "last superadmin" message inline; generic error for others.
      if (err instanceof ApiError && err.status === 409) {
        setRevokeError(err.message);
      } else {
        showToast({ tone: "error", title: t("actions.revokeSuperadminError") });
      }
    },
  });

  const core = query.data?.core ?? null;
  const identities = query.data?.identities ?? [];
  const email = core?.email ?? "";

  function handleConfirm() {
    if (!userId || !pendingAction) return;
    if (pendingAction === "suspend") suspendMutation.mutate(userId);
    else if (pendingAction === "unsuspend") unsuspendMutation.mutate(userId);
    else if (pendingAction === "grantSuperadmin")
      grantSuperadminMutation.mutate(userId);
    else if (pendingAction === "revokeSuperadmin") {
      setRevokeError(null);
      revokeSuperadminMutation.mutate(userId);
    }
    setPendingAction(null);
  }

  const confirmTitle = pendingAction
    ? t(`actions.${pendingAction}ConfirmTitle` as Parameters<typeof t>[0])
    : "";
  const confirmBody =
    pendingAction && email
      ? t(
          `actions.${pendingAction}ConfirmBody` as Parameters<typeof t>[0],
          { email },
        )
      : "";
  const isDangerous =
    pendingAction === "suspend" || pendingAction === "revokeSuperadmin";

  return (
    <>
      <Sheet
        open={Boolean(userId)}
        onClose={onClose}
        title={t("sheet.title")}
        closeLabel={t("sheet.closeLabel")}
      >
        {query.isPending && (
          <div className="space-y-3 px-1 py-2">
            <Skeleton className="h-6 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-4 w-1/2" />
          </div>
        )}

        {query.isError && (
          <EmptyState
            kind="error"
            icon={WarningCircle}
            title={t("errorTitle")}
            description={t("errorBody")}
          />
        )}

        {core && (
          <div className="space-y-5">
            {/* Core fields */}
            <section aria-labelledby="sheet-core">
              <h3
                id="sheet-core"
                className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-[var(--text-muted)]"
              >
                <UserCircle
                  aria-hidden
                  weight="duotone"
                  className="size-4"
                />
                {t("sheet.coreSection")}
              </h3>
              <div className="space-y-0">
                <DetailRow label={t("sheet.labelId")}>
                  <span
                    className="font-mono text-xs"
                    style={{
                      fontFamily:
                        "'JetBrains Mono', ui-monospace, monospace",
                    }}
                  >
                    {core.id}
                  </span>
                </DetailRow>
                <DetailRow label={t("sheet.labelEmail")}>
                  {core.email}
                </DetailRow>
                <DetailRow label={t("sheet.labelActive")}>
                  <StatusBadge tone={core.is_active ? "active" : "closed"}>
                    {core.is_active
                      ? t("status.active")
                      : t("status.suspended")}
                  </StatusBadge>
                </DetailRow>
                <DetailRow label={t("sheet.labelSuperadmin")}>
                  <StatusBadge tone={core.is_superadmin ? "active" : "draft"}>
                    {core.is_superadmin ? (
                      <>
                        <Check
                          aria-hidden
                          weight="bold"
                          className="size-3 shrink-0"
                        />
                        {t("sheet.yes")}
                      </>
                    ) : (
                      t("sheet.no")
                    )}
                  </StatusBadge>
                </DetailRow>
                <DetailRow label={t("sheet.labelEmailVerified")}>
                  <StatusBadge
                    tone={core.email_verified ? "active" : "pending"}
                  >
                    {core.email_verified
                      ? t("status.verified")
                      : t("status.unverified")}
                  </StatusBadge>
                </DetailRow>
                <DetailRow label={t("sheet.labelCreatedAt")}>
                  {formatDateTime(core.created_at, locale)}
                </DetailRow>
                <DetailRow label={t("sheet.labelLastLogin")}>
                  {core.last_login_at
                    ? formatDateTime(core.last_login_at, locale)
                    : t("sheet.never")}
                </DetailRow>
                <DetailRow label={t("sheet.labelSessions")}>
                  <span className="font-mono text-sm font-semibold tabular-nums">
                    {query.data?.active_session_count ?? 0}
                  </span>
                </DetailRow>
                <DetailRow label={t("sheet.labelAiUsage")}>
                  <span className="font-mono text-sm font-semibold tabular-nums">
                    {query.data?.recent_ai_usage_count ?? 0}
                  </span>
                </DetailRow>
              </div>
            </section>

            {/* Identities */}
            <section aria-labelledby="sheet-identities">
              <h3
                id="sheet-identities"
                className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-[var(--text-muted)]"
              >
                <IdentificationCard
                  aria-hidden
                  weight="duotone"
                  className="size-4"
                />
                {t("sheet.identitiesSection")}
              </h3>
              {identities.length === 0 ? (
                <p className="text-sm text-[var(--text-muted)]">
                  {t("sheet.noIdentities")}
                </p>
              ) : (
                <ul className="divide-y divide-[var(--border-subtle)]">
                  {identities.map((identity) => (
                    <li
                      key={identity.identity_id}
                      className="flex flex-col gap-0.5 py-2 text-sm"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-medium text-[var(--text-primary)]">
                          {identity.persona}
                        </span>
                        {identity.is_primary && (
                          <StatusBadge tone="active">
                            {t("sheet.identityPrimary")}
                          </StatusBadge>
                        )}
                      </div>
                      {identity.org_id && (
                        <span className="text-xs text-[var(--text-secondary)]">
                          {t("sheet.identityOrg")}: {identity.org_id}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {/* Revoke-last-superadmin inline error */}
            {revokeError && (
              <div
                role="alert"
                className="rounded-lg border border-[var(--brand-red)]/30 bg-[var(--brand-red)]/5 px-4 py-3 text-sm text-[var(--brand-red)]"
              >
                {revokeError}
              </div>
            )}

            {/* Actions */}
            <section
              aria-label="User actions"
              className="flex flex-wrap gap-2 pt-1"
            >
              {/* Suspend / Unsuspend */}
              {core.is_active ? (
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() => setPendingAction("suspend")}
                >
                  {t("actions.suspend")}
                </Button>
              ) : (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setPendingAction("unsuspend")}
                >
                  {t("actions.unsuspend")}
                </Button>
              )}

              {/* Grant / Revoke superadmin */}
              {core.is_superadmin ? (
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() => {
                    setRevokeError(null);
                    setPendingAction("revokeSuperadmin");
                  }}
                >
                  <ShieldCheck
                    aria-hidden
                    weight="fill"
                    className="size-4"
                  />
                  {t("actions.revokeSuperadmin")}
                </Button>
              ) : (
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => setPendingAction("grantSuperadmin")}
                >
                  <ShieldCheck aria-hidden className="size-4" />
                  {t("actions.grantSuperadmin")}
                </Button>
              )}
            </section>
          </div>
        )}
      </Sheet>

      <ConfirmDialog
        open={Boolean(pendingAction)}
        title={confirmTitle}
        body={confirmBody}
        confirmLabel={t("actions.confirm")}
        cancelLabel={t("actions.cancel")}
        onConfirm={handleConfirm}
        onCancel={() => setPendingAction(null)}
        dangerous={isDangerous}
      />
    </>
  );
}

/* -------------------------------------------------------------------------- */
/* Users Tab                                                                   */
/* -------------------------------------------------------------------------- */

function UsersTab() {
  const t = useTranslations("adminConsole.usersAccess");
  const [q, setQ] = useState("");
  const [persona, setPersona] = useState("");
  const [page, setPage] = useState(1);
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);

  const debouncedQ = useDebounce(q, 350);

  const query = useQuery({
    queryKey: ["platform-users", { q: debouncedQ, persona, page }] as const,
    queryFn: () =>
      platformUsersApi.list({
        q: debouncedQ || undefined,
        persona: persona || undefined,
        page,
        page_size: 20,
      }),
    staleTime: 30_000,
  });

  const personaOptions = [
    { value: "", label: t("filter.allPersonas") },
    { value: "student", label: t("filter.persona.student") },
    { value: "alumni", label: t("filter.persona.alumni") },
    { value: "partner_member", label: t("filter.persona.partner_member") },
    { value: "university_staff", label: t("filter.persona.university_staff") },
  ];

  const columns: Column<PlatformUserRow>[] = [
    {
      key: "email",
      header: t("col.email"),
      cell: (row) => (
        <button
          type="button"
          className="text-left text-sm font-medium text-[var(--text-primary)] underline-offset-2 hover:underline"
          onClick={() => setSelectedUserId(row.id)}
        >
          {row.email}
        </button>
      ),
    },
    {
      key: "full_name",
      header: t("col.fullName"),
      cell: (row) => (
        <span className="text-sm text-[var(--text-secondary)]">
          {dash(row.full_name)}
        </span>
      ),
    },
    {
      key: "persona",
      header: t("col.persona"),
      cell: (row) => (
        <span className="text-xs font-medium text-[var(--text-secondary)]">
          {row.persona || "—"}
        </span>
      ),
    },
    {
      key: "is_active",
      header: t("col.status"),
      cell: (row) => {
        const tone: StatusTone = row.is_active ? "active" : "closed";
        return (
          <StatusBadge tone={tone}>
            {row.is_active ? t("status.active") : t("status.suspended")}
          </StatusBadge>
        );
      },
    },
    {
      key: "email_verified",
      header: t("col.verified"),
      cell: (row) => {
        const tone: StatusTone = row.email_verified ? "active" : "pending";
        return (
          <StatusBadge tone={tone}>
            {row.email_verified
              ? t("status.verified")
              : t("status.unverified")}
          </StatusBadge>
        );
      },
    },
  ];

  const items = query.data?.items ?? [];
  const totalPages = query.data?.total_pages ?? 1;
  const currentPage = query.data?.page ?? page;

  function handleSearch(e: React.ChangeEvent<HTMLInputElement>) {
    setQ(e.target.value);
    setPage(1);
  }

  function handlePersonaChange(e: React.ChangeEvent<HTMLSelectElement>) {
    setPersona(e.target.value);
    setPage(1);
  }

  return (
    <>
      {/* Filters */}
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="min-w-0 flex-1">
          <Input
            value={q}
            onChange={handleSearch}
            placeholder={t("filter.searchPlaceholder")}
            aria-label={t("filter.searchPlaceholder")}
          />
        </div>
        <div className="w-full sm:w-52">
          <Select
            value={persona}
            onChange={handlePersonaChange}
            options={personaOptions}
            aria-label={t("filter.allPersonas")}
          />
        </div>
      </div>

      {/* Table */}
      {query.isPending ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      ) : query.isError ? (
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={t("errorTitle")}
          description={t("errorBody")}
          action={
            <button
              onClick={() => void query.refetch()}
              className="text-xs font-semibold text-[var(--brand-primary)] underline-offset-2 hover:underline"
            >
              {t("retry")}
            </button>
          }
        />
      ) : (
        <>
          <DataTable<PlatformUserRow>
            columns={columns}
            rows={items}
            getRowId={(row) => row.id}
            empty={{
              kind: "empty",
              icon: UserCircle,
              title: t("emptyTitle"),
              description: t("emptyBody"),
            }}
          />

          {/* Offset pagination */}
          {totalPages > 1 && (
            <div className="mt-4 flex items-center justify-between gap-3">
              <Button
                variant="ghost"
                size="sm"
                disabled={currentPage <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                {t("pagination.prev")}
              </Button>
              <span className="text-xs text-[var(--text-secondary)]">
                {t("pagination.page", {
                  page: currentPage,
                  total: totalPages,
                })}
              </span>
              <Button
                variant="ghost"
                size="sm"
                disabled={currentPage >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                {t("pagination.next")}
              </Button>
            </div>
          )}
        </>
      )}

      {/* User 360 Sheet */}
      <User360Sheet
        userId={selectedUserId}
        onClose={() => setSelectedUserId(null)}
      />
    </>
  );
}

/* -------------------------------------------------------------------------- */
/* Sessions Tab                                                                */
/* -------------------------------------------------------------------------- */

function SessionsTab() {
  const t = useTranslations("adminConsole.usersAccess");
  const locale = useLocale();
  const qc = useQueryClient();
  const { show: showToast } = useToast();

  // Cursor-based load-more with dedup by session_id
  const [cursor, setCursor] = useState<string | null>(null);
  const [allSessions, setAllSessions] = useState<AdminSession[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);

  // Pending revoke confirm
  const [pendingRevoke, setPendingRevoke] = useState<AdminSession | null>(null);

  const query = useQuery({
    queryKey: ["admin-sessions", cursor] as const,
    queryFn: () => platformUsersApi.listSessions({ cursor: cursor ?? undefined, limit: 20 }),
    staleTime: 30_000,
  });

  // Accumulate pages, deduping by session_id
  const seenIds = useRef(new Set<string>());
  if (query.isSuccess) {
    const newItems = query.data.items.filter(
      (s) => !seenIds.current.has(s.session_id),
    );
    if (newItems.length > 0) {
      newItems.forEach((s) => seenIds.current.add(s.session_id));
      setAllSessions((prev) => [...prev, ...newItems]);
    }
    if (query.data.next_cursor !== nextCursor) {
      setNextCursor(query.data.next_cursor);
    }
  }

  const revokeMutation = useMutation({
    mutationFn: (sessionId: string) =>
      platformUsersApi.revokeSession(sessionId),
    onSuccess: (_data, sessionId) => {
      // Remove the revoked session from the accumulated list
      seenIds.current.delete(sessionId);
      setAllSessions((prev) =>
        prev.filter((s) => s.session_id !== sessionId),
      );
      void qc.invalidateQueries({ queryKey: ["admin-sessions"] });
      showToast({ tone: "success", title: t("sessions.revokeSuccess") });
    },
    onError: () => {
      showToast({ tone: "error", title: t("sessions.revokeError") });
    },
  });

  const columns: Column<AdminSession>[] = [
    {
      key: "user_email",
      header: t("sessions.col.email"),
      cell: (row) => (
        <span className="text-sm text-[var(--text-primary)]">
          {row.user_email}
        </span>
      ),
    },
    {
      key: "device_hint",
      header: t("sessions.col.device"),
      cell: (row) => (
        <span className="text-sm text-[var(--text-secondary)]">
          {dash(row.device_hint)}
        </span>
      ),
    },
    {
      key: "city_level_location",
      header: t("sessions.col.location"),
      cell: (row) => (
        <span className="text-sm text-[var(--text-secondary)]">
          {dash(row.city_level_location)}
        </span>
      ),
    },
    {
      key: "last_seen_at",
      header: t("sessions.col.lastSeen"),
      cell: (row) => (
        <span className="text-xs text-[var(--text-secondary)]">
          {formatDateTime(row.last_seen_at, locale)}
        </span>
      ),
    },
    {
      key: "expires_at",
      header: t("sessions.col.expires"),
      cell: (row) => (
        <span className="text-xs text-[var(--text-secondary)]">
          {formatDateTime(row.expires_at, locale)}
        </span>
      ),
    },
    {
      key: "actions",
      header: t("sessions.col.actions"),
      align: "right",
      cell: (row) => (
        <button
          type="button"
          onClick={() => setPendingRevoke(row)}
          className="text-xs font-semibold text-[var(--brand-red)] underline-offset-2 hover:underline"
        >
          {t("sessions.revokeAction")}
        </button>
      ),
    },
  ];

  return (
    <>
      {query.isPending && allSessions.length === 0 ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      ) : query.isError && allSessions.length === 0 ? (
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={t("sessions.errorTitle")}
          description={t("sessions.errorBody")}
          action={
            <button
              onClick={() => {
                seenIds.current.clear();
                setAllSessions([]);
                setCursor(null);
                void query.refetch();
              }}
              className="text-xs font-semibold text-[var(--brand-primary)] underline-offset-2 hover:underline"
            >
              {t("retry")}
            </button>
          }
        />
      ) : (
        <>
          <DataTable<AdminSession>
            columns={columns}
            rows={allSessions}
            getRowId={(row) => row.session_id}
            empty={{
              kind: "empty",
              icon: ShieldCheck,
              title: t("sessions.emptyTitle"),
              description: t("sessions.emptyBody"),
            }}
          />

          {nextCursor && (
            <div className="mt-4 flex justify-center">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setCursor(nextCursor)}
                disabled={query.isFetching}
              >
                {query.isFetching
                  ? "…"
                  : t("sessions.loadMore")}
              </Button>
            </div>
          )}
        </>
      )}

      {/* Revoke confirm */}
      <ConfirmDialog
        open={Boolean(pendingRevoke)}
        title={t("sessions.revokeConfirmTitle")}
        body={t("sessions.revokeConfirmBody")}
        confirmLabel={t("sessions.revokeConfirm")}
        cancelLabel={t("sessions.revokeCancel")}
        onConfirm={() => {
          if (pendingRevoke) {
            revokeMutation.mutate(pendingRevoke.session_id);
          }
          setPendingRevoke(null);
        }}
        onCancel={() => setPendingRevoke(null)}
        dangerous
      />
    </>
  );
}

/* -------------------------------------------------------------------------- */
/* Main screen                                                                 */
/* -------------------------------------------------------------------------- */

const TAB_ID_BASE = "users-access";

export function UsersAccessScreen() {
  const t = useTranslations("adminConsole.usersAccess");
  const [activeTab, setActiveTab] = useState("users");

  const tabItems = [
    { value: "users", label: t("tabs.users") },
    { value: "sessions", label: t("tabs.sessions") },
  ];

  return (
    <>
      <PageHeader title={t("pageTitle")} />

      <Tabs
        items={tabItems}
        value={activeTab}
        onValueChange={setActiveTab}
        ariaLabel={t("pageTitle")}
        idBase={TAB_ID_BASE}
      />

      <TabPanel
        tabsId={TAB_ID_BASE}
        value="users"
        active={activeTab === "users"}
      >
        <UsersTab />
      </TabPanel>

      <TabPanel
        tabsId={TAB_ID_BASE}
        value="sessions"
        active={activeTab === "sessions"}
      >
        <SessionsTab />
      </TabPanel>
    </>
  );
}
