"use client";

import { useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useInfiniteQuery } from "@tanstack/react-query";
import {
  ChatsCircle,
  Megaphone,
  BellSlash,
  WifiSlash,
} from "@phosphor-icons/react";
import { Button, EmptyState, Sheet, Skeleton } from "@/components/ui";
import { cn } from "@/lib/utils";
import { relativeTime } from "@/lib/notifications/grouping";
import { messagingApi, type ThreadSummary } from "@/lib/api";
import { MESSAGING_THREADS_KEY } from "./query-keys";
import { ThreadPanel } from "./thread-panel";

export interface MessagingCenterProps {
  open: boolean;
  onClose: () => void;
  /** Optional thread to open immediately (e.g. after partner initiates). */
  initialThread?: ThreadSummary | null;
}

/**
 * Slide-in messaging center. Master view = the inbox (my threads, masked
 * counterpart labels, unread dots, announcement markers); detail view = one
 * open thread (transcript + composer). Polls the thread list while open so a new
 * institutional message surfaces without a refresh. Identity is the server label
 * only — the partner side renders an anonymous handle until reveal.
 */
export function MessagingCenter({
  open,
  onClose,
  initialThread,
}: MessagingCenterProps) {
  const t = useTranslations("messaging");
  const tc = useTranslations("common");
  const tStates = useTranslations("states");
  const locale = useLocale();

  const [selected, setSelected] = useState<ThreadSummary | null>(
    initialThread ?? null,
  );

  useEffect(() => {
    if (open && initialThread) setSelected(initialThread);
    if (!open) setSelected(null);
  }, [open, initialThread]);

  const query = useInfiniteQuery({
    queryKey: MESSAGING_THREADS_KEY,
    queryFn: ({ pageParam }) =>
      messagingApi.listThreads({ cursor: pageParam, limit: 20 }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.page.next_cursor ?? undefined,
    enabled: open,
    refetchInterval: open && !selected ? 30_000 : false,
    refetchOnWindowFocus: true,
    staleTime: 15_000,
  });

  useEffect(() => {
    if (open) void query.refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const threads: ThreadSummary[] =
    query.data?.pages.flatMap((p) => p.data) ?? [];
  const isLoading = query.isLoading;
  const isError = query.isError && threads.length === 0;
  const isStale = query.isError && threads.length > 0;
  const isEmpty = !isLoading && !isError && threads.length === 0;

  return (
    <Sheet
      open={open}
      onClose={onClose}
      side="right"
      title={t("title")}
      closeLabel={tc("close")}
    >
      {selected ? (
        <div className="-my-4 flex h-[calc(100%+2rem)] flex-col py-0">
          <ThreadPanel
            thread={selected}
            open={open}
            onBack={() => {
              setSelected(null);
              void query.refetch();
            }}
            onChanged={() => void query.refetch()}
          />
        </div>
      ) : (
        <div className="flex flex-col gap-1">
          {isStale && (
            <p className="mb-1 flex items-center gap-1.5 rounded-lg bg-[var(--amber-100)] px-3 py-1.5 text-xs font-medium text-[var(--amber-700)]">
              <WifiSlash aria-hidden weight="bold" className="size-3.5" />
              {t("staleReload")}
            </p>
          )}

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
              description={t("emptyBody")}
            />
          )}

          {!isLoading && !isError && threads.length > 0 && (
            <ul className="-mx-1 flex flex-col">
              {threads.map((th) => (
                <li key={th.id}>
                  <ThreadRow
                    thread={th}
                    locale={locale}
                    announcementLabel={t("announcement")}
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
                  disabled={query.isFetchingNextPage}
                  onClick={() => void query.fetchNextPage()}
                >
                  {tc("loadMore")}
                </Button>
              )}
            </ul>
          )}
        </div>
      )}
    </Sheet>
  );
}

/* ---------------------------------- Row ----------------------------------- */

function ThreadRow({
  thread,
  locale,
  announcementLabel,
  onOpen,
}: {
  thread: ThreadSummary;
  locale: string;
  announcementLabel: string;
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
        "flex w-full items-start gap-3 rounded-xl px-2 py-3 text-left outline-none transition-colors hover:bg-[var(--bg-subtle)] focus-visible:bg-[var(--bg-subtle)]",
        unread && "bg-[var(--blue-50)]/40",
      )}
    >
      <span
        className={cn(
          "mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-xl shadow-sm",
          isAnnouncement
            ? "icon-chip-warning"
            : "icon-chip-primary",
        )}
      >
        {isAnnouncement ? (
          <Megaphone aria-hidden weight="duotone" className="size-5 text-white" />
        ) : (
          <ChatsCircle aria-hidden weight="duotone" className="size-5 text-white" />
        )}
      </span>

      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5">
          {unread && (
            <span
              aria-hidden
              className="size-2 shrink-0 rounded-full bg-[var(--brand-primary)]"
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
            <span className="shrink-0 rounded-full bg-[var(--blue-50)] px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-[var(--brand-primary)]">
              {announcementLabel}
            </span>
          )}
          <span className="min-w-0 flex-1 truncate text-xs text-[var(--text-secondary)]">
            {secondary}
          </span>
          {unread && (
            <span className="shrink-0 rounded-full bg-[var(--brand-primary)] px-1.5 text-[10px] font-bold leading-4 text-white">
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
      {Array.from({ length: 6 }).map((_, i) => (
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
