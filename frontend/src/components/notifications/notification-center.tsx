"use client";

import { useEffect } from "react";
import { useLocale, useTranslations } from "next-intl";
import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
  type InfiniteData,
} from "@tanstack/react-query";
import { BellSlash, WarningCircle } from "@phosphor-icons/react";
import { X } from "lucide-react";
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

export interface NotificationCenterProps {
  open: boolean;
  onClose: () => void;
}

/**
 * Bell-center panel. Renders the cursor-paginated feed grouped by
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

  const items: Notification[] =
    query.data?.pages.flatMap((p) => p.data) ?? [];
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
        className="fixed left-3 right-3 top-[72px] z-50 max-h-[calc(100dvh-88px)] overflow-hidden rounded-[22px] border border-[var(--border-default)] bg-[#fbfaf8] shadow-[0_18px_54px_rgba(0,0,0,0.16)] outline-none sm:absolute sm:left-auto sm:right-0 sm:top-[calc(100%+0.5rem)] sm:w-[420px] sm:max-w-[calc(100vw-2rem)]"
      >
        <div className="flex items-start justify-between gap-3 border-b border-[var(--border-default)] bg-white px-4 py-3.5">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold text-[var(--text-primary)]">
                {t("title")}
              </h2>
              {unreadCount > 0 && (
                <span className="rounded-full bg-[var(--text-primary)] px-2 py-0.5 text-[11px] font-bold leading-none text-white">
                  {unreadCount > 99 ? "99+" : unreadCount}
                </span>
              )}
            </div>
            <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
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
                className="h-8 cursor-pointer rounded-full px-2.5 text-xs font-semibold text-[var(--text-secondary)] outline-none transition-colors hover:bg-[#f2f1ee] hover:text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
              >
                {t("markAllRead")}
              </button>
            )}
            <button
              type="button"
              aria-label={tc("close")}
              onClick={onClose}
              className="flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-full text-[var(--text-muted)] outline-none transition-colors hover:bg-[#f2f1ee] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
            >
              <X aria-hidden strokeWidth={1.8} className="size-4" />
            </button>
          </div>
        </div>

        <div className="max-h-[calc(100dvh-150px)] overflow-y-auto px-2.5 py-3 sm:max-h-[500px]">
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

          {!isLoading && !isError && items.length > 0 && (
            <div className="flex flex-col gap-5">
              {groups.map((group) => (
                <section key={group.bucket} aria-label={t(`groups.${group.bucket}`)}>
                  <h3 className="px-2 pb-2 text-[11px] font-bold uppercase tracking-[0.08em] text-[var(--text-muted)]">
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
      <NotifIcon type={n.notif_type} active={unread} />
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2">
          {categoryKey && (
            <span className="shrink-0 text-[10px] font-bold uppercase tracking-[0.08em] text-[var(--text-muted)]">
              {t(`categories.${categoryKey}`)}
            </span>
          )}
          {ts && (
            <time
              dateTime={n.created_at}
              className="shrink-0 text-xs text-[var(--text-muted)]"
            >
              {ts}
            </time>
          )}
        </span>
        <span className="mt-1 flex items-start gap-2">
          <span
            className={cn(
              "min-w-0 flex-1 text-sm leading-5 text-[var(--text-primary)]",
              unread ? "font-bold" : "font-semibold",
            )}
          >
            {n.title}
          </span>
          {unread && (
            <span className="mt-0.5 shrink-0 rounded-full bg-[#e6f7ef] px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-[0.06em] text-[#0d7f59]">
              {newLabel}
            </span>
          )}
        </span>
        <span className="mt-0.5 line-clamp-2 block text-sm leading-5 text-[var(--text-secondary)]">
          {n.body}
        </span>
      </span>
    </>
  );

  const base = cn(
    "relative flex w-full items-start gap-3 rounded-[16px] px-3 py-3 text-left outline-none transition-colors duration-200",
    "hover:bg-white focus-visible:bg-white",
    unread
      ? "bg-white shadow-[inset_0_0_0_1px_rgba(16,163,111,0.14),0_1px_2px_rgba(0,0,0,0.03)] before:absolute before:left-1.5 before:top-3 before:h-[calc(100%-1.5rem)] before:w-1 before:rounded-full before:bg-[#10a36f]"
      : "hover:shadow-[inset_0_0_0_1px_rgba(0,0,0,0.045)]",
  );

  if (n.action_url) {
    return (
      <Link
        href={n.action_url}
        onClick={() => onActivate(n, true)}
        className={base}
      >
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
    <div className="flex flex-col gap-3" aria-hidden>
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="flex items-start gap-3 px-1 py-2">
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
