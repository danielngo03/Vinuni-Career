"use client";

import { useEffect, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
  type InfiniteData,
} from "@tanstack/react-query";
import { AlertCircle, BellOff, ExternalLink } from "lucide-react";
import { Link } from "@/i18n/navigation";
import { Button, Skeleton } from "@/components/ui";
import { Card, EmptyState, PageHeader, StatusChip } from "@/components/kit";
import { cn } from "@/lib/utils";
import { groupByDay, relativeTime } from "@/lib/notifications/grouping";
import {
  notificationsApi,
  type Notification,
  type NotificationListResponse,
} from "@/lib/api";
import { NOTIFICATIONS_LIST_KEY, UNREAD_COUNT_KEY } from "./query-keys";
import { NotifIcon, notifCategoryKey } from "./notif-icon";

type ListData = InfiniteData<NotificationListResponse>;
type StatusFilter = "all" | "unread";

const CATEGORY_ORDER = [
  "application",
  "interview",
  "offer",
  "job",
  "event",
  "message",
  "advertising",
  "organization",
];

/**
 * Full-page notification center (v10 "Monochrome Shell + Data-viz Content").
 * A standard PageHeader + Card workspace inside the shared max-width/padding so
 * it reads with the same rhythm as every other partner/university surface: a
 * two-column layout (grouped feed left, detail right) with locked type scale,
 * design tokens, and honest loading/empty/error/unread states.
 */
export function NotificationScreen({
  headerActions,
}: {
  /** Optional persona-specific actions rendered in the PageHeader. */
  headerActions?: React.ReactNode;
}) {
  const t = useTranslations("notifications");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const qc = useQueryClient();

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [categoryFilter, setCategoryFilter] = useState<string>("all");

  const query = useInfiniteQuery({
    queryKey: NOTIFICATIONS_LIST_KEY,
    queryFn: ({ pageParam }) =>
      notificationsApi.list({ cursor: pageParam, limit: 40 }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.page.next_cursor ?? undefined,
    staleTime: 15_000,
  });

  const items: Notification[] = useMemo(
    () => query.data?.pages.flatMap((p) => p.data) ?? [],
    [query.data?.pages],
  );
  const unreadCount =
    query.data?.pages[0]?.meta.unread_count ??
    qc.getQueryData<number>(UNREAD_COUNT_KEY) ??
    0;
  const availableCategories = useMemo(() => {
    const keys = new Set<string>();
    for (const item of items) {
      const key = notifCategoryKey(item.notif_type);
      if (key) keys.add(key);
    }
    return Array.from(keys).sort((a, b) => {
      const ai = CATEGORY_ORDER.indexOf(a);
      const bi = CATEGORY_ORDER.indexOf(b);
      return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
    });
  }, [items]);
  const visibleItems = useMemo(() => {
    return items.filter((item) => {
      if (statusFilter === "unread" && item.is_read) return false;
      if (categoryFilter !== "all") {
        return notifCategoryKey(item.notif_type) === categoryFilter;
      }
      return true;
    });
  }, [categoryFilter, items, statusFilter]);
  const groups = groupByDay(visibleItems);
  const selected =
    visibleItems.find((item) => item.id === selectedId) ?? visibleItems[0] ?? null;
  const isLoading = query.isLoading;
  const isError = query.isError && items.length === 0;
  const isEmpty = !isLoading && !isError && items.length === 0;
  const hasActiveFilter = statusFilter !== "all" || categoryFilter !== "all";
  const noFilterResults =
    hasActiveFilter &&
    !isLoading &&
    !isError &&
    items.length > 0 &&
    visibleItems.length === 0;

  useEffect(() => {
    if (!visibleItems[0]) return;
    if (!selectedId || !visibleItems.some((item) => item.id === selectedId)) {
      setSelectedId(visibleItems[0].id);
    }
  }, [selectedId, visibleItems]);

  function patchRead(id: string) {
    qc.setQueryData<ListData>(NOTIFICATIONS_LIST_KEY, (prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        pages: prev.pages.map((page) => ({
          ...page,
          data: page.data.map((n) =>
            n.id === id && !n.is_read ? { ...n, is_read: true } : n,
          ),
        })),
      };
    });
  }

  function setUnread(count: number) {
    qc.setQueryData<number>(UNREAD_COUNT_KEY, count);
    qc.setQueryData<ListData>(NOTIFICATIONS_LIST_KEY, (prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        pages: prev.pages.map((page, i) =>
          i === 0
            ? { ...page, meta: { ...page.meta, unread_count: count } }
            : page,
        ),
      };
    });
  }

  const markRead = useMutation({
    mutationFn: (id: string) => notificationsApi.markRead(id),
    onMutate: (id) => {
      const wasUnread = items.find((n) => n.id === id && !n.is_read);
      patchRead(id);
      if (wasUnread) setUnread(Math.max(0, unreadCount - 1));
    },
    onSuccess: (res) => setUnread(res.unread_count),
    onError: () => {
      void qc.invalidateQueries({ queryKey: NOTIFICATIONS_LIST_KEY });
      void qc.invalidateQueries({ queryKey: UNREAD_COUNT_KEY });
    },
  });

  const markAll = useMutation({
    mutationFn: () => notificationsApi.markAllRead(),
    onMutate: () => {
      qc.setQueryData<ListData>(NOTIFICATIONS_LIST_KEY, (prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          pages: prev.pages.map((page) => ({
            ...page,
            data: page.data.map((n) => (n.is_read ? n : { ...n, is_read: true })),
          })),
        };
      });
      setUnread(0);
    },
    onError: () => {
      void qc.invalidateQueries({ queryKey: NOTIFICATIONS_LIST_KEY });
      void qc.invalidateQueries({ queryKey: UNREAD_COUNT_KEY });
    },
  });

  function selectNotification(item: Notification) {
    setSelectedId(item.id);
    if (!item.is_read) markRead.mutate(item.id);
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="mx-auto flex w-full min-h-0 max-w-7xl flex-1 flex-col px-4 py-5 lg:px-6">
        <PageHeader
          className="mb-4"
          title={t("title")}
          subtitle={
            unreadCount > 0
              ? t("unreadSummary", { count: unreadCount })
              : t("allCaughtUp")
          }
          actions={
            <div className="flex items-center gap-2">
              {unreadCount > 0 && (
                <Button
                  variant="secondary"
                  size="sm"
                  loading={markAll.isPending}
                  onClick={() => markAll.mutate()}
                >
                  {t("markAllRead")}
                </Button>
              )}
              {headerActions}
            </div>
          }
        />

        <Card className="grid min-h-0 flex-1 grid-rows-1 overflow-hidden p-0 md:grid-cols-[340px_minmax(0,1fr)]">
          {/* ── Feed (left rail) — always visible; detail pane is desktop-only ── */}
          <aside className="flex w-full min-h-0 flex-col overflow-y-auto p-3 md:shrink-0 md:border-r md:border-border">
            <div className="mb-3 border-b border-border px-1 pb-3">
              <div className="flex rounded-full bg-[var(--bg-muted)] p-1">
                <FilterButton
                  active={statusFilter === "all"}
                  onClick={() => setStatusFilter("all")}
                >
                  {t("filters.all")}
                </FilterButton>
                <FilterButton
                  active={statusFilter === "unread"}
                  onClick={() => setStatusFilter("unread")}
                >
                  {t("filters.unread")}
                  {unreadCount > 0 && (
                    <span className="ml-1.5 tabular-nums text-muted-foreground">
                      {unreadCount > 99 ? "99+" : unreadCount}
                    </span>
                  )}
                </FilterButton>
              </div>
              {availableCategories.length > 0 && (
                <div className="mt-2 flex gap-1.5 overflow-x-auto pb-0.5">
                  <CategoryFilterButton
                    active={categoryFilter === "all"}
                    onClick={() => setCategoryFilter("all")}
                  >
                    {t("filters.allTypes")}
                  </CategoryFilterButton>
                  {availableCategories.map((key) => (
                    <CategoryFilterButton
                      key={key}
                      active={categoryFilter === key}
                      onClick={() => setCategoryFilter(key)}
                    >
                      {t(`categories.${key}`)}
                    </CategoryFilterButton>
                  ))}
                </div>
              )}
            </div>

            {isLoading && <NotificationSkeletons />}

            {isError && (
              <EmptyState
                kind="error"
                icon={AlertCircle}
                title={tStates("errorTitle")}
                description={tStates("errorBody")}
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
                icon={BellOff}
                title={t("emptyTitle")}
                description={t("emptyBody")}
              />
            )}

            {noFilterResults && (
              <EmptyState
                kind="empty"
                icon={BellOff}
                title={t("noFilterTitle")}
                description={t("noFilterBody")}
              />
            )}

            {!isLoading && !isError && visibleItems.length > 0 && (
              <div className="flex flex-col gap-4">
                {groups.map((group) => (
                  <section
                    key={group.bucket}
                    aria-label={t(`groups.${group.bucket}`)}
                  >
                    <h3 className="px-2 pb-1.5 type-caption font-semibold uppercase tracking-[0.06em] text-muted-foreground">
                      {t(`groups.${group.bucket}`)}
                    </h3>
                    <ul className="flex flex-col gap-0.5">
                      {group.items.map((item) => (
                        <li key={item.id}>
                          <NotificationListRow
                            notification={item}
                            locale={locale}
                            active={selected?.id === item.id}
                            onSelect={() => selectNotification(item)}
                          />
                        </li>
                      ))}
                    </ul>
                  </section>
                ))}
                {query.hasNextPage && (
                  <Button
                    variant="ghost"
                    size="sm"
                    fullWidth
                    loading={query.isFetchingNextPage}
                    disabled={query.isFetchingNextPage}
                    onClick={() => void query.fetchNextPage()}
                  >
                    {tc("loadMore")}
                  </Button>
                )}
              </div>
            )}
          </aside>

          {/* ── Detail (right pane) — desktop-only, mirrors the original ── */}
          <main className="hidden min-h-0 flex-col overflow-y-auto bg-card md:flex">
            {selected ? (
              <NotificationDetail notification={selected} locale={locale} />
            ) : (
              <div className="flex flex-1 items-center justify-center p-8">
                <EmptyState
                  kind="empty"
                  icon={BellOff}
                  title={t("detailEmptyTitle")}
                  description={t("detailEmptyBody")}
                  className="border-0 bg-transparent"
                />
              </div>
            )}
          </main>
        </Card>
      </div>
    </div>
  );
}

function NotificationListRow({
  notification,
  locale,
  active,
  onSelect,
}: {
  notification: Notification;
  locale: string;
  active: boolean;
  onSelect: () => void;
}) {
  const t = useTranslations("notifications");
  const unread = !notification.is_read;
  const ts = relativeTime(notification.created_at, locale);
  const categoryKey = notifCategoryKey(notification.notif_type);

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={active ? "true" : undefined}
      className={cn(
        "flex w-full cursor-pointer items-start gap-3 rounded-[10px] px-2.5 py-2.5 text-left outline-none transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]",
        active
          ? "bg-[var(--bg-muted)] shadow-[inset_0_0_0_1px_var(--border-subtle)]"
          : "hover:bg-[var(--bg-subtle)] focus-visible:bg-[var(--bg-subtle)]",
      )}
    >
      <NotifIcon type={notification.notif_type} />
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5">
          {unread && (
            <span
              aria-hidden
              className="size-1.5 shrink-0 rounded-full"
              style={{ background: "var(--viz-indigo)" }}
            />
          )}
          <span
            className={cn(
              "min-w-0 flex-1 truncate type-body text-foreground",
              unread || active ? "font-semibold" : "font-medium",
            )}
          >
            {notification.title}
          </span>
          {ts && (
            <time
              dateTime={notification.created_at}
              className="shrink-0 type-caption tabular-nums text-muted-foreground"
            >
              {ts}
            </time>
          )}
        </span>
        <span className="mt-0.5 flex items-center gap-1.5">
          {categoryKey && (
            <StatusChip tone="neutral" size="sm">
              {t(`categories.${categoryKey}`)}
            </StatusChip>
          )}
          <span className="min-w-0 flex-1 truncate type-small text-muted-foreground">
            {notification.body}
          </span>
        </span>
      </span>
    </button>
  );
}

function FilterButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "flex h-8 flex-1 cursor-pointer items-center justify-center rounded-full px-3 type-small font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]",
        active
          ? "bg-card text-foreground shadow-[var(--shadow-sm)]"
          : "text-muted-foreground hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

function CategoryFilterButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "h-7 shrink-0 cursor-pointer rounded-full px-2.5 type-caption font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]",
        active
          ? "bg-[var(--bg-muted)] text-foreground shadow-[inset_0_0_0_1px_var(--border-subtle)]"
          : "text-muted-foreground hover:bg-[var(--bg-subtle)] hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

function NotificationDetail({
  notification,
  locale,
}: {
  notification: Notification;
  locale: string;
}) {
  const t = useTranslations("notifications");
  const categoryKey = notifCategoryKey(notification.notif_type);
  const ts = relativeTime(notification.created_at, locale);

  return (
    <article className="mx-auto flex w-full max-w-2xl flex-1 flex-col px-6 py-8">
      <div className="flex items-start gap-4">
        <NotifIcon type={notification.notif_type} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            {categoryKey && (
              <StatusChip tone="neutral" size="sm">
                {t(`categories.${categoryKey}`)}
              </StatusChip>
            )}
            {ts && (
              <time
                dateTime={notification.created_at}
                className="type-caption tabular-nums text-muted-foreground"
              >
                {ts}
              </time>
            )}
          </div>
          <h2 className="mt-3 type-h2 text-balance text-foreground">
            {notification.title}
          </h2>
          <p className="mt-2 type-body leading-6 text-muted-foreground">
            {notification.body}
          </p>
          {notification.action_url && (
            <div className="mt-5">
              <Link
                href={notification.action_url}
                className="inline-flex h-9 items-center gap-2 rounded-lg bg-foreground px-4 type-small font-semibold text-card outline-none transition-opacity hover:opacity-90 focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
              >
                {t("openAction")}
                <ExternalLink aria-hidden strokeWidth={1.9} className="size-4" />
              </Link>
            </div>
          )}
        </div>
      </div>
    </article>
  );
}

function NotificationSkeletons() {
  return (
    <div className="flex flex-col gap-2" aria-hidden>
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="flex items-start gap-3 px-2.5 py-2.5">
          <Skeleton className="size-9 rounded-xl" />
          <div className="flex-1">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="mt-2 h-3 w-full" />
          </div>
        </div>
      ))}
    </div>
  );
}
