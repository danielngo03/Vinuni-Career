"use client";

import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";

/**
 * AI interviewer avatar — a professional, human-looking illustrated portrait
 * (SVG) whose MOUTH is driven by the interviewer's live audio amplitude, like a
 * person talking on a video call.
 *
 * How the lip movement is driven (the important bit):
 * - The parent passes `getLevel()`, a smoothed 0..1 amplitude read from the
 *   ACTUAL interviewer audio via `Pcm24Player.level` on the realtime voice tiers
 *   (relay / descriptor) — a pure side-tap that never touches playback.
 * - A single `requestAnimationFrame` loop maps that level to how far the mouth
 *   opens (fast attack / slower release so it reads naturally, never jittery).
 * - When there is NO amplitude source (the turn-based TTS tier or browser
 *   speech-synthesis, where `getLevel()` stays ~0) but `state === "speaking"`, a
 *   gentle synthetic talk envelope keeps the mouth alive so the avatar still
 *   "speaks" in every tier.
 * - Idle/listening: no mouth movement, just soft breathing + occasional blink.
 *
 * The avatar is DECORATIVE — captions are the accessibility layer — so the whole
 * SVG is `aria-hidden`. Under `prefers-reduced-motion` it renders as a calm
 * static portrait (no breathing / blink / talking).
 */

export type AvatarState = "idle" | "listening" | "speaking" | "thinking";

interface Props {
  state: AvatarState;
  /** Smoothed 0..1 interviewer-audio amplitude (real playback level). */
  getLevel?: () => number;
  reduced?: boolean;
  className?: string;
}

export function InterviewerAvatar({ state, getLevel, reduced = false, className }: Props) {
  const stateRef = useRef<AvatarState>(state);
  const levelRef = useRef<() => number>(getLevel ?? (() => 0));

  const bustRef = useRef<SVGGElement>(null);
  const headRef = useRef<SVGGElement>(null);
  const browsRef = useRef<SVGGElement>(null);
  const lidLRef = useRef<SVGGElement>(null);
  const lidRRef = useRef<SVGGElement>(null);
  const mouthOpenRef = useRef<SVGGElement>(null);
  const lowerLipRef = useRef<SVGGElement>(null);
  const teethRef = useRef<SVGRectElement>(null);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);
  useEffect(() => {
    levelRef.current = getLevel ?? (() => 0);
  }, [getLevel]);

  useEffect(() => {
    if (reduced) return; // static portrait under reduced motion

    let raf = 0;
    let mouth = 0; // current mouth openness 0..1
    let brow = 0; // current brow raise 0..1
    let lastRealAt = -9999;
    let nextBlinkAt = performance.now() + 1600;
    let blinkStart = -9999;

    const loop = () => {
      const now = performance.now();
      const s = stateRef.current;

      /* ---- breathing (whole bust) ---- */
      const breathe = Math.sin(now / 2600);
      if (bustRef.current) {
        bustRef.current.style.transform = `translateY(${(breathe * 1.5).toFixed(2)}px) scaleY(${(1 + (breathe + 1) * 0.002).toFixed(4)})`;
      }

      /* ---- head sway ---- */
      const sway = Math.sin(now / 1500);
      const sway2 = Math.sin(now / 2300 + 1.1);
      const swayAmt = s === "speaking" ? 1.5 : s === "thinking" ? 0.9 : 0.5;
      if (headRef.current) {
        const tilt = s === "thinking" ? -1.6 : 0;
        headRef.current.style.transform = `translateX(${(sway * swayAmt * 0.6).toFixed(2)}px) rotate(${(sway * swayAmt + tilt + sway2 * 0.3).toFixed(2)}deg)`;
      }

      /* ---- mouth (audio-driven) ---- */
      const real = levelRef.current();
      if (real > 0.05) lastRealAt = now;
      const hasReal = now - lastRealAt < 650;
      let mouthTarget = 0;
      if (s === "speaking") {
        if (hasReal) {
          mouthTarget = Math.min(1, real * 1.15);
        } else {
          // No amplitude signal available → gentle synthetic talk envelope.
          const a = 0.5 + 0.5 * Math.sin(now / 92);
          const b = 0.5 + 0.5 * Math.sin(now / 149 + 1.3);
          mouthTarget = 0.14 + 0.42 * a * b;
        }
      }
      // Fast attack, gentler release for a lifelike mouth.
      mouth += (mouthTarget - mouth) * (mouthTarget > mouth ? 0.5 : 0.28);
      if (mouthOpenRef.current) {
        mouthOpenRef.current.style.transform = `scaleY(${(0.05 + mouth * 0.95).toFixed(3)})`;
      }
      if (lowerLipRef.current) {
        lowerLipRef.current.style.transform = `translateY(${(mouth * 5.5).toFixed(2)}px)`;
      }
      if (teethRef.current) {
        teethRef.current.style.opacity = Math.min(1, Math.max(0, mouth * 2.4 - 0.2)).toFixed(2);
      }

      /* ---- brows (slight lift while speaking) ---- */
      const browTarget = s === "speaking" ? 0.5 + 0.5 * Math.sin(now / 900) : s === "thinking" ? 0.2 : 0;
      brow += (browTarget - brow) * 0.08;
      if (browsRef.current) {
        browsRef.current.style.transform = `translateY(${(-brow * 2.2).toFixed(2)}px)`;
      }

      /* ---- blink ---- */
      if (now >= nextBlinkAt && blinkStart < 0) {
        blinkStart = now;
        nextBlinkAt = now + 2400 + Math.random() * 3200;
      }
      let lid = 0; // 0 open, 1 closed
      if (blinkStart >= 0) {
        const dt = now - blinkStart;
        if (dt < 70) lid = dt / 70;
        else if (dt < 150) lid = 1 - (dt - 70) / 80;
        else {
          lid = 0;
          blinkStart = -9999;
        }
      }
      const lidT = `scaleY(${lid.toFixed(3)})`;
      if (lidLRef.current) lidLRef.current.style.transform = lidT;
      if (lidRRef.current) lidRRef.current.style.transform = lidT;

      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [reduced]);

  // fill-box origins so CSS transforms rotate/scale about each part's own centre.
  const originCenter = { transformBox: "fill-box", transformOrigin: "center" } as const;
  const originTop = { transformBox: "fill-box", transformOrigin: "center top" } as const;

  return (
    <svg
      viewBox="0 0 260 300"
      className={cn("h-full w-full", className)}
      aria-hidden
      focusable="false"
      preserveAspectRatio="xMidYMid slice"
    >
      <defs>
        <linearGradient id="mi-skin" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#f3cdb0" />
          <stop offset="0.55" stopColor="#e7b393" />
          <stop offset="1" stopColor="#d89e7c" />
        </linearGradient>
        <linearGradient id="mi-hair" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#4a3b34" />
          <stop offset="1" stopColor="#261c18" />
        </linearGradient>
        <linearGradient id="mi-blazer" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#33405f" />
          <stop offset="1" stopColor="#1f273f" />
        </linearGradient>
        <linearGradient id="mi-shirt" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#ffffff" />
          <stop offset="1" stopColor="#e8edf5" />
        </linearGradient>
        <radialGradient id="mi-cheek" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0" stopColor="#e0876f" stopOpacity="0.2" />
          <stop offset="1" stopColor="#e0876f" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* bust — breathes */}
      <g ref={bustRef} style={originCenter}>
        {/* shoulders + blazer */}
        <path
          d="M20 300 C22 246 62 214 104 205 L156 205 C198 214 238 246 240 300 Z"
          fill="url(#mi-blazer)"
        />
        {/* shirt V / collar */}
        <path d="M104 205 L130 250 L156 205 L150 205 L130 236 L110 205 Z" fill="url(#mi-shirt)" />
        <path d="M112 206 L130 240 L148 206 Z" fill="url(#mi-shirt)" />
        {/* blazer lapels */}
        <path d="M104 205 L130 250 L118 205 Z" fill="#2a3450" opacity="0.9" />
        <path d="M156 205 L130 250 L142 205 Z" fill="#2a3450" opacity="0.9" />
        {/* neck */}
        <path d="M112 188 C112 214 118 224 130 224 C142 224 148 214 148 188 Z" fill="url(#mi-skin)" />
        <path d="M112 190 C118 206 142 206 148 190 L148 200 C140 210 120 210 112 200 Z" fill="#c98f6d" opacity="0.5" />

        {/* head — sways */}
        <g ref={headRef} style={originCenter}>
          {/* ears */}
          <ellipse cx="67" cy="122" rx="10" ry="14" fill="url(#mi-skin)" />
          <ellipse cx="193" cy="122" rx="10" ry="14" fill="url(#mi-skin)" />
          {/* hair back */}
          <path d="M58 118 C56 62 96 34 130 34 C164 34 204 62 202 118 L202 150 C202 92 176 66 130 66 C84 66 58 92 58 150 Z" fill="url(#mi-hair)" />
          {/* face */}
          <path d="M64 116 C64 66 92 44 130 44 C168 44 196 66 196 116 C196 158 172 196 130 196 C88 196 64 158 64 116 Z" fill="url(#mi-skin)" />
          {/* jaw shading */}
          <path d="M74 138 C82 176 104 194 130 194 C156 194 178 176 186 138 C176 168 156 182 130 182 C104 182 84 168 74 138 Z" fill="#cf9370" opacity="0.35" />
          {/* cheeks */}
          <ellipse cx="97" cy="140" rx="17" ry="12" fill="url(#mi-cheek)" />
          <ellipse cx="163" cy="140" rx="17" ry="12" fill="url(#mi-cheek)" />
          {/* hair front / fringe */}
          <path d="M60 112 C58 66 92 42 130 42 C168 42 202 66 200 112 C196 92 188 82 176 80 C170 66 150 58 130 58 C104 58 82 72 78 96 C74 100 68 104 64 116 Z" fill="url(#mi-hair)" />
          <path d="M128 44 C150 46 172 60 176 82 C160 70 144 66 128 66 Z" fill="#382a24" opacity="0.7" />

          {/* brows */}
          <g ref={browsRef} style={originCenter}>
            <path d="M88 96 C97 90 111 90 120 95 C111 92 98 92 88 98 Z" fill="#2f2521" />
            <path d="M140 95 C149 90 163 90 172 96 C162 92 149 92 140 98 Z" fill="#2f2521" />
          </g>

          {/* eyes */}
          <g>
            {/* left */}
            <ellipse cx="104" cy="110" rx="15" ry="9.5" fill="#ffffff" />
            <circle cx="106" cy="110" r="6.6" fill="#5b4636" />
            <circle cx="106" cy="110" r="3" fill="#20140d" />
            <circle cx="108.4" cy="107.6" r="1.5" fill="#ffffff" opacity="0.9" />
            <path d="M89 110 A15 9.5 0 0 1 119 110" fill="none" stroke="#3a2c25" strokeWidth="1.4" strokeLinecap="round" opacity="0.5" />
            {/* upper lid (blink) — starts open (scaleY 0) */}
            <g ref={lidLRef} style={{ ...originTop, transform: "scaleY(0)" }}>
              <path d="M88 110 A16 10 0 0 1 120 110 L120 100 L88 100 Z" fill="url(#mi-skin)" />
              <path d="M89 110 A15 9.5 0 0 1 119 110" fill="none" stroke="#c98f6d" strokeWidth="1" opacity="0.6" />
            </g>
            {/* right */}
            <ellipse cx="156" cy="110" rx="15" ry="9.5" fill="#ffffff" />
            <circle cx="154" cy="110" r="6.6" fill="#5b4636" />
            <circle cx="154" cy="110" r="3" fill="#20140d" />
            <circle cx="156.4" cy="107.6" r="1.5" fill="#ffffff" opacity="0.9" />
            <path d="M141 110 A15 9.5 0 0 1 171 110" fill="none" stroke="#3a2c25" strokeWidth="1.4" strokeLinecap="round" opacity="0.5" />
            <g ref={lidRRef} style={{ ...originTop, transform: "scaleY(0)" }}>
              <path d="M140 110 A16 10 0 0 1 172 110 L172 100 L140 100 Z" fill="url(#mi-skin)" />
              <path d="M141 110 A15 9.5 0 0 1 171 110" fill="none" stroke="#c98f6d" strokeWidth="1" opacity="0.6" />
            </g>
          </g>

          {/* nose */}
          <path d="M130 116 L124 142 C124 148 136 148 136 142 L130 116 Z" fill="#d69a76" opacity="0.55" />
          <path d="M123 143 C126 148 134 148 137 143" fill="none" stroke="#c98a66" strokeWidth="1.4" strokeLinecap="round" opacity="0.6" />

          {/* mouth */}
          <g style={originCenter}>
            {/* dark opening — scaleY driven by audio; starts nearly closed */}
            <g ref={mouthOpenRef} style={{ ...originCenter, transform: "scaleY(0.06)" }}>
              <ellipse cx="130" cy="163" rx="16" ry="11" fill="#7a2f31" />
              {/* teeth band, fades in as mouth opens */}
              <rect ref={teethRef} x="116" y="153.5" width="28" height="5.5" rx="2.4" fill="#fbf4ef" opacity="0" />
            </g>
            {/* upper lip */}
            <path d="M113 160 C120 154 140 154 147 160 C140 158 120 158 113 160 Z" fill="#c07668" />
            {/* lower lip — translates down as mouth opens */}
            <g ref={lowerLipRef} style={originCenter}>
              <path d="M114 163 C120 172 140 172 146 163 C140 168 120 168 114 163 Z" fill="#cf8577" />
            </g>
          </g>
        </g>
      </g>
    </svg>
  );
}
