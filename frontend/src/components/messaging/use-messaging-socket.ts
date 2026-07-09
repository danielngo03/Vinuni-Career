"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { getAccessToken } from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";
import { apiWsUrl } from "./messaging-endpoints";
import {
  MESSAGING_INBOX_ROOT,
  MESSAGING_THREADS_KEY,
  MESSAGING_UNREAD_KEY,
  messagingThreadDetailKey,
  messagingThreadKey,
} from "./query-keys";

/** Lightweight signal from the messaging socket — `{type, thread_id?}`. */
export interface MessagingSocketEvent {
  type: string;
  thread_id?: string;
}

type EventListener = (evt: MessagingSocketEvent) => void;
type StatusListener = (connected: boolean) => void;

const MAX_BACKOFF_MS = 30_000;

/**
 * ONE app-wide messaging WebSocket, ref-counted across every hook consumer so
 * mounting the realtime hooks on several surfaces never opens N sockets. It only
 * carries lightweight signals; consumers refetch through TanStack Query, so
 * masking/RBAC is never bypassed. Polling stays as the resilient fallback — this
 * is an accelerator, not a replacement.
 */
class MessagingSocket {
  private ws: WebSocket | null = null;
  private refCount = 0;
  private connected = false;
  private attempts = 0;
  private reconnectTimer: number | null = null;
  private stopped = true;
  private readonly listeners = new Set<EventListener>();
  private readonly statusListeners = new Set<StatusListener>();

  acquire(): () => void {
    this.refCount += 1;
    if (this.refCount === 1) {
      this.stopped = false;
      this.open();
    }
    return () => this.release();
  }

  private release(): void {
    this.refCount = Math.max(0, this.refCount - 1);
    if (this.refCount === 0) this.shutdown();
  }

  subscribe(listener: EventListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  onStatus(listener: StatusListener): () => void {
    this.statusListeners.add(listener);
    listener(this.connected);
    return () => this.statusListeners.delete(listener);
  }

  isConnected(): boolean {
    return this.connected;
  }

  sendTyping(threadId: string): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      try {
        this.ws.send(JSON.stringify({ type: "typing", thread_id: threadId }));
      } catch {
        /* transient — ignore, the next keystroke retries */
      }
    }
  }

  private setConnected(next: boolean): void {
    if (this.connected === next) return;
    this.connected = next;
    for (const l of this.statusListeners) l(next);
  }

  private open(): void {
    if (typeof window === "undefined" || this.stopped) return;
    if (this.ws) return;
    const token = getAccessToken();
    if (!token) {
      // No in-memory token yet (hydrating / refreshing) — retry shortly.
      this.scheduleReconnect();
      return;
    }
    let ws: WebSocket;
    try {
      // Token is NOT put in the URL (query strings leak into logs/history). It is
      // sent as the first frame after open — the server subscribes nothing until
      // that auth handshake validates.
      ws = new WebSocket(apiWsUrl("/messaging/ws"));
    } catch {
      this.scheduleReconnect();
      return;
    }
    this.ws = ws;
    ws.onopen = () => {
      this.attempts = 0;
      this.setConnected(true);
      try {
        ws.send(JSON.stringify({ type: "auth", token }));
      } catch {
        // If the first send fails the socket is already gone; reconnect logic handles it.
      }
    };
    ws.onmessage = (e) => {
      let data: unknown;
      try {
        data = JSON.parse(typeof e.data === "string" ? e.data : "");
      } catch {
        return;
      }
      if (!data || typeof data !== "object") return;
      const evt = data as MessagingSocketEvent;
      if (evt.type === "ready") return;
      for (const l of this.listeners) l(evt);
    };
    ws.onerror = () => {
      /* onclose will follow and drive reconnect */
    };
    ws.onclose = () => {
      this.ws = null;
      this.setConnected(false);
      if (!this.stopped && this.refCount > 0) this.scheduleReconnect();
    };
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer !== null || this.stopped || this.refCount === 0) return;
    const delay =
      Math.min(MAX_BACKOFF_MS, 1000 * 2 ** this.attempts) + Math.random() * 400;
    this.attempts = Math.min(this.attempts + 1, 6);
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.open();
    }, delay);
  }

  private shutdown(): void {
    this.stopped = true;
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      try {
        this.ws.close();
      } catch {
        /* ignore */
      }
      this.ws = null;
    }
    this.attempts = 0;
    this.setConnected(false);
  }
}

const socket = new MessagingSocket();

/**
 * App-level realtime: keep ONE socket alive while authenticated and translate its
 * signals into targeted TanStack Query invalidations (messages, thread detail,
 * lists, org inbox, unread badge). Mount on messaging surfaces; ref-counting keeps
 * a single connection. Returns `connected` for optional UI.
 */
export function useMessagingRealtime(): { connected: boolean } {
  const qc = useQueryClient();
  const authed = useAuthStore((s) => s.status === "authenticated");
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!authed) return;
    const release = socket.acquire();
    const offStatus = socket.onStatus(setConnected);
    const off = socket.subscribe((evt) => {
      const id = evt.thread_id;
      const invalidate = (key: readonly unknown[]) =>
        void qc.invalidateQueries({ queryKey: key });
      switch (evt.type) {
        case "message.created":
          if (id) invalidate(messagingThreadKey(id));
          invalidate(MESSAGING_THREADS_KEY);
          invalidate(MESSAGING_INBOX_ROOT);
          invalidate(MESSAGING_UNREAD_KEY);
          break;
        case "thread.created":
          invalidate(MESSAGING_THREADS_KEY);
          invalidate(MESSAGING_INBOX_ROOT);
          invalidate(MESSAGING_UNREAD_KEY);
          break;
        case "thread.request":
        case "thread.updated":
          if (id) {
            invalidate(messagingThreadKey(id));
            invalidate(messagingThreadDetailKey(id));
          }
          invalidate(MESSAGING_THREADS_KEY);
          invalidate(MESSAGING_INBOX_ROOT);
          invalidate(MESSAGING_UNREAD_KEY);
          break;
        default:
          break;
      }
    });
    return () => {
      off();
      offStatus();
      release();
    };
  }, [authed, qc]);

  return { connected };
}

/**
 * Per-thread typing: surface a transient "typing…" indicator for the OPEN thread
 * (auto-clears after ~4s or when a new message lands) and expose a throttled
 * `sendTyping` for the composer. Also keeps the shared socket alive while the
 * thread is open (ref-counted with the app-level connection).
 */
export function useThreadTyping(
  threadId: string | null,
  enabled: boolean,
): { typing: boolean; connected: boolean; sendTyping: () => void } {
  const [typing, setTyping] = useState(false);
  const [connected, setConnected] = useState(() => socket.isConnected());
  const clearTimer = useRef<number | null>(null);
  const lastSent = useRef(0);

  useEffect(() => {
    if (!enabled || !threadId) return;
    const release = socket.acquire();
    const offStatus = socket.onStatus(setConnected);
    const off = socket.subscribe((evt) => {
      if (evt.thread_id !== threadId) return;
      if (evt.type === "typing") {
        setTyping(true);
        if (clearTimer.current) window.clearTimeout(clearTimer.current);
        clearTimer.current = window.setTimeout(() => setTyping(false), 4000);
      } else if (evt.type === "message.created") {
        setTyping(false);
        if (clearTimer.current) window.clearTimeout(clearTimer.current);
      }
    });
    return () => {
      off();
      offStatus();
      release();
      if (clearTimer.current) window.clearTimeout(clearTimer.current);
      setTyping(false);
    };
  }, [threadId, enabled]);

  const sendTyping = useCallback(() => {
    if (!threadId) return;
    const now = Date.now();
    if (now - lastSent.current < 2000) return; // throttle ~1 / 2s
    lastSent.current = now;
    socket.sendTyping(threadId);
  }, [threadId]);

  return { typing, connected, sendTyping };
}
