"use client";

import { useCallback, useEffect, useRef, useState, type RefObject } from "react";
import { useTranslations } from "next-intl";
import { CircleNotch, LockSimple, VideoCameraSlash } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";

/**
 * Optional student self-view camera, like a real video interview.
 *
 * PRIVACY: the camera is LOCAL ONLY — the stream is attached to a `<video>`
 * element and NEVER uploaded, recorded, or sent anywhere. It is off by default,
 * degrades gracefully when denied/absent, and its tracks are stopped on disable
 * and on unmount. Only the mic (owned separately by the voice tiers) is needed
 * for spoken answers; the camera is pure presence/comfort.
 */

export type SelfViewStatus = "off" | "starting" | "on" | "denied" | "unsupported";

export interface SelfViewCamera {
  status: SelfViewStatus;
  videoRef: RefObject<HTMLVideoElement | null>;
  supported: boolean;
  toggle: () => void;
  enable: () => void;
  disable: () => void;
}

export function useSelfViewCamera(): SelfViewCamera {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const wantOnRef = useRef(false);
  const [status, setStatus] = useState<SelfViewStatus>("off");

  const supported =
    typeof navigator !== "undefined" &&
    !!navigator.mediaDevices &&
    typeof navigator.mediaDevices.getUserMedia === "function";

  const stopStream = useCallback(() => {
    const s = streamRef.current;
    streamRef.current = null;
    if (s) s.getTracks().forEach((t) => t.stop());
    if (videoRef.current) videoRef.current.srcObject = null;
  }, []);

  const disable = useCallback(() => {
    wantOnRef.current = false;
    stopStream();
    setStatus("off");
  }, [stopStream]);

  const enable = useCallback(() => {
    if (!supported) {
      setStatus("unsupported");
      return;
    }
    if (wantOnRef.current) return;
    wantOnRef.current = true;
    setStatus("starting");
    void navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "user" }, audio: false })
      .then((stream) => {
        // Toggled off (or unmounted) while the prompt was open → drop it.
        if (!wantOnRef.current) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        setStatus("on");
      })
      .catch(() => {
        if (wantOnRef.current) setStatus("denied");
        wantOnRef.current = false;
      });
  }, [supported]);

  const toggle = useCallback(() => {
    if (status === "on" || status === "starting") disable();
    else enable();
  }, [status, disable, enable]);

  // Attach the live stream once the element is mounted and the camera is on.
  useEffect(() => {
    const el = videoRef.current;
    if (status === "on" && el && streamRef.current) {
      el.srcObject = streamRef.current;
      void el.play().catch(() => undefined);
    }
  }, [status]);

  // Always release the camera on unmount.
  useEffect(
    () => () => {
      wantOnRef.current = false;
      const s = streamRef.current;
      streamRef.current = null;
      if (s) s.getTracks().forEach((t) => t.stop());
    },
    [],
  );

  return { status, videoRef, supported, toggle, enable, disable };
}

/**
 * Picture-in-picture self-view tile for the interview stage. Shows the mirrored
 * local camera when on; a calm placeholder otherwise. Clicking the placeholder
 * toggles the camera (the controls bar also has a labelled camera button).
 */
export function SelfViewTile({ camera }: { camera: SelfViewCamera }) {
  const t = useTranslations("jobs.mockInterview");
  const { status, videoRef, toggle } = camera;
  const live = status === "on";

  return (
    <div className="pointer-events-auto w-28 sm:w-36 md:w-44">
      <div className="relative aspect-[4/3] overflow-hidden rounded-xl border border-white/15 bg-[var(--gray-900)] shadow-lg ring-1 ring-black/20">
        {/* video is always mounted so the stream can attach; hidden when off */}
        <video
          ref={videoRef}
          muted
          autoPlay
          playsInline
          className={cn(
            "size-full object-cover [transform:scaleX(-1)]",
            live ? "opacity-100" : "opacity-0",
          )}
        />
        {!live && (
          <button
            type="button"
            onClick={toggle}
            aria-label={t("cameraEnable")}
            className="absolute inset-0 flex flex-col items-center justify-center gap-1.5 text-center outline-none focus-visible:ring-2 focus-visible:ring-white/60"
          >
            {status === "starting" ? (
              <CircleNotch aria-hidden weight="bold" className="size-5 animate-spin text-white/80" />
            ) : (
              <VideoCameraSlash aria-hidden weight="fill" className="size-5 text-white/70" />
            )}
            <span className="px-1 text-[10px] font-semibold leading-tight text-white/70">
              {status === "starting"
                ? t("cameraStarting")
                : status === "denied"
                  ? t("cameraDenied")
                  : status === "unsupported"
                    ? t("cameraUnsupported")
                    : t("cameraOffTitle")}
            </span>
          </button>
        )}

        {/* self label + live dot */}
        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-center justify-between px-1.5 py-1">
          <span className="rounded bg-black/45 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-white/90">
            {t("selfViewLabel")}
          </span>
          {live && (
            <span aria-hidden className="flex items-center gap-1">
              <span className="size-1.5 rounded-full bg-[var(--viz-emerald)]" />
            </span>
          )}
        </div>
      </div>
      {/* privacy line — camera is local only, never uploaded */}
      <p className="mt-1 flex items-center justify-center gap-1 text-[9px] leading-tight text-white/55">
        <LockSimple aria-hidden weight="fill" className="size-2.5 shrink-0" />
        <span className="truncate">{t("cameraPrivacyShort")}</span>
      </p>
    </div>
  );
}
