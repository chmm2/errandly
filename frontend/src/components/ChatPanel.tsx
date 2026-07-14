import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { type ChatMessage, fetchChat, sendChat } from "../api/chat";
import { useSocket } from "../lib/ws";
import { useAuth } from "../stores/auth";

function timeLabel(iso: string) {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** In-app chat between the requester and their runner for one errand.
 * History from Mongo; live messages over the errand's WebSocket. */
export default function ChatPanel({ errandId }: { errandId: string }) {
  const myId = useAuth((s) => s.user?.id);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchChat(errandId).then(setMessages).catch(() => {});
  }, [errandId]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useSocket(
    `/ws/errands/${errandId}`,
    useCallback((data: Record<string, unknown>) => {
      if (data.type !== "chat") return;
      const msg = data as unknown as ChatMessage;
      // Dedupe: our own sent message also comes back over the socket.
      setMessages((prev) => (prev.some((m) => m.id === msg.id) ? prev : [...prev, msg]));
    }, []),
  );

  async function onSend(e: FormEvent) {
    e.preventDefault();
    const text = body.trim();
    if (!text) return;
    setBusy(true);
    try {
      const msg = await sendChat(errandId, text);
      setMessages((prev) => (prev.some((m) => m.id === msg.id) ? prev : [...prev, msg]));
      setBody("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-6 rounded-2xl border border-line">
      <div className="border-b border-line px-5 py-3 font-bold">💬 Chat</div>
      <div className="max-h-72 space-y-2 overflow-y-auto px-5 py-4">
        {messages.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted">
            No messages yet — say hi, share a landmark, or note a preference.
          </p>
        ) : (
          messages.map((m) => {
            const mine = m.sender_id === myId;
            return (
              <div key={m.id} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[80%] rounded-2xl px-3.5 py-2 text-sm ${
                    mine ? "bg-brand text-white" : "bg-brand-soft text-ink"
                  }`}
                >
                  {!mine && (
                    <div className="text-xs font-bold text-brand-dark">{m.sender_name}</div>
                  )}
                  <div>{m.body}</div>
                  <div className={`mt-0.5 text-[10px] ${mine ? "text-white/70" : "text-muted"}`}>
                    {timeLabel(m.created_at)}
                  </div>
                </div>
              </div>
            );
          })
        )}
        <div ref={endRef} />
      </div>
      <form onSubmit={onSend} className="flex gap-2 border-t border-line p-3">
        <input
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="Type a message…"
          maxLength={2000}
          className="flex-1 rounded-xl border border-line px-4 py-2.5 outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20"
        />
        <button
          type="submit"
          disabled={busy || !body.trim()}
          className="rounded-xl bg-brand px-5 py-2.5 font-bold text-white transition hover:bg-brand-dark disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </div>
  );
}
