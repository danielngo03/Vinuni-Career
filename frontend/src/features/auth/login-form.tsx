"use client";

import {
  ArrowRight,
  Buildings,
  EnvelopeSimple,
  Eye,
  EyeSlash,
  GoogleLogo,
  GraduationCap,
  LockKey,
  MicrosoftOutlookLogo,
  ShieldCheck,
  SpinnerGap,
  UserCircle,
} from "@phosphor-icons/react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RegistrationOnboarding } from "@/features/auth/registration-onboarding";
import type { Identity } from "@/lib/api/types";
import { cn } from "@/lib/utils";

type AuthMode = "login" | "register";

export function LoginForm({
  locale,
  oidc,
}: {
  locale: string;
  oidc: { google: boolean; microsoft: boolean };
}) {
  const router = useRouter();
  const vi = locale === "vi";
  const [mode, setMode] = useState<AuthMode>("login");
  const [email, setEmail] = useState("student@vinuni.edu.vn");
  const [password, setPassword] = useState("password123");
  const [visible, setVisible] = useState(false);
  const [pending, setPending] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const hasOidc = oidc.google || oidc.microsoft;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setErrorMessage("");
    setPending(true);
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          password,
          device_info: navigator.userAgent.slice(0, 200),
        }),
      });
      const body = (await response.json()) as {
        detail?: string;
        error?: { message?: string };
        identities?: Identity[];
        access_scope?: string;
      };
      if (!response.ok) {
        throw new Error(
          body.detail ||
            body.error?.message ||
            (vi ? "Không thể đăng nhập." : "Unable to sign in."),
        );
      }
      const identities = body.identities || [];
      if (body.access_scope === "registration:pending") {
        toast.success(
          vi ? "Đã mở cổng theo dõi hồ sơ" : "Registration portal opened",
        );
        router.push(`/${locale}/pending`);
        router.refresh();
        return;
      }
      if (!identities.length) {
        throw new Error(
          vi
            ? "Tài khoản chưa được cấp workspace hoặc hồ sơ vẫn đang chờ duyệt."
            : "No workspace is assigned or the registration is still pending.",
        );
      }
      toast.success(vi ? "Đăng nhập thành công" : "Signed in successfully");
      router.push(
        identities.length > 1
          ? `/${locale}/select-identity`
          : `/${locale}/${identities[0].portal}`,
      );
      router.refresh();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Authentication failed";
      setErrorMessage(message);
      toast.error(message);
    } finally {
      setPending(false);
    }
  }

  return (
    <div>
      <div className="mb-7 grid grid-cols-2 rounded-xl bg-slate-100 p-1">
        {(["login", "register"] as const).map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => {
              setMode(item);
              setErrorMessage("");
            }}
            className={cn(
              "focus-ring cursor-pointer rounded-lg px-4 py-2.5 text-sm font-semibold transition-all",
              mode === item
                ? "bg-white text-foreground shadow-sm"
                : "text-slate-500 hover:text-foreground",
            )}
          >
            {item === "login"
              ? vi
                ? "Đăng nhập"
                : "Sign in"
              : vi
                ? "Đăng ký tài khoản"
                : "Register"}
          </button>
        ))}
      </div>

      {mode === "register" ? (
        <RegistrationOnboarding
          locale={locale}
          onComplete={(registeredEmail) => {
            setEmail(registeredEmail);
            setPassword("");
            setMode("login");
          }}
        />
      ) : (
        <form onSubmit={submit} className="space-y-5" noValidate>
          {hasOidc ? (
            <>
              <div className="grid gap-3 sm:grid-cols-2">
                {oidc.microsoft ? (
                  <Button variant="outline" type="button" asChild className="h-12 rounded-xl">
                    <a href={`/api/auth/oidc/microsoft?locale=${locale}`}>
                      <MicrosoftOutlookLogo
                        className="size-5 text-[#106ebe]"
                        weight="fill"
                      />
                      Microsoft
                    </a>
                  </Button>
                ) : null}
                {oidc.google ? (
                  <Button variant="outline" type="button" asChild className="h-12 rounded-xl">
                    <a href={`/api/auth/oidc/google?locale=${locale}`}>
                      <GoogleLogo className="size-5 text-[#4285f4]" weight="bold" />
                      Google
                    </a>
                  </Button>
                ) : null}
              </div>
              <Divider label={vi ? "hoặc dùng email" : "or continue with email"} />
            </>
          ) : null}

          <Field
            id="email"
            label={vi ? "Email trường hoặc công việc" : "University or work email"}
            icon={EnvelopeSimple}
          >
            <Input
              id="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);
                setErrorMessage("");
              }}
              placeholder="name@vinuni.edu.vn"
              required
              disabled={pending}
              className="h-12 rounded-xl pl-12"
            />
          </Field>

          <div>
            <div className="mb-2 flex items-center justify-between">
              <label htmlFor="password" className="text-sm font-semibold">
                {vi ? "Mật khẩu" : "Password"}
              </label>
              <button
                type="button"
                className="focus-ring cursor-pointer rounded text-xs font-semibold text-primary hover:underline"
                onClick={() =>
                  toast.info(
                    vi
                      ? "Liên hệ quản trị viên để đặt lại mật khẩu."
                      : "Contact an administrator to reset your password.",
                  )
                }
              >
                {vi ? "Quên mật khẩu?" : "Forgot password?"}
              </button>
            </div>
            <div className="relative">
              <LockKey className="pointer-events-none absolute left-4 top-1/2 size-5 -translate-y-1/2 text-slate-400" />
              <Input
                id="password"
                type={visible ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(event) => {
                  setPassword(event.target.value);
                  setErrorMessage("");
                }}
                required
                minLength={8}
                disabled={pending}
                className="h-12 rounded-xl px-12"
              />
              <button
                type="button"
                className="focus-ring absolute right-2 top-1/2 -translate-y-1/2 cursor-pointer rounded-md p-2 text-muted hover:text-foreground"
                onClick={() => setVisible((value) => !value)}
                aria-label={visible ? "Hide password" : "Show password"}
              >
                {visible ? <EyeSlash className="size-4" /> : <Eye className="size-4" />}
              </button>
            </div>
          </div>

          {errorMessage ? (
            <div
              role="alert"
              aria-live="polite"
              className="flex items-start gap-2.5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
            >
              <ShieldCheck className="mt-0.5 size-5 shrink-0" />
              <span>{errorMessage}</span>
            </div>
          ) : null}

          <Button
            type="submit"
            size="lg"
            className="h-12 w-full rounded-xl shadow-[0_12px_26px_-12px_rgba(15,92,229,0.8)]"
            disabled={pending || !email.trim() || password.length < 8}
          >
            {pending ? (
              <SpinnerGap className="size-5 animate-spin" />
            ) : (
              <ArrowRight className="size-4" />
            )}
            {pending
              ? vi
                ? "Đang xác thực..."
                : "Signing in..."
              : vi
                ? "Đăng nhập"
                : "Sign in"}
          </Button>

          <DemoAccounts
            vi={vi}
            pending={pending}
            onSelect={(account) => {
              setEmail(account);
              setPassword("password123");
              setErrorMessage("");
            }}
          />
        </form>
      )}
    </div>
  );
}

function Field({
  id,
  label,
  icon: Icon,
  children,
}: {
  id: string;
  label: string;
  icon: typeof EnvelopeSimple;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label htmlFor={id} className="mb-2 block text-sm font-semibold">
        {label}
      </label>
      <div className="relative">
        <Icon className="pointer-events-none absolute left-4 top-1/2 z-10 size-5 -translate-y-1/2 text-slate-400" />
        {children}
      </div>
    </div>
  );
}

function Divider({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3">
      <div className="h-px flex-1 bg-border" />
      <span className="text-xs font-medium text-muted">{label}</span>
      <div className="h-px flex-1 bg-border" />
    </div>
  );
}

function DemoAccounts({
  vi,
  pending,
  onSelect,
}: {
  vi: boolean;
  pending: boolean;
  onSelect: (account: string) => void;
}) {
  return (
    <details className="group border-t pt-5">
      <summary className="focus-ring flex cursor-pointer list-none items-center justify-between rounded text-sm font-semibold text-slate-600">
        <span>{vi ? "Dùng tài khoản trải nghiệm" : "Use a demo account"}</span>
        <span className="text-xs font-medium text-primary group-open:hidden">
          {vi ? "Hiển thị" : "Show"}
        </span>
        <span className="hidden text-xs font-medium text-primary group-open:inline">
          {vi ? "Thu gọn" : "Hide"}
        </span>
      </summary>
      <div className="mt-3 grid grid-cols-3 gap-2">
        {[
          [GraduationCap, vi ? "Sinh viên" : "Student", "student@vinuni.edu.vn"],
          [Buildings, vi ? "Đối tác" : "Partner", "hr@partner.vn"],
          [UserCircle, vi ? "Nhà trường" : "University", "career.center@vinuni.edu.vn"],
        ].map(([Icon, label, account]) => (
          <button
            key={String(account)}
            type="button"
            onClick={() => onSelect(String(account))}
            disabled={pending}
            className="focus-ring flex cursor-pointer flex-col items-center gap-1.5 rounded-xl border px-2 py-3 text-xs font-semibold text-slate-600 transition-colors hover:border-blue-300 hover:bg-blue-50 hover:text-primary disabled:pointer-events-none disabled:opacity-50"
          >
            <Icon className="size-5" />
            {String(label)}
          </button>
        ))}
      </div>
    </details>
  );
}
