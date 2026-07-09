"use client";

import { useEffect, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import {
  BellSlash,
  ChatsCircle,
  Megaphone,
  PencilSimpleLine,
  ShieldWarning,
  WifiSlash,
} from "@phosphor-icons/react";
import { Button, EmptyState, SegmentedControl, Skeleton } from "@/components/ui";
import { cn } from "@/lib/utils";
import { relativeTime } from "@/lib/notifications/grouping";
import {
  ApiError,
  messagingApi,
  organizationApi,
  type InboxScope,
  type InboxThreadSummary,
} from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";
import { messagingInboxKey } from "./query-keys";
import { ThreadPanel } from "./thread-panel";
import { NewMessageModal } from "./new-message-modal";
import { RequestChip, AssignmentChip } from "./thread-chips";
import { useMyOrgIdentity } from "./use-my-org";
import { useMessagingRealtime } from "./use-messaging-socket";

const SCOPES: InboxScope[] = ["unassigned", "mine", "all", "resolved"];

/**
 * Organization shared inbox for partner + university personas. The team queue:
 * filter by scope (Unassigned / Mine / All / Resolved) + department + search,
 * open a thread to read + reply, and route (Assign) or Resolve it. Threads belong
 * to the ORG; identity is the server label only.
 */
export function OrgInboxScreen({
  persona,
  headerExtra,
}: {
  persona: "partner" | "university";
  /** Optional extra header action (e.g. university "New announcement"). */
  headerExtra?: React.ReactNode;
}) {
  const t = useTranslations("messaging");
  const tc = useTranslations("common");
  const tStates = useTranslations("states");
  const locale = useLocale();
  const permissions = useAuthStore((s) => s.user?.permissions ?? []);
  const isSuperadmin = useAuthStore((s) => s.user?.isSuperadmin ?? false);
  const orgIdentity = useMyOrgIdentity();
  useMessagingRealtime();

  const canAssign =
    isSuperadmin ||
    permissions.includes("*") ||
    permissions.includes("*:*") ||
    permissions.includes("messaging:assign") ||
    permissions.includes("messaging:*");

  const [scope, setScope] = useState<InboxScope>("unassigned");
  const [departmentId, setDepartmentId] = useState<string>("");
  const [searchInput, setSearchInput] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [selected, setSelected] = useState<InboxThreadSummary | null>(null);
  const [composeOpen, setComposeOpen] = useState(false);

  useEffect(() => {
    const id = window.setTimeout(() => setDebouncedSearch(searchInput.trim()), 300);
    return () => window.clearTimeout(id);
  }, [searchInput]);

  const departmentsQuery = useQuery({
    queryKey: ["messaging", "inbox-departments"],
    queryFn: () => organizationApi.listDepartments(),
    staleTime: 5 * 60_000,
    retry: false,
  });

  const query = useInfiniteQuery({
    queryKey: messagingInboxKey({ scope, departmentId: departmentId || null, q: debouncedSearch }),
    queryFn: ({ pageParam }) =>
      messagingApi.listInbox({
        scope,
        departmentId: departmentId || null,
        q: debouncedSearch || null,
        cursor: pageParam,
        limit: 30,
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.page.next_cursor ?? undefined,
    refetchInterval: selected ? false : 30_000,
    refetchOnWindowFocus: true,
    staleTime: 15_000,
    retry: (count, err) =>
      err instanceof ApiError && err.isPermissionError ? false : count < 2,
  });

  const threads: InboxThreadSummary[] = useMemo(
    () => query.data?.pages.flatMap((p) => p.data) ?? [],
    [query.data],
  );

  // Keep the open thread's row data fresh (unread/assignment) as the list polls.
  useEffect(() => {
    if (!selected) return;
    const fresh = threads.find((th) => th.id === selected.id);
    if (fresh && fresh !== selected) setSelected(fresh);
  }, [threads, selected]);

  const permissionDenied =
    query.isError && query.error instanceof ApiError && query.error.isPermissionError;
  const isLoading = query.isLoading;
  const isError = query.isError && !permissionDenied && threads.length === 0;
  const isEmpty = !isLoading && !isError && !permissionDenied && threads.length === 0;

  const scopeOptions = SCOPES.map((s) => ({
    value: s,
    label: t(
      s === "unassigned"
        ? "inboxScopeUnassigned"
        : s === "mine"
          ? "inboxScopeMine"
          : s === "all"
            ? "inboxScopeAll"
            : "inboxScopeResolved",
    ),
  }));

  const departmentOptions = [
    { value: "", label: t("inboxDepartmentAll") },
    ...(departmentsQuery.data ?? []).map((d) => ({ value: d.id, label: d.name })),
  ];

  const emptyBody =
    scope === "unassigned"
      ? t("inboxEmptyUnassigned")
      : scope === "resolved"
        ? t("inboxEmptyResolved")
        : t("inboxEmptyBody");

  return (
    <div className="flex h-full min-h-[560px] flex-col">
      <div className="grid min-h-0 flex-1 overflow-hidden bg-[var(--surface-card)] md:grid-cols-[360px_minmax(0,1fr)]">
        {/* ── Inbox list (left rail) ── */}
        <aside
          className={cn(
            "flex w-full flex-col overflow-y-auto bg-[var(--surface-card)] p-3 md:shrink-0 md:border-r md:border-[var(--border-default)]",
            selected && "hidden md:flex",
          )}
        >
          <div className="mb-2 flex items-center justify-between gap-2 px-1">
            <h2 className="text-sm font-bold text-[var(--text-primary)]">
              {t("inboxTitle")}
            </h2>
            <div className="flex items-center gap-1.5">
              {headerExtra}
              <Button variant="primary" size="xs" onClick={() => setComposeOpen(true)}>
                <PencilSimpleLine aria-hidden weight="bold" className="size-3.5" />
                {t("newMessage")}
              </Button>
            </div>
          </div>

          {/* Filters */}
          <div className="mb-3 space-y-2 border-b border-[var(--border-default)] px-1 pb-3">
            <div className="overflow-x-auto">
              <SegmentedControl
                value={scope}
                onValueChange={(v) => {
                  setScope(v as InboxScope);
                  setSelected(null);
                }}
                options={scopeOptions}
                ariaLabel={t("inboxScopeLabel")}
                size="sm"
              />
            </div>
            <div className="flex flex-col gap-2 sm:flex-row">
              <div className="sm:w-1/2">
                <label htmlFor="inbox-dept" className="sr-only">
                  {t("inboxDepartmentLabel")}
                </label>
                <select
                  id="inbox-dept"
                  value={departmentId}
                  onChange={(e) => {
                    setDepartmentId(e.target.value);
                    setSelected(null);
                  }}
                  className="h-9 w-full appearance-none rounded-lg border border-[var(--border-default)] bg-[var(--bg-subtle)] px-2.5 text-xs font-medium text-[var(--text-primary)] outline-none focus:border-[var(--border-strong)] focus:bg-[var(--surface-card)]"
                >
                  {departmentOptions.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex h-9 flex-1 items-center gap-2 rounded-lg border border-[var(--border-default)] bg-[var(--bg-subtle)] px-2.5 text-[var(--text-secondary)] focus-within:border-[var(--border-strong)] focus-within:bg-[var(--surface-card)]">
                <label htmlFor="inbox-search" className="sr-only">
                  {t("searchLabel")}
                </label>
                <input
                  id="inbox-search"
                  type="search"
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                  placeholder={t("inboxSearchPlaceholder")}
                  className="min-w-0 flex-1 bg-transparent text-xs font-medium text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)]"
                />
              </div>
            </div>
          </div>

          {permissionDenied && (
            <EmptyState
              kind="permission"
              icon={ShieldWarning}
              title={t("inboxPermissionTitle")}
              description={t("inboxPermissionBody")}
            />
          )}

          {isLoading && <InboxSkeletons />}

          {isError && (
            <EmptyState
              kind="offline"
              icon={WifiSlash}
              title={tStates("offlineTitle")}
              description={t("offlineRetry")}
              action={
                <Button variant="secondary" size="sm" onClick={() => void query.refetch()}>
                  {tc("retry")}
                </Button>
              }
            />
          )}

          {isEmpty && (
            <EmptyState
              kind="empty"
              icon={ChatsCircle}
              title={t("inboxEmptyTitle")}
              description={emptyBody}
            />
          )}

          {threads.length > 0 && (
            <ul className="flex flex-col gap-1">
              {threads.map((th) => (
                <li key={th.id}>
                  <InboxRow
                    thread={th}
                    locale={locale}
                    announcementLabel={t("announcement")}
                    active={selected?.id === th.id}
                    onOpen={() => setSelected(th)}
                  />
                </li>
              ))}
              {query.hasNextPage && (
                <Button
                  variant="ghost"
                  size="sm"
                  fullWidth
                  loading={query.isFetchingNextPage}
                  onClick={() => void query.fetchNextPage()}
                >
                  {tc("loadMore")}
                </Button>
              )}
            </ul>
          )}
        </aside>

        {/* ── Thread detail (right pane) ── */}
        <div
          className={cn(
            "flex min-h-0 flex-col overflow-hidden bg-[var(--surface-card)]",
            !selected && "hidden md:flex",
          )}
        >
          {selected ? (
            <ThreadPanel
              key={selected.id}
              thread={selected}
              open
              variant="org"
              orgIdentity={orgIdentity}
              canAssign={canAssign}
              onBack={() => setSelected(null)}
              onChanged={() => void query.refetch()}
              onAssignmentChanged={() => void query.refetch()}
            />
          ) : (
            <div className="hidden flex-1 items-center justify-center p-8 md:flex">
              <div className="text-center">
                <ChatsCircle
                  aria-hidden
                  weight="duotone"
                  className="mx-auto mb-3 size-12 text-[var(--text-muted)]"
                />
                <p className="text-sm font-medium text-[var(--text-secondary)]">
                  {t("inboxSelectTitle")}
                </p>
                <p className="mt-1 text-xs text-[var(--text-muted)]">
                  {t("inboxSelectBody")}
                </p>
              </div>
            </div>
          )}
        </div>
      </div>

      <NewMessageModal
        open={composeOpen}
        onClose={() => setComposeOpen(false)}
        persona={persona}
        onCreated={(thread) => {
          void query.refetch();
          setSelected(thread as InboxThreadSummary);
        }}
      />
    </div>
  );
}

/* ---------------------------------- Row ----------------------------------- */

function InboxRow({
  thread,
  locale,
  announcementLabel,
  active,
  onOpen,
}: {
  thread: InboxThreadSummary;
  locale: string;
  announcementLabel: string;
  active: boolean;
  onOpen: () => void;
}) {
  const unread = thread.unread > 0;
  const ts = relativeTime(thread.last_message_at ?? "", locale);
  const secondary = thread.subject || thread.context_label || thread.kind_label;
  const isAnnouncement = thread.kind === "announcement";

  return (
    <button
      type="button"
      onClick={onOpen}
      className={cn(
        "relative flex w-full cursor-pointer items-start gap-3 rounded-[16px] px-3 py-3 text-left outline-none transition-colors duration-200",
        active
          ? "bg-[var(--surface-card)] shadow-[inset_0_0_0_1px_rgba(0,0,0,0.055),0_1px_2px_rgba(0,0,0,0.03)] before:absolute before:left-1.5 before:top-3 before:h-[calc(100%-1.5rem)] before:w-1 before:rounded-full before:bg-[var(--text-primary)]"
          : "hover:bg-[var(--bg-subtle)] focus-visible:bg-[var(--bg-subtle)]",
      )}
    >
      <span
        className={cn(
          "mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-full shadow-[inset_0_0_0_1px_rgba(0,0,0,0.045)]",
          active || unread
            ? "bg-[var(--text-primary)] text-white"
            : "bg-[var(--bg-muted)] text-[var(--text-secondary)]",
        )}
      >
        {isAnnouncement ? (
          <Megaphone aria-hidden weight="duotone" className="size-[18px]" />
        ) : (
          <ChatsCircle aria-hidden weight="duotone" className="size-[18px]" />
        )}
      </span>

      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5">
          {unread && (
            <span aria-hidden className="size-2 shrink-0 rounded-full bg-[#10a36f]" />
          )}
          <span
            className={cn(
              "min-w-0 flex-1 truncate text-sm text-[var(--text-primary)]",
              unread ? "font-bold" : "font-semibold",
            )}
          >
            {thread.counterpart_label}
          </span>
          {thread.muted && (
            <BellSlash
              aria-label="muted"
              weight="bold"
              className="size-3.5 shrink-0 text-[var(--text-muted)]"
            />
          )}
          {ts && (
            <time
              dateTime={thread.last_message_at ?? undefined}
              className="shrink-0 text-[10px] text-[var(--text-muted)]"
            >
              {ts}
            </time>
          )}
        </span>
        <span className="mt-0.5 flex items-center gap-1.5">
          {isAnnouncement && (
            <span className="shrink-0 text-[10px] font-bold uppercase tracking-[0.08em] text-[var(--text-muted)]">
              {announcementLabel}
            </span>
          )}
          <span className="min-w-0 flex-1 truncate text-xs text-[var(--text-secondary)]">
            {secondary}
          </span>
          {unread && (
            <span className="shrink-0 rounded-full bg-[#e6f7ef] px-1.5 text-[10px] font-bold leading-4 text-[#0d7f59]">
              {thread.unread > 99 ? "99+" : thread.unread}
            </span>
          )}
        </span>
        <span className="mt-1.5 flex flex-wrap items-center gap-1">
          <AssignmentChip state={thread.assignment_state} />
          <RequestChip state={thread.request_state} label={thread.request_label} />
        </span>
      </span>
    </button>
  );
}

function InboxSkeletons() {
  return (
    <div className="flex flex-col gap-2" aria-hidden>
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="flex items-start gap-3 px-2 py-2.5">
          <Skeleton className="size-9 rounded-xl" />
          <div className="flex-1">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="mt-2 h-3 w-full" />
            <Skeleton className="mt-2 h-3 w-1/3" />
          </div>
        </div>
      ))}
    </div>
  );
}
