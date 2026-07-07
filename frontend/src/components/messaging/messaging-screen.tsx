"use client";

import { useEffect, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import {
  BellSlash,
  ChatsCircle,
  MagnifyingGlass,
  Megaphone,
  WifiSlash,
} from "@phosphor-icons/react";
import { Button, EmptyState, Skeleton } from "@/components/ui";
import { cn } from "@/lib/utils";
import { relativeTime } from "@/lib/notifications/grouping";
import { messagingApi, type ThreadSummary } from "@/lib/api";
import { MESSAGING_THREADS_KEY } from "./query-keys";
import { ThreadPanel } from "./thread-panel";

/**
 * Full-page two-column messaging workspace. Left rail: thread inbox. Right
 * pane: open thread or select-prompt. Adapts to mobile by hiding the list when
 * a thread is open.
 */
export function MessagingScreen({
  persona = "student",
  initialThreadId,
}: {
  persona?: "student" | "partner" | "university";
  /** Deep-link target (e.g. `?thread=<id>` from an application detail page). */
  initialThreadId?: string;
}) {
  const t = useTranslations("messaging");
  const tc = useTranslations("common");
  const tStates = useTranslations("states");
  const locale = useLocale();

  const [selected, setSelected] = useState<ThreadSummary | null>(null);
  const [search, setSearch] = useState("");
  const [pendingDeepLink, setPendingDeepLink] = useState(initialThreadId ?? null);

  // Deep-link: fetch the specific thread directly (it may not be on the first
  // inbox page) and select it once loaded. Falls through to the normal
  // auto-select-first behavior if the id is invalid/inaccessible.
  const deepLinkQuery = useQuery({
    queryKey: ["messaging", "thread", pendingDeepLink],
    queryFn: () => messagingApi.getThread(pendingDeepLink as string),
    enabled: Boolean(pendingDeepLink),
    retry: false,
  });

  useEffect(() => {
    if (!pendingDeepLink) return;
    if (deepLinkQuery.data) {
      setSelected(deepLinkQuery.data);
      setPendingDeepLink(null);
    } else if (deepLinkQuery.isError) {
      setPendingDeepLink(null);
    }
  }, [pendingDeepLink, deepLinkQuery.data, deepLinkQuery.isError]);

  const query = useInfiniteQuery({
    queryKey: MESSAGING_THREADS_KEY,
    queryFn: ({ pageParam }) =>
      messagingApi.listThreads({ cursor: pageParam, limit: 30 }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.page.next_cursor ?? undefined,
    refetchInterval: selected ? false : 30_000,
    refetchOnWindowFocus: true,
    staleTime: 15_000,
  });

  const threads: ThreadSummary[] = useMemo(
    () => query.data?.pages.flatMap((p) => p.data) ?? [],
    [query.data],
  );
  const normalizedSearch = search.trim().toLowerCase();
  const visibleThreads = useMemo(() => {
    if (!normalizedSearch) return threads;
    return threads.filter((thread) => {
      const haystack = [
        thread.counterpart_label,
        thread.subject,
        thread.context_label,
        thread.kind_label,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(normalizedSearch);
    });
  }, [normalizedSearch, threads]);
  const firstThread = threads[0] ?? null;
  const isLoading = query.isLoading;
  const isError = query.isError && threads.length === 0;
  const isEmpty = !isLoading && !isError && threads.length === 0;
  const noSearchResults =
    Boolean(normalizedSearch) && !isLoading && !isError && threads.length > 0 && visibleThreads.length === 0;
  const emptyBody = persona === "partner" ? t("partnerEmptyBody") : t("emptyBody");

  // Auto-select the first thread on desktop when inbox loads (skipped while a
  // deep-linked thread is still resolving).
  useEffect(() => {
    if (!selected && firstThread && !pendingDeepLink) {
      setSelected(firstThread);
    }
  }, [firstThread, selected, pendingDeepLink]);

  return (
    <div className="flex h-full min-h-[560px] flex-col">
      <div className="grid min-h-0 flex-1 overflow-hidden bg-white md:grid-cols-[340px_minmax(0,1fr)]">
        {/* ── Thread list (left rail) ── */}
        <aside
          className={cn(
            "flex w-full flex-col overflow-y-auto bg-white p-3 md:shrink-0 md:border-r md:border-[var(--border-default)]",
            selected && "hidden md:flex",
          )}
        >
          <div className="mb-3 border-b border-[var(--border-default)] px-1 pb-3">
            <div className="flex h-9 items-center justify-between">
              <h2 className="text-sm font-bold text-[var(--text-primary)]">
                {t("title")}
              </h2>
              {threads.length > 0 && (
                <span className="rounded-full bg-[var(--ops-canvas)] px-2 py-1 text-xs font-semibold text-[var(--text-secondary)] shadow-[inset_0_0_0_1px_rgba(0,0,0,0.055)]">
                  {threads.length}
                </span>
              )}
            </div>
            <label htmlFor="message-search" className="sr-only">
              {t("searchLabel")}
            </label>
            <div className="mt-2 flex h-9 items-center gap-2 rounded-full border border-[var(--border-default)] bg-[var(--ops-canvas)] px-3 text-[var(--text-secondary)] focus-within:border-[var(--border-strong)] focus-within:bg-[var(--surface-card)]">
              <MagnifyingGlass aria-hidden weight="bold" className="size-4 shrink-0" />
              <input
                id="message-search"
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={t("searchPlaceholder")}
                className="min-w-0 flex-1 bg-transparent text-sm font-medium text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)]"
              />
            </div>
          </div>

          {isLoading && <InboxSkeletons />}

          {isError && (
            <EmptyState
              kind="offline"
              icon={WifiSlash}
              title={tStates("offlineTitle")}
              description={t("offlineRetry")}
              action={
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => void query.refetch()}
                >
                  {tc("retry")}
                </Button>
              }
            />
          )}

          {isEmpty && (
            <EmptyState
              kind="empty"
              icon={ChatsCircle}
              title={t("emptyTitle")}
              description={emptyBody}
            />
          )}

          {noSearchResults && (
            <EmptyState
              kind="empty"
              icon={MagnifyingGlass}
              title={t("noSearchTitle")}
              description={t("noSearchBody")}
            />
          )}

          {visibleThreads.length > 0 && (
            <ul className="flex flex-col gap-1">
              {visibleThreads.map((th) => (
                <li key={th.id}>
                  <ThreadListRow
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
            "flex min-h-0 flex-col overflow-hidden bg-white",
            !selected && "hidden md:flex",
          )}
        >
          {selected ? (
            <ThreadPanel
              thread={selected}
              open
              onBack={() => setSelected(null)}
              onChanged={() => void query.refetch()}
            />
          ) : (
            <div className="flex flex-1 items-center justify-center p-8">
              <div className="text-center">
                <ChatsCircle
                  aria-hidden
                  weight="duotone"
                  className="mx-auto mb-3 size-12 text-[var(--text-muted)]"
                />
                <p className="text-sm font-medium text-[var(--text-secondary)]">
                  {t("emptyTitle")}
                </p>
                <p className="mt-1 text-xs text-[var(--text-muted)]">
                  {emptyBody}
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Thread list row ─────────────────────────────────────────────────────── */

function ThreadListRow({
  thread,
  locale,
  announcementLabel,
  active,
  onOpen,
}: {
  thread: ThreadSummary;
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
          ? "bg-white shadow-[inset_0_0_0_1px_rgba(0,0,0,0.055),0_1px_2px_rgba(0,0,0,0.03)] before:absolute before:left-1.5 before:top-3 before:h-[calc(100%-1.5rem)] before:w-1 before:rounded-full before:bg-[var(--text-primary)]"
          : "hover:bg-white focus-visible:bg-white",
        !active && unread && "bg-white/70",
      )}
    >
      <span
        className={cn(
          "mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-full shadow-[inset_0_0_0_1px_rgba(0,0,0,0.045)]",
          active || unread
            ? "bg-[var(--text-primary)] text-white"
            : "bg-[#f2f1ee] text-[var(--text-secondary)]",
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
            <span
              aria-hidden
              className="size-2 shrink-0 rounded-full bg-[#10a36f]"
            />
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
      </span>
    </button>
  );
}

function InboxSkeletons() {
  return (
    <div className="flex flex-col gap-2" aria-hidden>
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="flex items-start gap-3 px-2 py-2.5">
          <Skeleton className="size-9 rounded-xl" />
          <div className="flex-1">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="mt-2 h-3 w-full" />
          </div>
        </div>
      ))}
    </div>
  );
}
