"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CaretRight,
  MagnifyingGlass,
  PaperPlaneTilt,
  SealCheck,
  UserCircle,
  UsersThree,
} from "@phosphor-icons/react";
import { Button, Modal, Textarea, useToast } from "@/components/ui";
import { CompanyAvatar } from "@/components/companies/company-avatar";
import { cn } from "@/lib/utils";
import { messagingApi, type RecipientTarget, type ThreadSummary } from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { MESSAGING_INBOX_ROOT, MESSAGING_THREADS_KEY } from "./query-keys";
import { useRecipientSearch } from "./use-recipient-search";

const BODY_MAX = 8000;

export interface NewMessageModalProps {
  open: boolean;
  onClose: () => void;
  persona: "student" | "partner" | "university";
  /** Fired with the created/re-opened thread so the caller can open it. */
  onCreated?: (thread: ThreadSummary) => void;
}

/**
 * "New message" composer. Step 1: a debounced recipient search (server enforces
 * the permission matrix — students only ever get organizations). Step 2: a first
 * message to the chosen target. Selecting a target maps to the correct create
 * field (org → target_org_id, department → target_department_id, user →
 * recipient_ids). Students never see a path to message another student.
 */
export function NewMessageModal({
  open,
  onClose,
  persona,
  onCreated,
}: NewMessageModalProps) {
  const t = useTranslations("messaging");
  const tc = useTranslations("common");
  const toast = useToast();
  const apiError = useApiErrorMessage();
  const qc = useQueryClient();

  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<RecipientTarget | null>(null);
  const [body, setBody] = useState("");

  // Reset everything whenever the modal is (re)opened/closed.
  useEffect(() => {
    if (!open) {
      setQuery("");
      setSelected(null);
      setBody("");
    }
  }, [open]);

  const search = useRecipientSearch(query, open && !selected);

  const create = useMutation({
    mutationFn: () => {
      if (!selected) throw new Error("no recipient");
      const first = body.trim() || null;
      if (selected.kind === "org") {
        return messagingApi.createThread({
          target_org_id: selected.org_id,
          first_message: first,
        });
      }
      if (selected.kind === "department") {
        return messagingApi.createThread({
          target_department_id: selected.department_id,
          first_message: first,
        });
      }
      return messagingApi.createThread({
        recipient_ids: [selected.user_id],
        first_message: first,
      });
    },
    onSuccess: (thread) => {
      toast.show({ tone: "success", title: t("startSuccess") });
      void qc.invalidateQueries({ queryKey: MESSAGING_THREADS_KEY });
      void qc.invalidateQueries({ queryKey: MESSAGING_INBOX_ROOT });
      onCreated?.(thread);
      onClose();
    },
    onError: (e) => {
      toast.show({ tone: "error", title: apiError(e) });
    },
  });

  const placeholder =
    persona === "student"
      ? t("recipientSearchPlaceholderStudent")
      : t("recipientSearchPlaceholder");

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t("newMessage")}
      description={selected ? undefined : t("newMessageDescription")}
      closeLabel={tc("close")}
      footer={
        selected ? (
          <>
            <Button
              variant="ghost"
              onClick={() => setSelected(null)}
              disabled={create.isPending}
            >
              <ArrowLeft aria-hidden weight="bold" className="size-4" />
              {tc("back")}
            </Button>
            <Button
              variant="primary"
              onClick={() => create.mutate()}
              loading={create.isPending}
              disabled={body.trim().length === 0}
            >
              <PaperPlaneTilt aria-hidden weight="fill" className="size-4" />
              {t("startConversation")}
            </Button>
          </>
        ) : undefined
      }
    >
      {selected ? (
        <ComposeStep
          selected={selected}
          body={body}
          onBody={setBody}
          onChange={() => setSelected(null)}
        />
      ) : (
        <PickStep
          query={query}
          onQuery={setQuery}
          placeholder={placeholder}
          persona={persona}
          search={search}
          onPick={setSelected}
        />
      )}
    </Modal>
  );
}

/* ------------------------------- Pick step -------------------------------- */

function PickStep({
  query,
  onQuery,
  placeholder,
  persona,
  search,
  onPick,
}: {
  query: string;
  onQuery: (v: string) => void;
  placeholder: string;
  persona: "student" | "partner" | "university";
  search: ReturnType<typeof useRecipientSearch>;
  onPick: (target: RecipientTarget) => void;
}) {
  const t = useTranslations("messaging");
  const { grouped, isLoading, isFetching, isEmpty, total } = search;

  return (
    <div className="space-y-3">
      <div className="flex h-11 items-center gap-2 rounded-xl border border-[var(--border-default)] bg-[var(--bg-subtle)] px-3 text-[var(--text-secondary)] focus-within:border-[var(--border-strong)] focus-within:bg-[var(--surface-card)]">
        <MagnifyingGlass aria-hidden weight="bold" className="size-4 shrink-0" />
        <label htmlFor="recipient-search" className="sr-only">
          {t("recipientSearchLabel")}
        </label>
        <input
          id="recipient-search"
          type="search"
          autoFocus
          value={query}
          onChange={(e) => onQuery(e.target.value)}
          placeholder={placeholder}
          className="min-w-0 flex-1 bg-transparent text-sm font-medium text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)]"
        />
      </div>

      {persona === "student" && (
        <p className="text-xs text-[var(--text-muted)]">
          {t("recipientStudentHint")}
        </p>
      )}

      <div className="min-h-[220px]" aria-busy={isFetching}>
        {isLoading ? (
          <RecipientSkeletons />
        ) : isEmpty ? (
          <div className="flex min-h-[220px] flex-col items-center justify-center gap-1 text-center">
            <p className="text-sm font-semibold text-[var(--text-secondary)]">
              {query.trim() ? t("recipientNoMatch") : t("recipientHintStart")}
            </p>
            <p className="text-xs text-[var(--text-muted)]">
              {query.trim() ? t("recipientNoMatchBody") : t("recipientHintBody")}
            </p>
          </div>
        ) : total === 0 ? (
          <div className="flex min-h-[220px] flex-col items-center justify-center gap-1 text-center">
            <p className="text-sm font-semibold text-[var(--text-secondary)]">
              {t("recipientHintStart")}
            </p>
            <p className="text-xs text-[var(--text-muted)]">
              {t("recipientHintBody")}
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {grouped.orgs.length > 0 && (
              <RecipientGroup title={t("recipientGroupOrgs")}>
                {grouped.orgs.map((org) => (
                  <RecipientRow
                    key={org.org_id}
                    onPick={() => onPick(org)}
                    avatar={
                      <CompanyAvatar
                        name={org.display_name}
                        logoUrl={org.logo_url ?? null}
                        size="sm"
                      />
                    }
                    title={org.display_name}
                    meta={
                      <span className="flex items-center gap-1.5">
                        <span className="rounded-full bg-[var(--bg-muted)] px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--text-secondary)]">
                          {org.org_type === "university"
                            ? t("recipientTypeUniversity")
                            : t("recipientTypePartner")}
                        </span>
                        {org.is_verified && (
                          <span className="inline-flex items-center gap-0.5 text-[10px] font-semibold text-[#0d7f59]">
                            <SealCheck aria-hidden weight="fill" className="size-3" />
                            {t("verified")}
                          </span>
                        )}
                      </span>
                    }
                  />
                ))}
              </RecipientGroup>
            )}

            {grouped.departments.length > 0 && (
              <RecipientGroup title={t("recipientGroupDepartments")}>
                {grouped.departments.map((dept) => (
                  <RecipientRow
                    key={dept.department_id}
                    onPick={() => onPick(dept)}
                    avatar={<AvatarIcon icon={UsersThree} />}
                    title={dept.display_name}
                    meta={
                      <span className="text-xs text-[var(--text-muted)]">
                        {t("recipientDepartmentMeta")}
                      </span>
                    }
                  />
                ))}
              </RecipientGroup>
            )}

            {grouped.users.length > 0 && (
              <RecipientGroup title={t("recipientGroupTeammates")}>
                {grouped.users.map((user) => (
                  <RecipientRow
                    key={user.user_id}
                    onPick={() => onPick(user)}
                    avatar={<AvatarIcon icon={UserCircle} />}
                    title={user.display_name}
                    meta={
                      <span className="text-xs text-[var(--text-muted)]">
                        {t("recipientTeammateMeta")}
                      </span>
                    }
                  />
                ))}
              </RecipientGroup>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function RecipientGroup({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <p className="mb-1.5 px-1 text-[11px] font-bold uppercase tracking-[0.08em] text-[var(--text-muted)]">
        {title}
      </p>
      <ul className="space-y-0.5">{children}</ul>
    </div>
  );
}

function RecipientRow({
  avatar,
  title,
  meta,
  onPick,
}: {
  avatar: React.ReactNode;
  title: string;
  meta: React.ReactNode;
  onPick: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        onClick={onPick}
        className="group flex w-full items-center gap-3 rounded-xl px-2 py-2 text-left outline-none transition-colors hover:bg-[var(--bg-subtle)] focus-visible:bg-[var(--bg-subtle)]"
      >
        <span className="shrink-0">{avatar}</span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-semibold text-[var(--text-primary)]">
            {title}
          </span>
          <span className="mt-0.5 block">{meta}</span>
        </span>
        <CaretRight
          aria-hidden
          weight="bold"
          className="size-4 shrink-0 text-[var(--text-muted)] transition-transform group-hover:translate-x-0.5"
        />
      </button>
    </li>
  );
}

function AvatarIcon({ icon: Icon }: { icon: typeof UsersThree }) {
  return (
    <span className="flex size-9 items-center justify-center rounded-lg bg-[var(--bg-muted)] text-[var(--text-secondary)] shadow-[inset_0_0_0_1px_rgba(0,0,0,0.045)]">
      <Icon aria-hidden weight="duotone" className="size-[18px]" />
    </span>
  );
}

function RecipientSkeletons() {
  return (
    <ul className="space-y-1" aria-hidden>
      {Array.from({ length: 4 }).map((_, i) => (
        <li key={i} className="flex items-center gap-3 px-2 py-2">
          <span className="size-9 shrink-0 animate-pulse rounded-lg bg-[var(--bg-muted)]" />
          <span className="flex-1">
            <span className="block h-3.5 w-2/5 animate-pulse rounded bg-[var(--bg-muted)]" />
            <span className="mt-1.5 block h-2.5 w-1/4 animate-pulse rounded bg-[var(--bg-muted)]" />
          </span>
        </li>
      ))}
    </ul>
  );
}

/* ------------------------------ Compose step ------------------------------ */

function ComposeStep({
  selected,
  body,
  onBody,
  onChange,
}: {
  selected: RecipientTarget;
  body: string;
  onBody: (v: string) => void;
  onChange: () => void;
}) {
  const t = useTranslations("messaging");

  const targetName = useMemo(() => {
    if (selected.kind === "org") return selected.display_name;
    return selected.display_name;
  }, [selected]);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 rounded-xl border border-[var(--border-default)] bg-[var(--bg-subtle)] px-3 py-2.5">
        <span className="shrink-0">
          {selected.kind === "org" ? (
            <CompanyAvatar
              name={selected.display_name}
              logoUrl={selected.logo_url ?? null}
              size="sm"
            />
          ) : (
            <AvatarIcon
              icon={selected.kind === "department" ? UsersThree : UserCircle}
            />
          )}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            {t("selectedRecipientLabel")}
          </span>
          <span className="block truncate text-sm font-bold text-[var(--text-primary)]">
            {targetName}
          </span>
        </span>
        <Button variant="ghost" size="xs" onClick={onChange}>
          {t("changeRecipient")}
        </Button>
      </div>

      <Textarea
        label={t("firstMessageLabel")}
        value={body}
        onChange={(e) => onBody(e.target.value)}
        placeholder={t("firstMessagePlaceholder")}
        rows={5}
        maxLength={BODY_MAX}
        autoFocus
      />
      {selected.kind === "org" && (
        <p className={cn("text-xs text-[var(--text-muted)]")}>
          {t("requestGateHint")}
        </p>
      )}
    </div>
  );
}
