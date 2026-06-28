"use client";

import { ArrowRight, Buildings, GraduationCap, SpinnerGap } from "@phosphor-icons/react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import type { Identity } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

export function IdentitySelector({
  locale,
  identities,
}: {
  locale: string;
  identities: Identity[];
}) {
  const router = useRouter();
  const [selected, setSelected] = useState(identities[0]?.id);
  const [pending, setPending] = useState(false);

  async function continueToWorkspace() {
    if (!selected) return;
    setPending(true);
    const response = await fetch("/api/auth/identity", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ identity_id: selected }),
    });
    if (!response.ok) {
      toast.error("Unable to select this workspace");
      setPending(false);
      return;
    }
    const identity = (await response.json()) as Identity;
    router.push(`/${locale}/${identity.portal}`);
    router.refresh();
  }

  return (
    <div className="space-y-3">
      {identities.map((identity) => {
        const active = selected === identity.id;
        const Icon = identity.portal === "partner" ? Buildings : GraduationCap;
        return (
          <button
            key={identity.id}
            type="button"
            onClick={() => setSelected(identity.id)}
            className={cn(
              "focus-ring flex w-full cursor-pointer items-center gap-4 rounded-xl border p-4 text-left transition-colors",
              active
                ? "border-primary bg-blue-50/70 ring-1 ring-primary"
                : "bg-white hover:border-blue-200 hover:bg-slate-50",
            )}
          >
            <div className="flex size-11 items-center justify-center rounded-xl bg-white text-primary shadow-sm ring-1 ring-slate-200">
              <Icon className="size-6" weight="duotone" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate font-semibold">{identity.org_name}</p>
              <p className="mt-1 text-sm text-muted">
                {identity.role_name} · {identity.portal}
              </p>
            </div>
            <span
              className={cn(
                "size-4 rounded-full border-2",
                active ? "border-[5px] border-primary" : "border-slate-300",
              )}
            />
          </button>
        );
      })}
      <Button
        size="lg"
        className="mt-4 w-full"
        onClick={continueToWorkspace}
        disabled={pending || !selected}
      >
        {pending ? (
          <SpinnerGap className="size-5 animate-spin" />
        ) : (
          <ArrowRight className="size-4" />
        )}
        Continue
      </Button>
    </div>
  );
}
