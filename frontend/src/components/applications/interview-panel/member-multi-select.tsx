"use client";

import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { organizationApi, type OrgMember } from "@/lib/api";

export function useOrgMembers(enabled: boolean) {
  return useQuery({
    queryKey: ["organization", "members", "interviewAssignees"],
    queryFn: () => organizationApi.listMembers(),
    enabled,
    retry: false,
    staleTime: 60_000,
  });
}

/** Members that can actually be assigned (active + carry a user id). */
export function assignableMembers(members: OrgMember[]): OrgMember[] {
  return members.filter((m) => !!m.user_id && m.status !== "suspended");
}

export function MemberMultiSelect({
  idBase,
  selected,
  onChange,
}: {
  idBase: string;
  selected: string[];
  onChange: (ids: string[]) => void;
}) {
  const t = useTranslations("interviews");
  const query = useOrgMembers(true);
  const members = assignableMembers(query.data?.data ?? []);

  function toggle(userId: string) {
    onChange(
      selected.includes(userId)
        ? selected.filter((id) => id !== userId)
        : [...selected, userId],
    );
  }

  return (
    <fieldset>
      <legend className="mb-1.5 text-sm font-semibold text-[var(--text-primary)]">
        {t("assigneesLabel")}
      </legend>
      {query.isPending ? (
        <div
          className="h-16 animate-pulse rounded-xl bg-[var(--bg-muted)]"
          aria-hidden
        />
      ) : query.isError || members.length === 0 ? (
        <p className="rounded-lg border border-white/50 bg-white/70 px-3 py-2 text-xs text-[var(--text-secondary)] backdrop-blur-sm">
          {t("noAssignableMembers")}
        </p>
      ) : (
        <ul className="max-h-44 space-y-1 overflow-y-auto rounded-xl border border-white/60 bg-white/72 p-1.5">
          {members.map((m) => {
            const id = `${idBase}-asg-${m.user_id}`;
            const checked = selected.includes(m.user_id as string);
            return (
              <li key={m.id}>
                <label
                  htmlFor={id}
                  className="flex cursor-pointer items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm hover:bg-white/80 has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-[var(--brand-primary)]/40"
                >
                  <input
                    id={id}
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggle(m.user_id as string)}
                    className="size-4 accent-[var(--brand-primary)]"
                  />
                  <span className="min-w-0 truncate text-[var(--text-primary)]">
                    {m.full_name?.trim() || m.user_email}
                  </span>
                </label>
              </li>
            );
          })}
        </ul>
      )}
      <p className="mt-1 text-xs text-[var(--text-muted)]">
        {t("assigneesHelp")}
      </p>
    </fieldset>
  );
}
