"use client";

import { useEffect, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import {
  BellSlash,
  WarningCircle,
} from "@phosphor-icons/react";
import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
  type InfiniteData,
} from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { Link } from "@/i18n/navigation";
import { Button, EmptyState, Skeleton } from "@/components/ui";
import { cn } from "@/lib/utils";
import { groupByDay, relativeTime } from "@/lib/notifications/grouping";
import {
  notificationsApi,
  type Notification,
  type NotificationListResponse,
} from "@/lib/api";
import {
  NOTIFICATIONS_LIST_KEY,
  UNREAD_COUNT_KEY,
} from "./query-keys";
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

export function NotificationScreen() {
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
            data: page.data.map((n) =>
              n.is_read ? n : { ...n, is_read: true },
            ),
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
    <div className="flex h-full min-h-[560px] flex-col">
      <div className="grid min-h-0 flex-1 overflow-hidden bg-white md:grid-cols-[380px_minmax(0,1fr)]">
        <aside className="flex w-full flex-col overflow-y-auto bg-white p-3 md:border-r md:border-[var(--border-default)]">
          <div className="mb-3 border-b border-[var(--border-default)] px-1 pb-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h2 className="text-sm font-bold text-[var(--text-primary)]">
                  {t("title")}
                </h2>
                <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
                  {unreadCount > 0
                    ? t("unreadSummary", { count: unreadCount })
                    : t("allCaughtUp")}
                </p>
              </div>
              {unreadCount > 0 && (
                <button
                  type="button"
                  disabled={markAll.isPending}
                  onClick={() => markAll.mutate()}
                  className="h-8 shrink-0 cursor-pointer rounded-full px-2.5 text-xs font-semibold text-[var(--text-secondary)] outline-none transition-colors hover:bg-[#f2f1ee] hover:text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
                >
                  {t("markAllRead")}
                </button>
              )}
            </div>
            <div className="mt-3 flex rounded-full bg-[#f7f6f2] p-1">
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
                  <span className="ml-1 rounded-full bg-white/90 px-1.5 text-[10px] leading-4 text-[var(--text-primary)]">
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
              icon={WarningCircle}
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
              icon={BellSlash}
              title={t("emptyTitle")}
              description={t("emptyBody")}
            />
          )}

          {noFilterResults && (
            <EmptyState
              kind="empty"
              icon={BellSlash}
              title={t("noFilterTitle")}
              description={t("noFilterBody")}
            />
          )}

          {!isLoading && !isError && visibleItems.length > 0 && (
            <div className="flex flex-col gap-5">
              {groups.map((group) => (
                <section key={group.bucket} aria-label={t(`groups.${group.bucket}`)}>
                  <h3 className="px-2 pb-2 text-[11px] font-bold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                    {t(`groups.${group.bucket}`)}
                  </h3>
                  <ul className="flex flex-col gap-1">
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

        <main className="hidden min-h-0 flex-col overflow-y-auto bg-white md:flex">
          {selected ? (
            <NotificationDetail notification={selected} locale={locale} />
          ) : (
            <div className="flex flex-1 items-center justify-center p-8">
              <EmptyState
                kind="empty"
                icon={BellSlash}
                title={t("detailEmptyTitle")}
                description={t("detailEmptyBody")}
                className="border-0 bg-transparent"
              />
            </div>
          )}
        </main>
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
      className={cn(
        "relative flex w-full cursor-pointer items-start gap-3 rounded-[14px] px-3 py-2.5 text-left outline-none transition-colors duration-200",
        active
          ? "bg-[#f7f6f2] shadow-[inset_0_0_0_1px_rgba(0,0,0,0.055)]"
          : "hover:bg-[#f7f6f2] focus-visible:bg-[#f7f6f2]",
        unread && !active && "bg-white",
      )}
    >
      <NotifIcon type={notification.notif_type} active={unread || active} />
      <span className="min-w-0 flex-1">
        <span className="flex items-start gap-2">
          {unread && (
            <span
              aria-hidden
              className="mt-[0.45rem] size-2 shrink-0 rounded-full bg-[#10a36f]"
            />
          )}
          <span
            className={cn(
              "min-w-0 flex-1 truncate text-sm text-[var(--text-primary)]",
              unread ? "font-bold" : "font-semibold",
            )}
          >
            {notification.title}
          </span>
          {ts && (
            <time
              dateTime={notification.created_at}
              className="shrink-0 text-xs text-[var(--text-muted)]"
            >
              {ts}
            </time>
          )}
        </span>
        <span className="mt-0.5 line-clamp-1 block text-sm leading-5 text-[var(--text-secondary)]">
          {notification.body}
        </span>
        {categoryKey && (
          <span className="mt-1 block text-[10px] font-bold uppercase tracking-[0.08em] text-[var(--text-muted)]">
            {t(`categories.${categoryKey}`)}
          </span>
        )}
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
        "flex h-8 flex-1 cursor-pointer items-center justify-center rounded-full px-3 text-xs font-bold outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30",
        active
          ? "bg-[var(--text-primary)] text-white shadow-[0_6px_14px_rgba(0,0,0,0.1)]"
          : "text-[var(--text-secondary)] hover:bg-white hover:text-[var(--text-primary)]",
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
        "h-7 shrink-0 cursor-pointer rounded-full px-2.5 text-[11px] font-bold outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30",
        active
          ? "bg-[#f2f1ee] text-[var(--text-primary)] shadow-[inset_0_0_0_1px_rgba(0,0,0,0.08)]"
          : "text-[var(--text-muted)] hover:bg-[#f7f6f2] hover:text-[var(--text-primary)]",
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
    <article className="mx-auto flex w-full max-w-3xl flex-1 flex-col px-8 py-10">
      <div className="flex items-start gap-4">
        <NotifIcon type={notification.notif_type} active={!notification.is_read} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            {categoryKey && (
              <span className="rounded-full bg-[#f2f1ee] px-2 py-1 text-[10px] font-bold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                {t(`categories.${categoryKey}`)}
              </span>
            )}
            {ts && (
              <time
                dateTime={notification.created_at}
                className="text-xs font-medium text-[var(--text-muted)]"
              >
                {ts}
              </time>
            )}
          </div>
          <h1 className="mt-4 text-2xl font-bold tracking-tight text-[var(--text-primary)]">
            {notification.title}
          </h1>
          <p className="mt-3 text-base leading-7 text-[var(--text-secondary)]">
            {notification.body}
          </p>
          {notification.action_url && (
            <div className="mt-6">
              <Link
                href={notification.action_url}
                className="inline-flex h-10 items-center gap-2 rounded-full bg-[var(--text-primary)] px-4 text-sm font-semibold text-white outline-none transition-colors hover:bg-black focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/35"
              >
                {t("openAction")}
                <ExternalLink aria-hidden strokeWidth={1.8} className="size-4" />
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
    <div className="flex flex-col gap-3" aria-hidden>
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="flex items-start gap-3 px-3 py-3">
          <Skeleton className="size-9 rounded-full" />
          <div className="flex-1">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="mt-2 h-3 w-full" />
            <Skeleton className="mt-1.5 h-3 w-1/3" />
          </div>
        </div>
      ))}
    </div>
  );
}
