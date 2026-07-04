/**
 * Shared TanStack Query keys for institutional messaging. The topbar badge poll,
 * the inbox list, and an open thread's message poll all read/write these caches
 * so optimistic mark-read, mute, and send stay consistent across surfaces.
 */
export const MESSAGING_UNREAD_KEY = ["messaging", "unread-count"] as const;
export const MESSAGING_THREADS_KEY = ["messaging", "threads"] as const;

/** Per-thread message cache (full thread, polled while open). */
export function messagingThreadKey(threadId: string) {
  return ["messaging", "thread", threadId] as const;
}

/** Per-thread detail cache (participants + can_reply + status). */
export function messagingThreadDetailKey(threadId: string) {
  return ["messaging", "thread-detail", threadId] as const;
}
