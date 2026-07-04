"use client";

import { useQuery } from "@tanstack/react-query";
import { messagingApi, type MessagingMessage } from "@/lib/api";
import { messagingThreadKey } from "./query-keys";

/**
 * Load the FULL message history of a thread (institutional threads are
 * low-volume — ADR-0012 §3) by paging forward until the cursor is exhausted,
 * then poll on an interval to pick up new messages. Messages come back ascending
 * (oldest → newest); we keep that order for the transcript.
 *
 * V1 deliberately re-reads the whole (small) thread per poll rather than doing
 * incremental `after`-cursor merging: the backend's final partial page returns a
 * null cursor, so there is no opaque anchor for "the newest message" — a full
 * re-read is simpler and correct for institutional volume. The WS follow-up
 * (ADR-0012 §3, deferred) replaces polling without changing this contract.
 */
async function fetchEntireThread(threadId: string): Promise<MessagingMessage[]> {
  const all: MessagingMessage[] = [];
  let cursor: string | null = null;
  // Hard cap the loop so a pathological thread can never hang the panel.
  for (let guard = 0; guard < 50; guard += 1) {
    const page = await messagingApi.listMessages(threadId, {
      after: cursor,
      limit: 50,
    });
    all.push(...page.data);
    cursor = page.page.next_cursor;
    if (!cursor) break;
  }
  return all;
}

export function useThreadMessages(threadId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: threadId ? messagingThreadKey(threadId) : ["messaging", "thread", "none"],
    queryFn: () => fetchEntireThread(threadId as string),
    enabled: enabled && !!threadId,
    refetchInterval: enabled && threadId ? 12_000 : false,
    refetchOnWindowFocus: true,
    staleTime: 8_000,
  });
}
