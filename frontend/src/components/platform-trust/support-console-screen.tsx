"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  MagnifyingGlass,
  ShieldWarning,
  SignIn,
  Envelope,
  ArrowClockwise,
  WarningCircle,
  CheckCircle,
  Tray,
} from "@phosphor-icons/react";
import {
  Button,
  DataTable,
  EmptyState,
  Input,
  Modal,
  Select,
  StatusBadge,
  Tabs,
  TabPanel,
  Textarea,
  useToast,
  type Column,
  type StatusTone,
} from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { TrustTabs } from "./trust-tabs";
import {
  ApiError,
  supportApi,
  type SupportUserRow,
  type SupportOrgRow,
  type SupportLookupResult,
  type SupportCase,
  type RevealedContact,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { formatDateTime } from "@/lib/format";

const TABS_ID = "support-console";

const CASE_SEVERITY_TONE: Record<string, StatusTone> = {
  low: "info",
  medium: "pending",
  high: "rejected",
};

function PermissionOrErrorState({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry: () => void;
}) {
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  if (error instanceof ApiError && (error.isPermissionError || error.isAuthError)) {
    return (
      <EmptyState
        kind={error.isPermissionError ? "permission" : "auth"}
        icon={error.isPermissionError ? ShieldWarning : SignIn}
        title={error.isPermissionError ? tStates("permissionTitle") : tStates("authTitle")}
        description={error.isPermissionError ? tStates("permissionBody") : tStates("authBody")}
      />
    );
  }
  return (
    <EmptyState
      kind="error"
      icon={WarningCircle}
      title={tStates("errorTitle")}
      description={tStates("errorBody")}
      action={
        <Button variant="secondary" onClick={onRetry}>
          {tc("retry")}
        </Button>
      }
    />
  );
}

/** Masks an email for default display; unmasked only after an audited reveal. */
function maskEmail(email: string): string {
  const [local, domain] = email.split("@");
  if (!domain || !local) return "•••";
  const visible = local.slice(0, 1);
  return `${visible}${"•".repeat(Math.max(local.length - 1, 3))}@${domain}`;
}

export function SupportConsoleScreen() {
  const t = useTranslations("supportConsole");
  const tc = useTranslations("common");
  const locale = useLocale();
  const toast = useToast();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();

  const [tab, setTab] = useState("lookup");

  const items = [
    { value: "lookup", label: t("tabs.lookup") },
    { value: "outbox", label: t("tabs.outbox") },
    { value: "cases", label: t("tabs.cases") },
  ];

  return (
    <div>
      <PageHeader title={t("title")} />
      <TrustTabs />
      <Tabs items={items} value={tab} onValueChange={setTab} ariaLabel={t("title")} idBase={TABS_ID} />
      <TabPanel tabsId={TABS_ID} value="lookup" active={tab === "lookup"}>
        <LookupPanel />
      </TabPanel>
      <TabPanel tabsId={TABS_ID} value="outbox" active={tab === "outbox"}>
        <OutboxPanel />
      </TabPanel>
      <TabPanel tabsId={TABS_ID} value="cases" active={tab === "cases"}>
        <CasesPanel />
      </TabPanel>
    </div>
  );

  function LookupPanel() {
    const [type, setType] = useState<"user" | "organization">("user");
    const [q, setQ] = useState("");
    const [queryText, setQueryText] = useState("");
    const [revealTarget, setRevealTarget] = useState<SupportUserRow | null>(null);
    const [reason, setReason] = useState("");
    const [reasonError, setReasonError] = useState<string | null>(null);
    const [revealed, setRevealed] = useState<Record<string, RevealedContact>>({});

    const query = useQuery<SupportLookupResult<SupportUserRow> | SupportLookupResult<SupportOrgRow>>({
      queryKey: ["support", "lookup", type, queryText],
      queryFn: () =>
        type === "user"
          ? supportApi.lookupUsers(queryText || undefined)
          : supportApi.lookupOrgs(queryText || undefined),
      retry: false,
    });

    const reveal = useMutation({
      mutationFn: () => supportApi.revealUserContact(revealTarget!.id, reason),
      onSuccess: (data) => {
        setRevealed((prev) => ({ ...prev, [revealTarget!.id]: data }));
        setRevealTarget(null);
        setReason("");
        toast.show({ tone: "success", title: t("revealSuccess") });
      },
      onError: (e) => toast.show({ tone: "error", title: getMessage(e) }),
    });

    const userColumns: Column<SupportUserRow>[] = [
      {
        key: "email",
        header: t("colEmail"),
        cell: (r) => revealed[r.id]?.email ?? maskEmail(r.email),
      },
      {
        key: "full_name",
        header: t("colName"),
        cell: (r) => revealed[r.id]?.full_name || t("nameHidden"),
      },
      { key: "persona", header: t("colPersona"), cell: (r) => r.persona },
      {
        key: "status",
        header: t("colStatus"),
        cell: (r) => (
          <StatusBadge tone={r.is_active ? "active" : "closed"}>
            {r.is_active ? t("statusActive") : t("statusSuspended")}
          </StatusBadge>
        ),
      },
      {
        key: "actions",
        header: "",
        align: "right",
        cell: (r) => (
          <Button
            variant="ghost"
            size="sm"
            disabled={!!revealed[r.id]}
            onClick={() => {
              setRevealTarget(r);
              setReason("");
              setReasonError(null);
            }}
          >
            <Envelope aria-hidden weight="duotone" className="size-4" />
            {revealed[r.id] ? t("revealed") : t("reveal")}
          </Button>
        ),
      },
    ];

    const orgColumns: Column<SupportOrgRow>[] = [
      { key: "display_name", header: t("colOrgName"), cell: (r) => r.display_name },
      { key: "org_type", header: t("colOrgType"), cell: (r) => r.org_type },
      {
        key: "status",
        header: t("colStatus"),
        cell: (r) => (
          <StatusBadge tone={r.status === "active" ? "active" : "closed"}>{r.status}</StatusBadge>
        ),
      },
      {
        key: "verified",
        header: t("colVerified"),
        cell: (r) =>
          r.is_verified ? (
            <StatusBadge tone="verified">{tc("yes")}</StatusBadge>
          ) : (
            <span className="text-[var(--text-muted)]">{tc("no")}</span>
          ),
      },
      { key: "tier", header: t("colTier"), cell: (r) => r.subscription_tier ?? "—" },
    ];

    return (
      <div>
        <div className="mb-4 flex flex-wrap items-end gap-3">
          <Select
            label={t("typeLabel")}
            value={type}
            onChange={(e) => setType(e.target.value as "user" | "organization")}
            options={[
              { value: "user", label: t("typeUser") },
              { value: "organization", label: t("typeOrg") },
            ]}
            className="w-40"
          />
          <form
            className="flex flex-1 min-w-[220px] items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              setQueryText(q.trim());
            }}
          >
            <Input
              label={t("searchLabel")}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={t("searchPlaceholder")}
              className="flex-1"
            />
            <Button type="submit" variant="secondary">
              <MagnifyingGlass aria-hidden weight="bold" className="size-4" />
              {tc("search")}
            </Button>
          </form>
        </div>

        {query.isError ? (
          <PermissionOrErrorState error={query.error} onRetry={() => query.refetch()} />
        ) : type === "user" ? (
          <DataTable
            columns={userColumns}
            rows={(query.data?.items as SupportUserRow[] | undefined) ?? []}
            getRowId={(r) => r.id}
            loading={query.isPending}
            caption={t("tabs.lookup")}
            empty={{ kind: "empty", icon: MagnifyingGlass, title: t("lookupEmpty") }}
          />
        ) : (
          <DataTable
            columns={orgColumns}
            rows={(query.data?.items as SupportOrgRow[] | undefined) ?? []}
            getRowId={(r) => r.id}
            loading={query.isPending}
            caption={t("tabs.lookup")}
            empty={{ kind: "empty", icon: MagnifyingGlass, title: t("lookupEmpty") }}
          />
        )}

        <Modal
          open={revealTarget !== null}
          onClose={() => setRevealTarget(null)}
          title={t("revealTitle")}
          description={t("revealBody")}
          size="sm"
          closeLabel={tc("close")}
          footer={
            <>
              <Button variant="ghost" onClick={() => setRevealTarget(null)}>
                {tc("cancel")}
              </Button>
              <Button
                variant="danger"
                loading={reveal.isPending}
                onClick={() => {
                  if (!reason.trim()) {
                    setReasonError(t("reasonRequired"));
                    return;
                  }
                  reveal.mutate();
                }}
              >
                {t("revealConfirm")}
              </Button>
            </>
          }
        >
          <Textarea
            label={t("reasonLabel")}
            required
            value={reason}
            onChange={(e) => {
              setReason(e.target.value);
              if (e.target.value.trim()) setReasonError(null);
            }}
            error={reasonError ?? undefined}
            rows={3}
          />
          <p className="mt-3 rounded-xl border border-[var(--border-default)] bg-[var(--bg-subtle)] px-3 py-2 text-xs text-[var(--text-muted)]">
            {t("loggedNotice")}
          </p>
        </Modal>
      </div>
    );
  }

  function OutboxPanel() {
    const [outboxId, setOutboxId] = useState("");
    const [idError, setIdError] = useState<string | null>(null);

    const health = useQuery({
      queryKey: ["support", "outbox-health"],
      queryFn: () => supportApi.outboxHealth(),
      retry: false,
      refetchInterval: 30000,
    });

    const requeue = useMutation({
      mutationFn: (id: string) => supportApi.requeueOutbox(id),
      onSuccess: () => {
        setOutboxId("");
        toast.show({ tone: "success", title: t("requeueSuccess") });
        void qc.invalidateQueries({ queryKey: ["support", "outbox-health"] });
      },
      onError: (e) => {
        if (e instanceof ApiError && e.isConflict) {
          toast.show({ tone: "error", title: t("requeueNotDead") });
          return;
        }
        toast.show({ tone: "error", title: getMessage(e) });
      },
    });

    if (health.isError) {
      return <PermissionOrErrorState error={health.error} onRetry={() => health.refetch()} />;
    }

    type OutboxCountKey = "pending" | "retry_scheduled" | "sent" | "failed" | "dead" | "skipped";
    const cards: Array<{ key: OutboxCountKey; tone: StatusTone; label: string }> = [
      { key: "pending", tone: "pending", label: t("outbox.pending") },
      { key: "retry_scheduled", tone: "info", label: t("outbox.retryScheduled") },
      { key: "sent", tone: "active", label: t("outbox.sent") },
      { key: "failed", tone: "rejected", label: t("outbox.failed") },
      { key: "dead", tone: "rejected", label: t("outbox.dead") },
      { key: "skipped", tone: "draft", label: t("outbox.skipped") },
    ];

    return (
      <div>
        <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {health.isPending
            ? Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="h-24 animate-pulse rounded-2xl bg-[var(--bg-subtle)]" />
              ))
            : cards.map((c) => (
                <div
                  key={c.key}
                  className="rounded-2xl border border-[var(--border-default)] bg-white p-4"
                >
                  <p className="text-2xl font-bold text-[var(--text-primary)]">
                    {(health.data?.[c.key] as number) ?? 0}
                  </p>
                  <p className="mt-1 text-xs font-semibold text-[var(--text-secondary)]">{c.label}</p>
                </div>
              ))}
        </div>

        {!health.isPending && health.data?.oldest_pending_age_seconds != null && (
          <p className="mb-6 text-sm text-[var(--text-secondary)]">
            {t("oldestPending", {
              seconds: health.data.oldest_pending_age_seconds,
            })}
          </p>
        )}

        <div className="rounded-2xl border border-[var(--border-default)] bg-white p-5">
          <h3 className="mb-1 text-sm font-bold text-[var(--text-primary)]">{t("requeueTitle")}</h3>
          <p className="mb-4 text-sm text-[var(--text-secondary)]">{t("requeueBody")}</p>
          <div className="flex flex-wrap items-end gap-2">
            <Input
              label={t("outboxIdLabel")}
              value={outboxId}
              onChange={(e) => {
                setOutboxId(e.target.value);
                setIdError(null);
              }}
              placeholder={t("outboxIdPlaceholder")}
              error={idError ?? undefined}
              className="min-w-[280px] flex-1"
            />
            <Button
              variant="secondary"
              loading={requeue.isPending}
              onClick={() => {
                if (!outboxId.trim()) {
                  setIdError(t("outboxIdRequired"));
                  return;
                }
                requeue.mutate(outboxId.trim());
              }}
            >
              <ArrowClockwise aria-hidden weight="bold" className="size-4" />
              {t("requeueAction")}
            </Button>
          </div>
        </div>
      </div>
    );
  }

  function CasesPanel() {
    const [statusFilter, setStatusFilter] = useState<string>("pending");
    const [target, setTarget] = useState<SupportCase | null>(null);
    const [note, setNote] = useState("");

    const query = useQuery({
      queryKey: ["support", "cases", statusFilter],
      queryFn: () => supportApi.listCases(statusFilter || undefined),
      retry: false,
    });

    const resolve = useMutation({
      mutationFn: () => supportApi.resolveCase(target!.id, note.trim() || undefined),
      onSuccess: () => {
        setTarget(null);
        setNote("");
        toast.show({ tone: "success", title: t("caseResolved") });
        void qc.invalidateQueries({ queryKey: ["support", "cases"] });
      },
      onError: (e) => toast.show({ tone: "error", title: getMessage(e) }),
    });

    const columns: Column<SupportCase>[] = [
      { key: "resource_type", header: t("colResourceType"), cell: (r) => r.resource_type },
      {
        key: "severity",
        header: t("colSeverity"),
        cell: (r) => (
          <StatusBadge tone={CASE_SEVERITY_TONE[r.severity] ?? "info"}>
            {["low", "medium", "high"].includes(r.severity) ? t(`severity.${r.severity}`) : r.severity}
          </StatusBadge>
        ),
      },
      { key: "status", header: t("colStatus"), cell: (r) => r.status },
      {
        key: "created_at",
        header: t("colCreated"),
        cell: (r) => formatDateTime(r.created_at, locale),
      },
      {
        key: "actions",
        header: "",
        align: "right",
        cell: (r) => (
          <Button
            variant="ghost"
            size="sm"
            disabled={r.status !== "pending"}
            onClick={() => setTarget(r)}
          >
            <CheckCircle aria-hidden weight="bold" className="size-4" />
            {t("resolve")}
          </Button>
        ),
      },
    ];

    return (
      <div>
        <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label={t("filterLabel")}>
          {["pending", "resolved", ""].map((s) => (
            <button
              key={s || "all"}
              onClick={() => setStatusFilter(s)}
              aria-pressed={statusFilter === s}
              className={
                statusFilter === s
                  ? "rounded-full bg-[var(--text-primary)] px-3.5 py-1.5 text-xs font-semibold text-white"
                  : "rounded-full border border-[var(--border-default)] bg-white px-3.5 py-1.5 text-xs font-semibold text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              }
            >
              {s ? t(`status.${s}`) : tc("all")}
            </button>
          ))}
        </div>

        {query.isError ? (
          <PermissionOrErrorState error={query.error} onRetry={() => query.refetch()} />
        ) : (
          <DataTable
            columns={columns}
            rows={query.data ?? []}
            getRowId={(r) => r.id}
            loading={query.isPending}
            caption={t("tabs.cases")}
            empty={{ kind: "empty", icon: Tray, title: t("casesEmpty") }}
          />
        )}

        <Modal
          open={target !== null}
          onClose={() => setTarget(null)}
          title={t("resolveTitle")}
          size="sm"
          closeLabel={tc("close")}
          footer={
            <>
              <Button variant="ghost" onClick={() => setTarget(null)}>
                {tc("cancel")}
              </Button>
              <Button variant="primary" loading={resolve.isPending} onClick={() => resolve.mutate()}>
                {t("resolveConfirm")}
              </Button>
            </>
          }
        >
          <Textarea
            label={t("resolveNoteLabel")}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={3}
          />
        </Modal>
      </div>
    );
  }
}
