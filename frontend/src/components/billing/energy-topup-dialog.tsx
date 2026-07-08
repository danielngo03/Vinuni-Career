"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Lightning,
  Bank,
  Clock,
  CheckCircle,
  UsersThree,
} from "@phosphor-icons/react";
import { Button, Modal, Skeleton, StatusBadge } from "@/components/ui";
import {
  ApiError,
  aiEnergyApi,
  type AiEnergyPack,
  type AiEnergyTopup,
  type AiEnergyTopupResult,
} from "@/lib/api";
import { formatUnits, TOPUP_STATUS_TONE } from "@/lib/ai-energy/format";
import { formatVnd, formatDate } from "@/lib/billing/format";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { cn } from "@/lib/utils";

/**
 * Member "Buy more energy" dialog. Shows the top-up packs (opaque energy units +
 * a real VND price), requests a manual/bank-transfer top-up for the caller's own
 * scope, then renders the returned bank-transfer instructions + reference and a
 * pending-confirmation state. Also lists the member's past top-ups.
 *
 * Energy is an abstract product credit — no tokens/USD/provider/model. Payment is
 * manual: the top-up stays pending until VinUni finance confirms the transfer.
 *
 * NOTE: the pack catalogue is only exposed by the management overview
 * (`billing:manage`). A member without that capability (a shared org pool is
 * admin-managed) sees honest guidance to contact their admin, plus their own
 * top-up history.
 */
export function EnergyTopupDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const t = useTranslations("aiEnergy");
  const tc = useTranslations("common");
  const locale = useLocale();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();

  const [selected, setSelected] = useState<string | null>(null);
  const [result, setResult] = useState<AiEnergyTopupResult | null>(null);

  const packsQuery = useQuery({
    queryKey: ["ai-energy", "packs"],
    queryFn: () => aiEnergyApi.getOverview(),
    enabled: open,
    retry: false,
    staleTime: 5 * 60_000,
  });

  const historyQuery = useQuery({
    queryKey: ["ai-energy", "my-topups"],
    queryFn: () => aiEnergyApi.listMyTopups(),
    enabled: open,
    retry: false,
  });

  const request = useMutation({
    mutationFn: (packCode: string) =>
      aiEnergyApi.requestTopup({ pack_code: packCode }),
    onSuccess: (res) => {
      setResult(res);
      setSelected(null);
      void qc.invalidateQueries({ queryKey: ["ai-energy", "my-topups"] });
      void qc.invalidateQueries({ queryKey: ["ai", "usage"] });
    },
    // Errors surface inline below the packs via `request.isError`.
  });

  const packsBlocked =
    packsQuery.isError &&
    packsQuery.error instanceof ApiError &&
    (packsQuery.error.isPermissionError || packsQuery.error.isValidation);

  const packs: AiEnergyPack[] = packsQuery.data?.packs ?? [];

  function handleClose() {
    // Reset transient purchase state so a re-open starts clean.
    setSelected(null);
    setResult(null);
    onClose();
  }

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title={t("member.title")}
      description={result ? undefined : t("member.subtitle")}
      size="md"
      closeLabel={tc("close")}
      footer={
        result ? (
          <>
            <Button variant="ghost" onClick={() => setResult(null)}>
              {t("member.buyAnother")}
            </Button>
            <Button onClick={handleClose}>{tc("done")}</Button>
          </>
        ) : (
          <>
            <Button variant="ghost" onClick={handleClose}>
              {tc("cancel")}
            </Button>
            <Button
              onClick={() => selected && request.mutate(selected)}
              disabled={!selected || packsBlocked}
              loading={request.isPending}
            >
              {t("member.request")}
            </Button>
          </>
        )
      }
    >
      {result ? (
        <TopupResultPanel result={result} locale={locale} />
      ) : (
        <div className="space-y-5">
          {/* Packs */}
          {packsQuery.isPending ? (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              <Skeleton className="h-20 w-full" />
              <Skeleton className="h-20 w-full" />
              <Skeleton className="h-20 w-full" />
            </div>
          ) : packsBlocked ? (
            <OrgManagedNotice />
          ) : (
            <fieldset>
              <legend className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                {t("member.packsTitle")}
              </legend>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                {packs.map((p) => {
                  const active = selected === p.code;
                  return (
                    <label
                      key={p.code}
                      className={cn(
                        "flex cursor-pointer flex-col gap-1 rounded-xl border p-3.5 outline-none transition-colors",
                        "focus-within:ring-2 focus-within:ring-[var(--border-focus)]",
                        active
                          ? "border-[var(--text-primary)] bg-[var(--bg-subtle)] ring-2 ring-[var(--text-primary)]/15"
                          : "border-[var(--border-default)] hover:border-[var(--text-muted)]",
                      )}
                    >
                      <input
                        type="radio"
                        name="energy-pack"
                        value={p.code}
                        checked={active}
                        onChange={() => setSelected(p.code)}
                        className="sr-only"
                      />
                      <span className="flex items-center gap-1.5 text-sm font-bold text-[var(--text-primary)]">
                        <Lightning
                          aria-hidden
                          weight="duotone"
                          className="size-4 text-[var(--text-muted)]"
                        />
                        {t("member.packUnits", {
                          units: formatUnits(p.units, locale),
                        })}
                      </span>
                      <span className="text-sm font-semibold tabular-nums text-[var(--text-secondary)]">
                        {formatVnd(p.price_amount, p.currency, locale)}
                      </span>
                    </label>
                  );
                })}
              </div>
              <p className="mt-2 text-xs text-[var(--text-muted)]">
                {t("member.manualHint")}
              </p>
            </fieldset>
          )}

          {request.isError && !packsBlocked && (
            <p className="text-sm font-medium text-[var(--red-600)]">
              {getMessage(request.error)}
            </p>
          )}

          {/* History */}
          <History
            loading={historyQuery.isPending}
            items={historyQuery.data ?? []}
            locale={locale}
          />
        </div>
      )}
    </Modal>
  );
}

/* -------------------------------------------------------------------------- */

function OrgManagedNotice() {
  const t = useTranslations("aiEnergy");
  return (
    <div className="flex items-start gap-2.5 rounded-xl border border-[var(--border-default)] bg-[var(--bg-subtle)] px-3.5 py-3">
      <span className="flex size-8 shrink-0 items-center justify-center rounded-lg border border-[var(--border-default)] bg-[var(--surface-card)] text-[var(--text-secondary)]">
        <UsersThree aria-hidden weight="duotone" className="size-4" />
      </span>
      <div>
        <p className="text-sm font-semibold text-[var(--text-primary)]">
          {t("member.orgManagedTitle")}
        </p>
        <p className="mt-0.5 text-sm text-[var(--text-secondary)]">
          {t("member.orgManagedBody")}
        </p>
      </div>
    </div>
  );
}

function TopupResultPanel({
  result,
  locale,
}: {
  result: AiEnergyTopupResult;
  locale: string;
}) {
  const t = useTranslations("aiEnergy");
  const inst = result.payment_instructions;

  return (
    <div className="space-y-4">
      <div className="flex items-start gap-2.5 rounded-xl border border-[var(--amber-400)] bg-[var(--amber-50)] px-3.5 py-3">
        <Clock
          aria-hidden
          weight="duotone"
          className="mt-0.5 size-5 shrink-0 text-[var(--amber-700)]"
        />
        <div>
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            {t("member.pendingTitle")}
          </p>
          <p className="mt-0.5 text-sm text-[var(--text-secondary)]">
            {t("member.pendingBody", {
              units: formatUnits(result.units, locale),
              price: formatVnd(result.price_amount, result.currency, locale),
            })}
          </p>
        </div>
      </div>

      <div className="rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] p-4">
        <div className="mb-2 flex items-center gap-2">
          <span className="flex size-7 items-center justify-center rounded-lg icon-chip-primary shadow-sm">
            <Bank aria-hidden weight="duotone" className="size-4 text-white" />
          </span>
          <h4 className="text-sm font-bold text-[var(--text-primary)]">
            {t("member.bank.title")}
          </h4>
        </div>
        <p className="mb-3 text-sm text-[var(--text-secondary)]">
          {t("member.bank.intro")}
        </p>
        <dl className="space-y-1.5 text-sm">
          <BankRow label={t("member.bank.bank")} value={inst.bank_name} />
          <BankRow
            label={t("member.bank.accountName")}
            value={inst.account_name}
          />
          <BankRow
            label={t("member.bank.accountNumber")}
            value={inst.account_number}
            mono
          />
          <BankRow
            label={t("member.bank.reference")}
            value={inst.reference_hint}
            mono
            highlight
          />
        </dl>
        <p className="mt-3 text-xs text-[var(--text-muted)]">
          {t("member.bank.doneHint")}
        </p>
      </div>
    </div>
  );
}

function BankRow({
  label,
  value,
  mono,
  highlight,
}: {
  label: string;
  value: string;
  mono?: boolean;
  highlight?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-[var(--text-secondary)]">{label}</dt>
      <dd
        className={cn(
          mono ? "font-mono" : "font-semibold",
          highlight ? "text-[var(--text-primary)] underline" : "text-[var(--text-primary)]",
        )}
      >
        {value}
      </dd>
    </div>
  );
}

function History({
  loading,
  items,
  locale,
}: {
  loading: boolean;
  items: AiEnergyTopup[];
  locale: string;
}) {
  const t = useTranslations("aiEnergy");

  return (
    <div>
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        {t("member.history.title")}
      </p>
      {loading ? (
        <div className="space-y-1.5">
          <Skeleton className="h-5 w-full" />
          <Skeleton className="h-5 w-full" />
        </div>
      ) : items.length === 0 ? (
        <p className="text-sm text-[var(--text-muted)]">
          {t("member.history.empty")}
        </p>
      ) : (
        <ul className="divide-y divide-[var(--border-default)]">
          {items.map((it) => (
            <li
              key={it.id}
              className="flex items-center justify-between gap-3 py-2 text-sm"
            >
              <span className="flex items-center gap-2">
                <CheckCircle
                  aria-hidden
                  weight={it.status === "paid" ? "fill" : "regular"}
                  className={cn(
                    "size-4 shrink-0",
                    it.status === "paid"
                      ? "text-[var(--teal-600)]"
                      : "text-[var(--text-muted)]",
                  )}
                />
                <span className="text-[var(--text-secondary)]">
                  {t("member.packUnits", {
                    units: formatUnits(it.units, locale),
                  })}
                  <span className="ml-1.5 tabular-nums text-[var(--text-muted)]">
                    {formatVnd(it.price_amount, it.currency, locale)}
                  </span>
                </span>
              </span>
              <span className="flex items-center gap-2">
                <span className="hidden tabular-nums text-xs text-[var(--text-muted)] sm:inline">
                  {formatDate(it.created_at, locale)}
                </span>
                <StatusBadge tone={TOPUP_STATUS_TONE[it.status]}>
                  {it.status_label}
                </StatusBadge>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
