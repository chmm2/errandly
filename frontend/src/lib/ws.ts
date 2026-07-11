import { useEffect } from "react";

import { useAuth } from "../stores/auth";

/** Open an authenticated WebSocket through the Vite `/api` proxy.
 * Browsers can't set Authorization headers on sockets, so the access
 * token travels as a query parameter (matches the backend contract). */
export function openSocket(path: string): WebSocket | null {
  const token = useAuth.getState().accessToken;
  if (!token) return null;
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  const url = `${scheme}://${window.location.host}/api${path}?token=${encodeURIComponent(token)}`;
  return new WebSocket(url);
}

/** Subscribe to a socket for the lifetime of a component. Messages of
 * type "ping" (server heartbeat) are filtered out. Reconnects are left
 * to the caller re-mounting — polling remains the fallback. */
export function useSocket(
  path: string | null,
  onMessage: (data: Record<string, unknown>) => void,
) {
  useEffect(() => {
    if (!path) return;
    const socket = openSocket(path);
    if (!socket) return;
    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type !== "ping") onMessage(data);
      } catch {
        // non-JSON frame — ignore
      }
    };
    return () => socket.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path]);
}
