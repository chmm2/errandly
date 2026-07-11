import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import { fetchNotifications, markAllRead, type Notification } from "../api/notifications";
import { useSocket } from "../lib/ws";

const TYPE_ICONS: Record<string, string> = {
  ORDER_ACCEPTED: "🤝",
  ORDER_PICKED_UP: "📦",
  ORDER_DELIVERED: "🎉",
  ORDER_COMPLETED: "✅",
  ORDER_CANCELLED: "🚫",
  TIMETABLE_BLOCK: "📚",
};

function timeAgo(iso: string): string {
  const seconds = Math.max(1, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

export default function NotificationBell() {
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();
  const panelRef = useRef<HTMLDivElement>(null);

  const { data } = useQuery({
    queryKey: ["notifications"],
    queryFn: fetchNotifications,
    refetchInterval: 60_000,
  });
  const unread = data?.unread ?? 0;

  // Live: the Kafka notification consumer pushes through Redis → this socket.
  useSocket(
    "/ws/notifications",
    useCallback(
      () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
      [queryClient],
    ),
  );

  useEffect(() => {
    if (!open) return;
    function onClick(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  async function toggle() {
    const next = !open;
    setOpen(next);
    if (next && unread > 0) {
      await markAllRead();
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    }
  }

  return (
    <div className="relative" ref={panelRef}>
      <button
        onClick={toggle}
        aria-label="Notifications"
        className="relative flex h-9 w-9 items-center justify-center rounded-full text-xl transition hover:bg-brand-soft"
      >
        🔔
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-brand px-1 text-xs font-bold text-white">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-11 z-30 w-80 overflow-hidden rounded-2xl border border-line bg-white shadow-2xl">
          <div className="border-b border-line px-4 py-3 font-bold">Notifications</div>
          <div className="max-h-96 overflow-y-auto">
            {(data?.items ?? []).length === 0 ? (
              <div className="px-4 py-8 text-center text-sm text-muted">
                Nothing yet — order updates land here.
              </div>
            ) : (
              data!.items.map((n: Notification) => (
                <div
                  key={n.id}
                  className={`flex gap-3 border-b border-line px-4 py-3 last:border-0 ${
                    n.read_at ? "" : "bg-brand-soft/50"
                  }`}
                >
                  <span className="text-xl">{TYPE_ICONS[n.type] ?? "🔔"}</span>
                  <div className="min-w-0">
                    <div className="text-sm font-bold">{n.title}</div>
                    {n.body && <div className="truncate text-sm text-muted">{n.body}</div>}
                    <div className="mt-0.5 text-xs text-muted">{timeAgo(n.created_at)}</div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
