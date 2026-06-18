"use client";

import {
  Bell,
  CalendarDots,
  CheckCircle,
  ClipboardText,
  Info,
} from "@phosphor-icons/react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { apiFetch, apiMessage } from "@/lib/api/client";
import type { Notification } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { SidePanel } from "@/components/ui/side-panel";

const icons = {
  APPLICATION: ClipboardText,
  EVENT: CalendarDots,
  INTERVIEW: CalendarDots,
  SYSTEM: Info,
} as const;

export function NotificationCenter({
  open,
  onOpenChange,
  onUnreadChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onUnreadChange?: (count: number) => void;
}) {
  const { locale, dictionary } = useI18n();
  const [items, setItems] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const notifications = await apiFetch<Notification[]>("/notifications?limit=50");
      setItems(notifications);
      onUnreadChange?.(notifications.filter((item) => !item.is_read).length);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setLoading(false);
    }
  }, [dictionary.common.retry, onUnreadChange]);

  useEffect(() => {
    if (!open) return;
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [open, load]);

  async function markRead(id: string) {
    try {
      await apiFetch(`/notifications/${id}/read`, { method: "POST" });
      setItems((current) =>
        current.map((item) => (item.id === id ? { ...item, is_read: true } : item)),
      );
      onUnreadChange?.(Math.max(0, items.filter((item) => !item.is_read).length - 1));
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    }
  }

  async function markAllRead() {
    try {
      await apiFetch("/notifications/read-all", { method: "POST" });
      setItems((current) => current.map((item) => ({ ...item, is_read: true })));
      onUnreadChange?.(0);
      toast.success(dictionary.common.updated);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    }
  }

  return (
    <SidePanel
      open={open}
      onOpenChange={onOpenChange}
      title={dictionary.shell.notifications}
      description={`${items.filter((item) => !item.is_read).length} ${dictionary.shell.unread}`}
    >
      <div className="flex justify-end border-b px-5 py-3">
        <Button size="sm" variant="ghost" onClick={markAllRead}>
          <CheckCircle className="size-4" />
          {dictionary.shell.markAllRead}
        </Button>
      </div>
      <div className="p-4 sm:p-5">
        {loading ? <PanelSkeleton /> : null}
        {!loading && !items.length ? (
          <EmptyState
            icon={Bell}
            title={dictionary.shell.noNotifications}
            description={dictionary.shell.noNotificationsDescription}
          />
        ) : null}
        {!loading && items.length ? (
          <div className="space-y-2">
            {items.map((item) => {
              const Icon = icons[item.notification_type];
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    if (!item.is_read) void markRead(item.id);
                    if (item.action_link) window.location.href = item.action_link;
                  }}
                  className={cn(
                    "focus-ring flex w-full cursor-pointer items-start gap-3 rounded-2xl border p-4 text-left transition-colors",
                    item.is_read
                      ? "bg-white hover:bg-slate-50"
                      : "border-blue-100 bg-blue-50/60 hover:bg-blue-50",
                  )}
                >
                  <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-white text-primary shadow-sm ring-1 ring-slate-200">
                    <Icon className="size-5" weight="duotone" />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="font-semibold">{item.title}</p>
                      {!item.is_read ? (
                        <span className="size-2 rounded-full bg-primary" />
                      ) : null}
                    </div>
                    <p className="mt-1 text-sm leading-6 text-muted">{item.content}</p>
                    <p className="mt-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                      {new Intl.DateTimeFormat(locale, {
                        dateStyle: "medium",
                        timeStyle: "short",
                      }).format(new Date())}
                    </p>
                  </div>
                </button>
              );
            })}
          </div>
        ) : null}
      </div>
    </SidePanel>
  );
}
