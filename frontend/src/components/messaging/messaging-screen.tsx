"use client";

import { useEffect, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { BellOff, MessagesSquare, Search, WifiOff } from "lucide-react";
import { Button, Input, Skeleton } from "@/components/ui";
import { Card, EmptyState, StatusChip } from "@/components/kit";
import { cn } from "@/lib/utils";
import { relativeTime } from "@/lib/notifications/grouping";
import { messagingApi, type ThreadSummary } from "@/lib/api";
import { MESSAGING_THREADS_KEY } from "./query-keys";
import { ThreadPanel } from "./thread-panel";
import { ThreadAvatar } from "./thread-bits";

/**
 * Full-page two-column messaging workspace. Left rail: thread inbox. Right
 * pane: open thread or select-prompt. Adapts to mobile by hiding the list when
 * a thread is open. v10 "Monochrome Shell + Data-viz Content": the workspace is
 * a single Card panel; rows use a subtle active pill matching the sidebar, and
 * counterparty avatars carry soft data-viz tints while chrome stays mono.
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
      <Card className="grid min-h-0 flex-1 grid-rows-1 overflow-hidden p-0 md:grid-cols-[340px_minmax(0,1fr)]">
        {/* ── Thread list (left rail) ── */}
        <aside
          className={cn(
            "flex w-full min-h-0 flex-col overflow-y-auto p-3 md:shrink-0 md:border-r md:border-border",
            selected && "hidden md:flex",
          )}
        >
          <div className="mb-3 border-b border-border px-1 pb-3">
            <div className="flex h-9 items-center justify-between">
              <h2 className="type-body font-semibold text-foreground">
                {t("title")}
              </h2>
              {threads.length > 0 && (
                <span className="inline-flex min-w-5 items-center justify-center rounded-full bg-[var(--bg-muted)] px-1.5 py-0.5 type-caption font-semibold tabular-nums text-muted-foreground">
                  {threads.length}
                </span>
              )}
            </div>
            <div className="relative mt-2">
              <Search
                aria-hidden
                strokeWidth={1.8}
                className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
              />
              <label htmlFor="message-search" className="sr-only">
                {t("searchLabel")}
              </label>
              <Input
                id="message-search"
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={t("searchPlaceholder")}
                className="h-9 rounded-full py-0 pl-9"
              />
            </div>
          </div>

          {isLoading && <InboxSkeletons />}

          {isError && (
            <EmptyState
              kind="offline"
              icon={WifiOff}
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
              icon={MessagesSquare}
              title={t("emptyTitle")}
              description={emptyBody}
            />
          )}

          {noSearchResults && (
            <EmptyState
              kind="empty"
              icon={Search}
              title={t("noSearchTitle")}
              description={t("noSearchBody")}
            />
          )}

          {visibleThreads.length > 0 && (
            <ul className="flex flex-col gap-0.5">
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
            "flex min-h-0 flex-col overflow-hidden bg-card",
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
              <EmptyState
                kind="empty"
                icon={MessagesSquare}
                title={t("emptyTitle")}
                description={emptyBody}
                className="border-0 bg-transparent"
              />
            </div>
          )}
        </div>
      </Card>
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
      aria-current={active ? "true" : undefined}
      className={cn(
        "flex w-full cursor-pointer items-start gap-3 rounded-[10px] px-2.5 py-2.5 text-left outline-none transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]",
        active
          ? "bg-[var(--bg-muted)] shadow-[inset_0_0_0_1px_var(--border-subtle)]"
          : "hover:bg-[var(--bg-subtle)] focus-visible:bg-[var(--bg-subtle)]",
      )}
    >
      <ThreadAvatar label={thread.counterpart_label} announcement={isAnnouncement} />

      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5">
          <span
            className={cn(
              "min-w-0 flex-1 truncate type-body text-foreground",
              unread || active ? "font-semibold" : "font-medium",
            )}
          >
            {thread.counterpart_label}
          </span>
          {thread.muted && (
            <BellOff
              aria-label="muted"
              strokeWidth={1.8}
              className="size-3.5 shrink-0 text-muted-foreground"
            />
          )}
          {ts && (
            <time
              dateTime={thread.last_message_at ?? undefined}
              className="shrink-0 type-caption tabular-nums text-muted-foreground"
            >
              {ts}
            </time>
          )}
        </span>
        <span className="mt-0.5 flex items-center gap-1.5">
          {isAnnouncement && (
            <StatusChip tone="amber" size="sm">
              {announcementLabel}
            </StatusChip>
          )}
          <span className="min-w-0 flex-1 truncate type-small text-muted-foreground">
            {secondary}
          </span>
          {unread && (
            <StatusChip tone="indigo" size="sm" className="tabular-nums">
              {thread.unread > 99 ? "99+" : thread.unread}
            </StatusChip>
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
          <Skeleton className="size-10 rounded-xl" />
          <div className="flex-1">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="mt-2 h-3 w-full" />
          </div>
        </div>
      ))}
    </div>
  );
}
