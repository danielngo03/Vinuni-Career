"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { CheckCircle, UsersThree, SignIn } from "@phosphor-icons/react";
import { Button } from "@/components/ui";
import { Link, useRouter } from "@/i18n/navigation";
import { ApiError, authApi, organizationApi } from "@/lib/api";
import { useAuthStore, normalizePersona } from "@/stores/auth-store";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";

type Phase = "idle" | "accepting" | "done";

export function InvitationAcceptView({ token }: { token?: string }) {
  const t = useTranslations("inviteAccept");
  const tc = useTranslations("common");
  const getMessage = useApiErrorMessage();
  const router = useRouter();

  const status = useAuthStore((s) => s.status);
  const user = useAuthStore((s) => s.user);
  const selectIdentity = useAuthStore((s) => s.selectIdentity);

  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [landed, setLanded] = useState<"partner" | "university" | null>(null);

  const acceptPath = `/organizations/invitations/accept?token=${encodeURIComponent(
    token ?? "",
  )}`;

  async function accept() {
    if (!token) return;
    setPhase("accepting");
    setError(null);
    try {
      // Snapshot identities before so we can find the newly created one.
      const before = new Set(
        (await authApi.listIdentities()).map((i) => i.id),
      );
      await organizationApi.acceptInvitation(token);
      const after = await authApi.listIdentities();
      const fresh =
        after.find((i) => !before.has(i.id)) ??
        after.find((i) => i.org_id) ??
        after[0];
      if (fresh) {
        // Switch active identity into the org so the user can act there.
        await selectIdentity(fresh.id);
        const persona = normalizePersona(fresh.persona);
        setLanded(persona === "university" ? "university" : "partner");
      } else {
        setLanded("partner");
      }
      setPhase("done");
    } catch (err) {
      setPhase("idle");
      if (err instanceof ApiError) {
        const reason =
          typeof err.details?.reason === "string" ? err.details.reason : undefined;
        if (err.code === "CONFLICT" || reason === "already_member") {
          setError(t("alreadyMember"));
          return;
        }
        if (reason === "invite_email_mismatch" || err.isPermissionError) {
          setError(t("emailMismatch"));
          return;
        }
        if (reason === "invite_expired") {
          setError(t("expired"));
          return;
        }
        if (reason === "invite_used") {
          setError(t("used"));
          return;
        }
        if (reason === "invite_invalid" || err.code === "VALIDATION_FAILED") {
          setError(t("invalid"));
          return;
        }
      }
      setError(getMessage(err));
    }
  }

  return (
    <Shell>
      {!token ? (
        <State
          tone="error"
          icon={<UsersThree aria-hidden weight="duotone" className="size-7" />}
          title={t("invalidTitle")}
          body={t("invalidBody")}
        />
      ) : status === "unknown" ? (
        <State title={tc("loading")} body="" busy />
      ) : status === "guest" ? (
        <State
          tone="auth"
          icon={<SignIn aria-hidden weight="duotone" className="size-7" />}
          title={t("loginTitle")}
          body={t("loginBody")}
          action={
            <Button
              variant="primary"
              size="lg"
              onClick={() =>
                router.push(`/auth/login?returnTo=${encodeURIComponent(acceptPath)}`)
              }
            >
              {t("loginCta")}
            </Button>
          }
        />
      ) : phase === "done" ? (
        <State
          tone="success"
          icon={<CheckCircle aria-hidden weight="duotone" className="size-7" />}
          title={t("doneTitle")}
          body={t("doneBody")}
          action={
            <Button
              variant="primary"
              size="lg"
              onClick={() =>
                router.replace(`/${landed ?? "partner"}/dashboard`)
              }
            >
              {t("openWorkspace")}
            </Button>
          }
        />
      ) : (
        <State
          tone="auth"
          icon={<UsersThree aria-hidden weight="duotone" className="size-7" />}
          title={t("title")}
          body={t("body", { email: user?.email ?? "" })}
          error={error}
          action={
            <div className="flex flex-col gap-2 sm:flex-row">
              <Button
                variant="primary"
                size="lg"
                loading={phase === "accepting"}
                onClick={accept}
              >
                {t("accept")}
              </Button>
              <Link
                href="/"
                className="inline-flex h-10 items-center justify-center rounded-lg px-5 text-sm font-semibold text-[var(--text-secondary)] outline-none transition-colors hover:bg-[var(--bg-subtle)]"
              >
                {tc("cancel")}
              </Link>
            </div>
          }
        />
      )}
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-[calc(100dvh-60px)] w-full items-center justify-center bg-[var(--bg-subtle)] px-4 py-10">
      <div className="w-full max-w-md rounded-2xl border border-white/60 bg-white/82 p-8 text-center shadow-[0_4px_20px_rgba(11,34,57,0.08)] backdrop-blur-md">
        {children}
      </div>
    </div>
  );
}

const TONE: Record<string, string> = {
  auth: "icon-chip-primary text-white shadow-sm",
  success: "icon-chip-success text-white shadow-sm",
  error: "icon-chip-danger text-white shadow-sm",
};

function State({
  tone = "auth",
  icon,
  title,
  body,
  error,
  action,
  busy,
}: {
  tone?: string;
  icon?: React.ReactNode;
  title: string;
  body: string;
  error?: string | null;
  action?: React.ReactNode;
  busy?: boolean;
}) {
  return (
    <div className="space-y-4">
      {icon && (
        <span
          className={`mx-auto flex size-14 items-center justify-center rounded-2xl ${TONE[tone]}`}
        >
          {icon}
        </span>
      )}
      <h1 className="text-xl font-bold tracking-tight text-[var(--text-primary)]">
        {title}
      </h1>
      {body && <p className="text-sm text-[var(--text-secondary)]">{body}</p>}
      {busy && (
        <span
          role="status"
          className="mx-auto block size-5 animate-spin rounded-full border-2 border-[var(--brand-primary)] border-t-transparent"
        />
      )}
      {error && (
        <p
          role="alert"
          className="rounded-xl border border-[var(--red-400)]/40 bg-[var(--red-50)] px-3 py-2 text-sm font-medium text-[var(--brand-red)]"
        >
          {error}
        </p>
      )}
      {action && <div className="flex justify-center pt-1">{action}</div>}
    </div>
  );
}
