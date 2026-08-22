import { useEffect, useRef } from "react";
import { AppState } from "react-native";

import { useAuth } from "../stores/auth";
import { wsBase } from "./config";

/**
 * Authenticated socket to the backend.
 *
 * Browsers can't set Authorization headers on sockets, so the backend reads the
 * access token from a query parameter — same contract here.
 */
function openSocket(path: string): WebSocket | null {
  const token = useAuth.getState().accessToken;
  if (!token) return null;
  // Resolved per connection, so retyping the backend host takes effect on the
  // next reconnect rather than needing an app restart.
  return new WebSocket(`${wsBase()}${path}?token=${encodeURIComponent(token)}`);
}

/**
 * Subscribe to a backend channel for the lifetime of a screen.
 *
 * Differs from the web version in one important way: phones suspend sockets
 * when the app backgrounds, so this reconnects with backoff and also forces a
 * reconnect when the app returns to the foreground. Server "ping" heartbeats
 * are swallowed.
 *
 * Pass `path: null` to stay disconnected (e.g. runner is offline).
 */
export function useSocket(
  path: string | null,
  onMessage: (data: Record<string, unknown>) => void,
) {
  const handlerRef = useRef(onMessage);
  handlerRef.current = onMessage;

  useEffect(() => {
    if (!path) return;

    let socket: WebSocket | null = null;
    let retry = 0;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let closed = false;

    const connect = () => {
      if (closed) return;
      socket = openSocket(path);
      if (!socket) return;

      socket.onopen = () => {
        retry = 0;
      };

      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data as string);
          if (data?.type !== "ping") handlerRef.current(data);
        } catch {
          // non-JSON frame — ignore
        }
      };

      socket.onerror = () => {
        // `onclose` always follows; let it own the retry so we don't double-schedule.
      };

      socket.onclose = () => {
        if (closed) return;
        // Exponential backoff, capped — a dropped socket on a flaky campus
        // network shouldn't turn into a reconnect storm.
        const delay = Math.min(1000 * 2 ** retry, 15000);
        retry += 1;
        retryTimer = setTimeout(connect, delay);
      };
    };

    connect();

    // Coming back from background: the old socket is usually dead but hasn't
    // fired onclose yet. Force the cycle so updates resume immediately.
    const sub = AppState.addEventListener("change", (state) => {
      if (state === "active" && socket && socket.readyState !== WebSocket.OPEN) {
        socket.close();
      }
    });

    return () => {
      closed = true;
      sub.remove();
      if (retryTimer) clearTimeout(retryTimer);
      socket?.close();
    };
  }, [path]);
}
