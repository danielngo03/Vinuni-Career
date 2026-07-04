/**
 * Shared TanStack Query keys for the notification bell. The trigger (badge poll)
 * and the panel (feed + optimistic mutations) must read/write the same caches.
 */
export const UNREAD_COUNT_KEY = ["notifications", "unread-count"] as const;
export const NOTIFICATIONS_LIST_KEY = ["notifications", "list"] as const;
