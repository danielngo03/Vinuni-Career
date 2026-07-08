"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  MagnifyingGlass,
  UserCircle,
  UsersThree,
  X,
} from "@phosphor-icons/react";
import { Button, Modal, useToast } from "@/components/ui";
import { cn } from "@/lib/utils";
import {
  messagingApi,
  type InboxThreadSummary,
  type ThreadSummary,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { MESSAGING_INBOX_ROOT, MESSAGING_THREADS_KEY } from "./query-keys";
import { useRecipientSearch } from "./use-recipient-search";

export interface AssignThreadModalProps {
  open: boolean;
  onClose: () => void;
  thread: ThreadSummary | InboxThreadSummary;
  onAssigned?: () => void;
}

function inboxFields(
  thread: ThreadSummary | InboxThreadSummary,
): Pick<InboxThreadSummary, "assigned_department_id" | "assigned_user_id"> {
  const t = thread as Partial<InboxThreadSummary>;
  return {
    assigned_department_id: t.assigned_department_id ?? null,
    assigned_user_id: t.assigned_user_id ?? null,
  };
}

/**
 * Route an org thread to a department and/or a teammate. Both pickers are driven
 * by the RBAC-scoped recipient search (never raw id inputs). Sends the full
 * routing on save so clearing a slot is honored server-side.
 */
export function AssignThreadModal({
  open,
  onClose,
  thread,
  onAssigned,
}: AssignThreadModalProps) {
  const t = useTranslations("messaging");
  const tc = useTranslations("common");
  const toast = useToast();
  const apiError = useApiErrorMessage();
  const qc = useQueryClient();

  const current = inboxFields(thread);
  const [deptId, setDeptId] = useState<string | null>(current.assigned_department_id);
  const [deptName, setDeptName] = useState<string | null>(null);
  const [assigneeId, setAssigneeId] = useState<string | null>(current.assigned_user_id);
  const [assigneeName, setAssigneeName] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  // Reset to the thread's current routing each time the modal opens.
  useEffect(() => {
    if (open) {
      const fresh = inboxFields(thread);
      setDeptId(fresh.assigned_department_id);
      setAssigneeId(fresh.assigned_user_id);
      setDeptName(null);
      setAssigneeName(null);
      setQuery("");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, thread.id]);

  const search = useRecipientSearch(query, open);
  const { grouped } = search;

  // Resolve current ids → names from the default/searched list (no raw ids shown).
  const nameMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const d of grouped.departments) map.set(d.department_id, d.display_name);
    for (const u of grouped.users) map.set(u.user_id, u.display_name);
    return map;
  }, [grouped]);

  const resolvedDeptName =
    deptName ?? (deptId ? nameMap.get(deptId) ?? null : null);
  const resolvedAssigneeName =
    assigneeName ?? (assigneeId ? nameMap.get(assigneeId) ?? null : null);

  const save = useMutation({
    mutationFn: () =>
      messagingApi.assignThread(thread.id, {
        department_id: deptId,
        assignee_id: assigneeId,
      }),
    onSuccess: () => {
      toast.show({ tone: "success", title: t("assignSaved") });
      void qc.invalidateQueries({ queryKey: MESSAGING_INBOX_ROOT });
      void qc.invalidateQueries({ queryKey: MESSAGING_THREADS_KEY });
      onAssigned?.();
      onClose();
    },
    onError: (e) => toast.show({ tone: "error", title: apiError(e) }),
  });

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t("assignTitle")}
      description={t("assignDescription")}
      closeLabel={tc("close")}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={save.isPending}>
            {tc("cancel")}
          </Button>
          <Button
            variant="primary"
            onClick={() => save.mutate()}
            loading={save.isPending}
          >
            {t("assignSave")}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {/* Current selections */}
        <div className="grid gap-2 sm:grid-cols-2">
          <SelectedSlot
            label={t("assignDepartmentLabel")}
            icon={UsersThree}
            name={resolvedDeptName}
            emptyLabel={t("assignNone")}
            clearLabel={t("assignClear")}
            onClear={() => {
              setDeptId(null);
              setDeptName(null);
            }}
          />
          <SelectedSlot
            label={t("assignAssigneeLabel")}
            icon={UserCircle}
            name={resolvedAssigneeName}
            emptyLabel={t("assignNone")}
            clearLabel={t("assignClear")}
            onClear={() => {
              setAssigneeId(null);
              setAssigneeName(null);
            }}
          />
        </div>

        {/* Search + pick */}
        <div className="flex h-11 items-center gap-2 rounded-xl border border-[var(--border-default)] bg-[var(--bg-subtle)] px-3 text-[var(--text-secondary)] focus-within:border-[var(--border-strong)] focus-within:bg-white">
          <MagnifyingGlass aria-hidden weight="bold" className="size-4 shrink-0" />
          <label htmlFor="assign-search" className="sr-only">
            {t("assignSearchLabel")}
          </label>
          <input
            id="assign-search"
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("assignSearchPlaceholder")}
            className="min-w-0 flex-1 bg-transparent text-sm font-medium text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)]"
          />
        </div>

        <div className="max-h-[240px] min-h-[120px] space-y-4 overflow-y-auto">
          {grouped.departments.length > 0 && (
            <PickGroup title={t("recipientGroupDepartments")}>
              {grouped.departments.map((d) => (
                <PickRow
                  key={d.department_id}
                  icon={UsersThree}
                  title={d.display_name}
                  active={deptId === d.department_id}
                  onPick={() => {
                    setDeptId(d.department_id);
                    setDeptName(d.display_name);
                  }}
                />
              ))}
            </PickGroup>
          )}
          {grouped.users.length > 0 && (
            <PickGroup title={t("recipientGroupTeammates")}>
              {grouped.users.map((u) => (
                <PickRow
                  key={u.user_id}
                  icon={UserCircle}
                  title={u.display_name}
                  active={assigneeId === u.user_id}
                  onPick={() => {
                    setAssigneeId(u.user_id);
                    setAssigneeName(u.display_name);
                  }}
                />
              ))}
            </PickGroup>
          )}
          {grouped.departments.length === 0 && grouped.users.length === 0 && (
            <p className="py-6 text-center text-sm text-[var(--text-muted)]">
              {search.isLoading ? tc("loading") : t("assignNoTargets")}
            </p>
          )}
        </div>
      </div>
    </Modal>
  );
}

function SelectedSlot({
  label,
  icon: Icon,
  name,
  emptyLabel,
  clearLabel,
  onClear,
}: {
  label: string;
  icon: typeof UsersThree;
  name: string | null;
  emptyLabel: string;
  clearLabel: string;
  onClear: () => void;
}) {
  return (
    <div className="rounded-xl border border-[var(--border-default)] bg-white px-3 py-2">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        {label}
      </p>
      <div className="mt-1 flex items-center gap-2">
        <Icon
          aria-hidden
          weight="duotone"
          className="size-4 shrink-0 text-[var(--text-secondary)]"
        />
        <span
          className={cn(
            "min-w-0 flex-1 truncate text-sm font-semibold",
            name ? "text-[var(--text-primary)]" : "text-[var(--text-muted)]",
          )}
        >
          {name ?? emptyLabel}
        </span>
        {name && (
          <button
            type="button"
            onClick={onClear}
            aria-label={clearLabel}
            title={clearLabel}
            className="rounded-md p-1 text-[var(--text-muted)] outline-none hover:bg-[var(--bg-subtle)] hover:text-[var(--brand-red)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]"
          >
            <X aria-hidden weight="bold" className="size-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}

function PickGroup({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <p className="mb-1 px-1 text-[11px] font-bold uppercase tracking-[0.08em] text-[var(--text-muted)]">
        {title}
      </p>
      <ul className="space-y-0.5">{children}</ul>
    </div>
  );
}

function PickRow({
  icon: Icon,
  title,
  active,
  onPick,
}: {
  icon: typeof UsersThree;
  title: string;
  active: boolean;
  onPick: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        onClick={onPick}
        aria-pressed={active}
        className={cn(
          "flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left text-sm outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30",
          active
            ? "bg-[var(--text-primary)]/[0.06] font-semibold text-[var(--text-primary)] shadow-[inset_0_0_0_1px_rgba(0,0,0,0.1)]"
            : "text-[var(--text-secondary)] hover:bg-[var(--bg-subtle)]",
        )}
      >
        <Icon aria-hidden weight="duotone" className="size-4 shrink-0" />
        <span className="min-w-0 flex-1 truncate">{title}</span>
      </button>
    </li>
  );
}
