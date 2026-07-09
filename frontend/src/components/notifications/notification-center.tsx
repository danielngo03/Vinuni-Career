"use client";

import { useEffect } from "react";
import { useLocale, useTranslations } from "next-intl";
import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
  type InfiniteData,
} from "@tanstack/react-query";
import { AlertCircle, BellOff, X } from "lucide-react";
import { Link } from "@/i18n/navigation";
import { Button, Skeleton } from "@/components/ui";
import { EmptyState, StatusChip } from "@/components/kit";
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

export interface NotificationCenterProps {
  open: boolean;
  onClose: () => void;
}

/**
 * Bell-center panel (v10). Renders the cursor-paginated feed grouped by
 * Today / Yesterday / Older, with optimistic mark-read on row click and a
 * mark-all-as-read action. The unread badge lives on the trigger (NotificationBell);
 * both read the shared UNREAD_COUNT_KEY cache so they stay in sync.
 */
export function NotificationCenter({ open, onClose }: NotificationCenterProps) {
  const t = useTranslations("notifications");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const qc = useQueryClient();

  const query = useInfiniteQuery({
    queryKey: NOTIFICATIONS_LIST_KEY,
    queryFn: ({ pageParam }) =>
      notificationsApi.list({ cursor: pageParam, limit: 20 }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.page.next_cursor ?? undefined,
    enabled: open,
    staleTime: 15_000,
  });

  // Refetch the feed each time the panel opens so it reflects the latest badge.
  useEffect(() => {
    if (open) void query.refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (!open) return;

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  const items: Notification[] = query.data?.pages.flatMap((p) => p.data) ?? [];
  const unreadCount =
    query.data?.pages[0]?.meta.unread_count ??
    qc.getQueryData<number>(UNREAD_COUNT_KEY) ??
    0;

  /** Optimistically flip one row to read across every cached page. */
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
      // Reconcile from the server on failure (no fabricated state).
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

  /** Row click: mark read first (optimistic, synchronous cache write), then nav. */
  function onRowActivate(n: Notification, navigates: boolean) {
    if (!n.is_read) markRead.mutate(n.id);
    if (navigates) onClose();
  }

  const groups = groupByDay(items);
  const isLoading = query.isLoading;
  const isError = query.isError && items.length === 0;
  const isEmpty = !isLoading && !isError && items.length === 0;

  if (!open) return null;

  return (
    <>
      <button
        type="button"
        aria-hidden="true"
        tabIndex={-1}
        className="fixed inset-0 z-40 cursor-default bg-transparent"
        onClick={onClose}
      />

      <section
        role="dialog"
        aria-modal="false"
        aria-label={t("title")}
        className="fixed left-3 right-3 top-[72px] z-50 max-h-[calc(100dvh-88px)] overflow-hidden rounded-2xl border border-border bg-card shadow-[var(--shadow-lg)] outline-none sm:absolute sm:left-auto sm:right-0 sm:top-[calc(100%+0.5rem)] sm:w-[420px] sm:max-w-[calc(100vw-2rem)]"
      >
        <div className="flex items-start justify-between gap-3 border-b border-border bg-card px-4 py-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="type-h3 text-foreground">{t("title")}</h2>
              {unreadCount > 0 && (
                <StatusChip tone="indigo" size="sm" className="tabular-nums">
                  {unreadCount > 99 ? "99+" : unreadCount}
                </StatusChip>
              )}
            </div>
            <p className="mt-0.5 type-small text-muted-foreground">
              {unreadCount > 0
                ? t("unreadSummary", { count: unreadCount })
                : t("allCaughtUp")}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            {unreadCount > 0 && (
              <button
                type="button"
                disabled={markAll.isPending}
                onClick={() => markAll.mutate()}
                className="h-8 cursor-pointer rounded-lg px-2.5 type-small font-medium text-muted-foreground outline-none transition-colors hover:bg-[var(--bg-muted)] hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
              >
                {t("markAllRead")}
              </button>
            )}
            <button
              type="button"
              aria-label={tc("close")}
              onClick={onClose}
              className="flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-lg text-muted-foreground outline-none transition-colors hover:bg-[var(--bg-muted)] hover:text-foreground focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
            >
              <X aria-hidden strokeWidth={1.8} className="size-4" />
            </button>
          </div>
        </div>

        <div className="max-h-[calc(100dvh-150px)] overflow-y-auto p-2 sm:max-h-[500px]">
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

          {!isLoading && !isError && items.length > 0 && (
            <div className="flex flex-col gap-4">
              {groups.map((group) => (
                <section key={group.bucket} aria-label={t(`groups.${group.bucket}`)}>
                  <h3 className="px-2 pb-1.5 type-caption font-semibold uppercase tracking-[0.06em] text-muted-foreground">
                    {t(`groups.${group.bucket}`)}
                  </h3>
                  <ul className="flex flex-col gap-0.5">
                    {group.items.map((n) => (
                      <li key={n.id}>
                        <NotificationRow
                          notification={n}
                          locale={locale}
                          newLabel={t("newTag")}
                          onActivate={onRowActivate}
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
        </div>
      </section>
    </>
  );
}

/* --------------------------------- Row ------------------------------------ */

interface NotificationRowProps {
  notification: Notification;
  locale: string;
  newLabel: string;
  onActivate: (n: Notification, navigates: boolean) => void;
}

function NotificationRow({
  notification: n,
  locale,
  newLabel,
  onActivate,
}: NotificationRowProps) {
  const t = useTranslations("notifications");
  const unread = !n.is_read;
  const ts = relativeTime(n.created_at, locale);
  const categoryKey = notifCategoryKey(n.notif_type);

  const inner = (
    <>
      <NotifIcon type={n.notif_type} />
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5">
          {categoryKey && (
            <StatusChip tone="neutral" size="sm">
              {t(`categories.${categoryKey}`)}
            </StatusChip>
          )}
          {ts && (
            <time
              dateTime={n.created_at}
              className="ml-auto shrink-0 type-caption tabular-nums text-muted-foreground"
            >
              {ts}
            </time>
          )}
        </span>
        <span className="mt-1 flex items-start gap-2">
          <span
            className={cn(
              "min-w-0 flex-1 type-body text-foreground",
              unread ? "font-semibold" : "font-medium",
            )}
          >
            {n.title}
          </span>
          {unread && (
            <StatusChip tone="indigo" size="sm" className="mt-0.5">
              {newLabel}
            </StatusChip>
          )}
        </span>
        <span className="mt-0.5 line-clamp-2 block type-small text-muted-foreground">
          {n.body}
        </span>
      </span>
    </>
  );

  const base = cn(
    "relative flex w-full items-start gap-3 rounded-[10px] px-2.5 py-2.5 text-left outline-none transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]",
    unread
      ? "bg-[var(--bg-subtle)] before:absolute before:left-1 before:top-2.5 before:h-[calc(100%-1.25rem)] before:w-0.5 before:rounded-full before:bg-[var(--viz-indigo)] hover:bg-[var(--bg-muted)]"
      : "hover:bg-[var(--bg-subtle)]",
  );

  if (n.action_url) {
    return (
      <Link href={n.action_url} onClick={() => onActivate(n, true)} className={base}>
        {inner}
      </Link>
    );
  }

  // No destination — still allow marking read in place.
  return (
    <button type="button" onClick={() => onActivate(n, false)} className={base}>
      {inner}
    </button>
  );
}

/* ------------------------------ Skeletons --------------------------------- */

function NotificationSkeletons() {
  return (
    <div className="flex flex-col gap-2" aria-hidden>
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="flex items-start gap-3 px-2.5 py-2.5">
          <Skeleton className="size-9 rounded-xl" />
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
