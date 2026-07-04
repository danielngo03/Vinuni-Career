"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle, CircleNotch } from "@phosphor-icons/react";
import { Button } from "@/components/ui";
import { Link } from "@/i18n/navigation";
import { authApi } from "@/lib/api";
import { useApiErrorMessage, getRetryAfterSeconds } from "@/lib/auth/use-api-error";
import { useCooldown } from "@/lib/auth/use-cooldown";
import { useTranslations } from "next-intl";
import { AuthShell } from "./auth-shell";
import { FormBanner } from "./form-banner";

// ── OTP Input component — 6 individual digit boxes ──────────────────────────
export function OtpInput({
  value,
  onChange,
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
}) {
  const inputs = useRef<Array<HTMLInputElement | null>>([]);

  const handleKey = (i: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Backspace" && !value[i] && i > 0) {
      inputs.current[i - 1]?.focus();
    }
  };

  const handleChange = (i: number, ch: string) => {
    const digits = ch.replace(/\D/g, "").slice(-1);
    const arr = value.split("");
    arr[i] = digits;
    const next = arr.join("").padEnd(6, "").slice(0, 6);
    onChange(next.trimEnd() === "" ? next.trimEnd() : next);
    if (digits && i < 5) {
      inputs.current[i + 1]?.focus();
    }
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    const text = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
    if (text.length === 6) {
      onChange(text);
      inputs.current[5]?.focus();
    }
  };

  return (
    <div className="flex gap-2 justify-center" onPaste={handlePaste}>
      {Array.from({ length: 6 }).map((_, i) => (
        <input
          key={i}
          ref={(el) => {
            inputs.current[i] = el;
          }}
          type="text"
          inputMode="numeric"
          maxLength={1}
          value={value[i] ?? ""}
          disabled={disabled}
          onChange={(e) => handleChange(i, e.target.value)}
          onKeyDown={(e) => handleKey(i, e)}
          onClick={(e) => (e.target as HTMLInputElement).select()}
          className="h-12 w-10 rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] text-center text-lg font-bold text-[var(--text-primary)] outline-none transition-[border-color,box-shadow,background-color] duration-150 focus:border-[var(--field-focus-border)] focus:shadow-[0_0_0_4px_var(--field-focus-ring)] focus:ring-0 disabled:bg-[var(--bg-muted)] disabled:text-[var(--text-muted)]"
          aria-label={`Chữ số ${i + 1}`}
        />
      ))}
    </div>
  );
}

// ── Main verify-email view ────────────────────────────────────────────────────
export function VerifyEmailView({
  token,
  email,
  onBack,
}: {
  token?: string;
  email?: string;
  onBack?: () => void;
}) {
  const tAuth = useTranslations("auth");
  const getMessage = useApiErrorMessage();
  const started = useRef(false);
  const [resent, setResent] = useState(false);
  const [otp, setOtp] = useState("");
  const [mode, setMode] = useState<"otp" | "link">(token ? "link" : "otp");
  const [resendError, setResendError] = useState<string | null>(null);
  const cooldown = useCooldown();

  // Magic-link auto-verify
  const verifyLink = useMutation({
    mutationFn: (tok: string) => authApi.verifyEmail({ token: tok }),
  });

  // OTP verify
  const verifyOtp = useMutation({
    mutationFn: ({ email: addr, code }: { email: string; code: string }) =>
      authApi.verifyEmailOtp({ email: addr, otp_code: code }),
  });

  const resend = useMutation({
    mutationFn: (addr: string) => authApi.resendVerification({ email: addr }),
    onSuccess: () => {
      setResent(true);
      setResendError(null);
      setOtp("");
    },
    onError: (err) => {
      const retryAfter = getRetryAfterSeconds(err);
      if (retryAfter) cooldown.start(retryAfter);
      setResendError(getMessage(err));
    },
  });

  // Auto-verify magic link
  useEffect(() => {
    if (token && mode === "link" && !started.current) {
      started.current = true;
      verifyLink.mutate(token);
    }
  }, [token, mode, verifyLink]);

  // Auto-submit OTP when all 6 digits filled
  useEffect(() => {
    if (otp.length === 6 && email && mode === "otp" && !verifyOtp.isPending) {
      verifyOtp.mutate({ email, code: otp });
    }
  }, [otp]); // eslint-disable-line react-hooks/exhaustive-deps

  const loginFooter = (
    <Link href="/auth/login" className="font-semibold text-[var(--ink)] hover:underline">
      Quay lại đăng nhập
    </Link>
  );
  const backControl = onBack ? (
    <button
      type="button"
      onClick={onBack}
      className="inline-flex items-center gap-2 rounded-full px-1 text-sm font-semibold text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--field-focus-ring)]"
    >
      <ArrowLeft aria-hidden className="size-4" />
      Quay lại
    </button>
  ) : null;

  // ── Success state ──────────────────────────────────────────────────────────
  const isSuccess = verifyLink.isSuccess || verifyOtp.isSuccess;
  if (isSuccess) {
    return (
      <AuthShell title="Email đã được xác minh!" footer={loginFooter}>
        <div className="space-y-5 text-center">
          <span className="mx-auto flex size-14 items-center justify-center rounded-2xl bg-gray-900 shadow-lg">
            <CheckCircle aria-hidden weight="fill" className="size-7 text-white" />
          </span>
          <p className="text-sm text-[var(--text-secondary)]">
            Địa chỉ email của bạn đã được xác minh thành công. Bây giờ hãy hoàn thiện hồ sơ.
          </p>
          <Link
            href="/onboarding/role"
            className="inline-flex h-11 w-full items-center justify-center rounded-xl bg-[var(--ink)] px-5 text-sm font-semibold text-white transition-colors hover:bg-gray-800"
          >
            Tiếp tục thiết lập hồ sơ →
          </Link>
        </div>
      </AuthShell>
    );
  }

  // ── Magic-link verifying ───────────────────────────────────────────────────
  if (token && mode === "link" && (verifyLink.isPending || verifyLink.isIdle)) {
    return (
      <AuthShell title="Đang xác minh...">
        <div className="flex flex-col items-center gap-3 py-4 text-center">
          <CircleNotch aria-hidden className="size-8 animate-spin text-[var(--ink)]" />
          <p className="text-sm text-[var(--text-secondary)]">Đang xác minh liên kết của bạn...</p>
        </div>
      </AuthShell>
    );
  }

  // ── OTP entry mode (main UI after registration) ────────────────────────────
  const otpError = verifyOtp.isError
    ? getMessage(verifyOtp.error)
    : verifyLink.isError && mode === "link"
    ? "Liên kết không hợp lệ hoặc đã hết hạn."
    : null;

  return (
    <AuthShell
      title="Xác minh email"
      subtitle={
        email
          ? `Nhập mã 6 số đã gửi đến ${email}`
          : "Nhập mã xác minh từ email của bạn"
      }
      beforeTitle={backControl}
      footer={onBack ? undefined : loginFooter}
    >
      <div className="space-y-5">
        {otpError && (
          <FormBanner title="Xác minh thất bại">
            {otpError}
          </FormBanner>
        )}

        {resent && (
          <FormBanner tone="success">
            Đã gửi lại mã xác minh. Vui lòng kiểm tra email.
          </FormBanner>
        )}

        {resendError && (
          <FormBanner tone={cooldown.active ? "info" : "error"}>
            {resendError}
          </FormBanner>
        )}

        {/* OTP boxes */}
        <OtpInput
          value={otp}
          onChange={setOtp}
          disabled={verifyOtp.isPending}
        />

        {verifyOtp.isPending && (
          <div className="flex justify-center">
            <CircleNotch aria-hidden className="size-5 animate-spin text-[var(--ink)]" />
          </div>
        )}

        {/* Resend */}
        {email ? (
          <Button
            variant="secondary"
            fullWidth
            loading={resend.isPending}
            disabled={cooldown.active}
            onClick={() => {
              setResent(false);
              resend.mutate(email);
            }}
          >
            {cooldown.active
              ? `${tAuth("forgotResend")} (${cooldown.seconds}s)`
              : "Gửi lại mã xác minh"}
          </Button>
        ) : (
          <p className="text-center text-sm text-[var(--text-secondary)]">
            Vui lòng kiểm tra hộp thư của bạn và nhập mã bên trên.
          </p>
        )}

        {/* Switch to magic link if they have a token param */}
        {token && mode === "otp" && (
          <button
            type="button"
            className="w-full text-center text-xs text-[var(--text-tertiary)] hover:text-[var(--ink)] transition-colors underline underline-offset-2"
            onClick={() => {
              setMode("link");
              if (!started.current) {
                started.current = true;
                verifyLink.mutate(token);
              }
            }}
          >
            Xác minh tự động bằng liên kết trong email →
          </button>
        )}
      </div>
    </AuthShell>
  );
}
