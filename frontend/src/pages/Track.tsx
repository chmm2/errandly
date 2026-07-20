import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import L from "leaflet";
import { useCallback, useEffect, useMemo, useState } from "react";
import { MapContainer, Marker, TileLayer, useMap } from "react-leaflet";
import { Link, useParams } from "react-router-dom";

import {
  cancelErrand,
  type Errand,
  type ErrandEvent,
  type ErrandStatus,
  type RunnerSummary,
  setItemAvailability,
} from "../api/errands";
import ChatPanel from "../components/ChatPanel";
import Navbar from "../components/Navbar";
import { api } from "../lib/api";
import { useSocket } from "../lib/ws";
import { useAuth } from "../stores/auth";

import "leaflet/dist/leaflet.css";

// Nobody accepted within this window → the server expires the errand. We
// mirror it here as a countdown (server stays the source of truth).
const FIND_WINDOW_MS = 10 * 60 * 1000;

// Emoji markers: no image-asset plumbing, and they read instantly.
const dropIcon = L.divIcon({
  className: "",
  html: '<div style="font-size:28px;line-height:1;filter:drop-shadow(0 2px 2px rgba(0,0,0,.35))">📍</div>',
  iconSize: [28, 28],
  iconAnchor: [14, 26],
});
const runnerIcon = L.divIcon({
  className: "",
  html: '<div style="font-size:30px;line-height:1;filter:drop-shadow(0 2px 3px rgba(0,0,0,.4))">🛵</div>',
  iconSize: [30, 30],
  iconAnchor: [15, 15],
});

const STEPS: { key: string; label: string; icon: string }[] = [
  { key: "CREATED", label: "Posted", icon: "📝" },
  { key: "ACCEPTED", label: "Runner assigned", icon: "🤝" },
  { key: "PICKED_UP", label: "Picked up", icon: "📦" },
  { key: "DELIVERED", label: "Delivered", icon: "🎉" },
  { key: "COMPLETED", label: "Confirmed", icon: "✅" },
];

const LIVE: ErrandStatus[] = ["OPEN", "ACCEPTED", "IN_PROGRESS", "DELIVERED"];

/** Gently pan the map to keep the moving runner in view. */
function FollowRunner({ position }: { position: [number, number] | null }) {
  const map = useMap();
  useEffect(() => {
    if (position && !map.getBounds().pad(-0.2).contains(position)) {
      map.panTo(position, { animate: true });
    }
  }, [position, map]);
  return null;
}

async function fetchErrand(id: string): Promise<Errand> {
  return (await api.get<Errand>(`/errands/${id}`)).data;
}

async function fetchEvents(id: string): Promise<ErrandEvent[]> {
  return (await api.get<ErrandEvent[]>(`/errands/${id}/events`)).data;
}

function timeLabel(iso: string) {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** Circular countdown that unwinds from full to empty over the poster's wait
 * window, with the time remaining in the middle. */
function CountdownRing({ createdAt, expiresAt }: { createdAt: string; expiresAt: string }) {
  const start = new Date(createdAt).getTime();
  const end = new Date(expiresAt).getTime();
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const total = Math.max(1, end - start);
  const remaining = Math.max(0, end - now);
  const fraction = Math.max(0, Math.min(1, remaining / total));
  const mm = Math.floor(remaining / 60000);
  const ss = Math.floor((remaining % 60000) / 1000);
  const outOfTime = remaining === 0;

  const size = 184;
  const stroke = 12;
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;

  return (
    <div className="relative mx-auto" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          strokeWidth={stroke}
          stroke="currentColor"
          className="text-brand-soft"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          strokeWidth={stroke}
          strokeLinecap="round"
          stroke="currentColor"
          className="text-brand transition-[stroke-dashoffset] duration-1000 ease-linear"
          style={{ strokeDasharray: circ, strokeDashoffset: circ * (1 - fraction) }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        {outOfTime ? (
          <span className="text-4xl">🛵</span>
        ) : (
          <>
            <span className="text-4xl font-extrabold tabular-nums text-brand-dark">
              {mm}:{String(ss).padStart(2, "0")}
            </span>
            <span className="mt-0.5 text-[10px] font-semibold uppercase tracking-widest text-muted">
              until it expires
            </span>
          </>
        )}
      </div>
    </div>
  );
}

/** Full-width "we're finding you a runner" state with the countdown ring. */
function FindingRunner({ createdAt, expiresAt }: { createdAt: string; expiresAt: string }) {
  const outOfTime = Date.now() >= new Date(expiresAt).getTime();
  return (
    <div className="mt-8 rounded-2xl border border-line bg-brand-soft/40 p-10 text-center">
      <CountdownRing createdAt={createdAt} expiresAt={expiresAt} />
      <h2 className="mt-6 text-2xl font-extrabold">
        {outOfTime ? "Still searching…" : "Finding a runner nearby"}
      </h2>
      <p className="mx-auto mt-2 max-w-md text-muted">
        {outOfTime
          ? "No one has accepted yet — one last widen of the search before it expires."
          : "We're offering your errand to verified students heading your way."}
      </p>
    </div>
  );
}

/** What was ordered — items or the shopping list, plus where it goes. The
 * runner's primary content (they don't get the map). When `canManage` is set,
 * the runner can mark items out of stock and, if nothing's left, cancel. */
function OrderDetails({ errand, canManage }: { errand: Errand; canManage: boolean }) {
  const queryClient = useQueryClient();
  const items = errand.items ?? [];

  const toggle = useMutation({
    mutationFn: (v: { itemId: string; available: boolean }) =>
      setItemAvailability(errand.id, v.itemId, v.available),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["errand", errand.id] });
      queryClient.invalidateQueries({ queryKey: ["errand-events", errand.id] });
    },
  });
  const cancel = useMutation({
    mutationFn: () => cancelErrand(errand.id, "None of the items were available in store"),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["errand", errand.id] });
      queryClient.invalidateQueries({ queryKey: ["my-errands"] });
    },
  });

  const allUnavailable = items.length > 0 && items.every((it) => !it.is_available);

  return (
    <div className="mt-6 rounded-2xl border border-line p-5">
      <div className="text-xs font-semibold uppercase tracking-wide text-muted">Order details</div>

      {items.length > 0 ? (
        <>
          <ul className="mt-3 space-y-2.5">
            {items.map((it) => (
              <li key={it.id} className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div
                    className={`text-sm font-semibold ${
                      it.is_available ? "" : "text-muted line-through"
                    }`}
                  >
                    {it.quantity}× {it.name_snapshot}
                  </div>
                  {it.note && <div className="text-xs text-muted">{it.note}</div>}
                  {!it.is_available && (
                    <div className="text-xs font-bold text-red-500">out of stock</div>
                  )}
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  {it.unit_price_snapshot != null && (
                    <span
                      className={`text-sm text-muted ${it.is_available ? "" : "line-through"}`}
                    >
                      ₹{(it.unit_price_snapshot * it.quantity).toFixed(0)}
                    </span>
                  )}
                  {canManage && (
                    <button
                      onClick={() =>
                        toggle.mutate({ itemId: it.id, available: !it.is_available })
                      }
                      disabled={toggle.isPending}
                      className={`rounded-lg border px-2.5 py-1 text-xs font-bold transition disabled:opacity-50 ${
                        it.is_available
                          ? "border-line text-muted hover:border-red-400 hover:text-red-600"
                          : "border-brand text-brand hover:bg-brand-soft"
                      }`}
                    >
                      {it.is_available ? "Out of stock" : "Restore"}
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
          {errand.items_total > 0 && (
            <div className="mt-3 flex items-center justify-between border-t border-line pt-2 text-sm font-bold">
              <span>Items total</span>
              <span>₹{Number(errand.items_total).toFixed(0)}</span>
            </div>
          )}
        </>
      ) : errand.notes ? (
        <p className="mt-3 whitespace-pre-wrap text-sm text-ink">{errand.notes}</p>
      ) : (
        <p className="mt-3 text-sm text-muted">{errand.title}</p>
      )}

      {canManage && allUnavailable && (
        <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3">
          <p className="text-sm font-semibold text-red-700">
            Nothing on this list is available.
          </p>
          <button
            onClick={() => cancel.mutate()}
            disabled={cancel.isPending}
            className="mt-2 w-full rounded-lg bg-red-600 py-2 text-sm font-bold text-white transition hover:bg-red-700 disabled:opacity-60"
          >
            {cancel.isPending ? "Cancelling…" : "Cancel run — nothing available"}
          </button>
        </div>
      )}

      <div className="mt-4 space-y-1.5 border-t border-line pt-3 text-sm text-muted">
        <div>
          🏪 From <span className="font-semibold text-ink">{errand.pickup_label}</span>
        </div>
        <div>
          📍 Deliver to{" "}
          <span className="font-semibold text-ink">{errand.drop_label || "pinned location"}</span>
        </div>
        {errand.collect_amount > 0 && (
          <div>
            💵 Pay at pickup{" "}
            <span className="font-semibold text-brand-dark">
              ₹{Number(errand.collect_amount).toFixed(0)}
            </span>{" "}
            (reimbursed)
          </div>
        )}
      </div>
    </div>
  );
}

/** The escrow panel — the trust centerpiece. Shows the customer's money is
 * secured before the runner shops, and how it settles. Shown to both parties. */
function EscrowPanel({
  errand,
  isRunner,
}: {
  errand: Errand;
  isRunner: boolean;
}) {
  const escrow = errand.escrow;
  if (!escrow) return null;

  if (escrow.status === "REFUNDED") {
    return (
      <div className="mt-6 rounded-2xl border border-line bg-gray-50 p-5">
        <div className="flex items-center gap-2 font-bold">
          <span>💸</span> Refunded
        </div>
        <p className="mt-1 text-sm text-muted">
          ₹{escrow.total.toFixed(0)} was returned to the customer's wallet. Nothing was charged.
        </p>
      </div>
    );
  }

  const released = escrow.status === "RELEASED";
  return (
    <div
      className={`mt-6 rounded-2xl border p-5 ${
        released ? "border-green-200 bg-green-50" : "border-brand/30 bg-brand-soft/40"
      }`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 font-bold">
          <span>{released ? "✅" : "🔒"}</span>
          {released ? "Payment released" : "Secured in escrow"}
        </div>
        <span className="text-lg font-extrabold text-brand-dark">₹{escrow.total.toFixed(0)}</span>
      </div>

      <dl className="mt-3 space-y-1.5 border-t border-line/70 pt-3 text-sm text-muted">
        {escrow.item_total > 0 && (
          <div className="flex justify-between">
            <dt>Item cost</dt>
            <dd>₹{escrow.item_total.toFixed(0)}</dd>
          </div>
        )}
        <div className="flex justify-between">
          <dt>Runner fee</dt>
          <dd>₹{escrow.runner_fee.toFixed(0)}</dd>
        </div>
        <div className="flex justify-between">
          <dt>Convenience</dt>
          <dd>₹{escrow.convenience_fee.toFixed(0)}</dd>
        </div>
      </dl>

      <p className="mt-3 text-sm font-medium text-ink">
        {released
          ? isRunner
            ? "You've been paid your fee and reimbursed for what you spent. 🎉"
            : "The runner has been paid and any unspent budget refunded to your wallet."
          : isRunner
            ? "The customer's money is already secured — you'll be paid your fee and reimbursed the moment delivery is confirmed. No risk to you."
            : "This amount left your wallet and is held safely. It's released to the runner only after you confirm delivery."}
      </p>
    </div>
  );
}

/** Apology shown when the errand expired with no runner. */
function ExpiredCard() {
  return (
    <div className="mt-8 rounded-2xl border border-line p-10 text-center">
      <div className="text-5xl">😔</div>
      <h2 className="mt-4 text-2xl font-extrabold">No runner was available</h2>
      <p className="mx-auto mt-2 max-w-md text-muted">
        We're sorry — nobody could pick this up right now, so we've closed the request.
        Any amount held for it has been refunded to your wallet. Try again in a bit, or
        offer a slightly higher reward to catch more attention.
      </p>
      <div className="mt-6 flex justify-center gap-3">
        <Link
          to="/shops"
          className="rounded-xl border border-line px-5 py-2.5 font-semibold text-muted transition hover:border-brand hover:text-brand"
        >
          Browse stores
        </Link>
        <Link
          to="/errands/new"
          className="rounded-xl bg-brand px-6 py-2.5 font-bold text-white transition hover:bg-brand-dark"
        >
          Post again
        </Link>
      </div>
    </div>
  );
}

/** Runner profile card, Swiggy-style: photo, name, rating, delivery count,
 * and a tap-to-call button. */
function RunnerCard({ runner }: { runner: RunnerSummary }) {
  const initial = runner.display_name.charAt(0).toUpperCase();
  return (
    <div className="mt-6 flex items-center gap-4 rounded-2xl border border-line p-5">
      {runner.photo_url ? (
        <img
          src={runner.photo_url}
          alt={runner.display_name}
          className="h-14 w-14 shrink-0 rounded-full object-cover"
        />
      ) : (
        <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-brand-soft text-xl font-extrabold text-brand">
          {initial}
        </div>
      )}
      <div className="min-w-0 flex-1">
        <div className="text-xs font-semibold uppercase tracking-wide text-muted">
          Your runner
        </div>
        <div className="truncate text-lg font-bold">{runner.display_name}</div>
        <div className="text-sm text-muted">
          ★ {Number(runner.reputation_score).toFixed(1)}
          {runner.rating_count > 0 && <span> · {runner.rating_count} ratings</span>}
          <span> · {runner.trips_completed} deliveries</span>
        </div>
      </div>
      {runner.phone ? (
        <a
          href={`tel:${runner.phone}`}
          className="flex shrink-0 items-center gap-2 rounded-xl bg-emerald-600 px-5 py-2.5 font-bold text-white transition hover:bg-emerald-700"
        >
          📞 Call
        </a>
      ) : (
        <span className="shrink-0 text-xs text-muted">no phone on file</span>
      )}
    </div>
  );
}

export default function Track() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const myId = useAuth((s) => s.user?.id);
  const [runnerPos, setRunnerPos] = useState<[number, number] | null>(null);

  const { data: errand } = useQuery({
    queryKey: ["errand", id],
    queryFn: () => fetchErrand(id!),
    enabled: !!id,
  });
  const { data: events } = useQuery({
    queryKey: ["errand-events", id],
    queryFn: () => fetchEvents(id!),
    enabled: !!id,
    refetchInterval: 30_000,
  });

  // One socket: status transitions AND runner location share the channel.
  useSocket(
    errand && LIVE.includes(errand.status) ? `/ws/errands/${id}` : null,
    useCallback(
      (data: Record<string, unknown>) => {
        if (data.type === "location") {
          setRunnerPos([data.lat as number, data.lng as number]);
        } else {
          queryClient.invalidateQueries({ queryKey: ["errand", id] });
          queryClient.invalidateQueries({ queryKey: ["errand-events", id] });
          queryClient.invalidateQueries({ queryKey: ["my-errands"] });
        }
      },
      [queryClient, id],
    ),
  );

  const doneEvents = useMemo(() => {
    const map = new Map<string, string>();
    (events ?? []).forEach((e) => {
      if (!map.has(e.event_type)) map.set(e.event_type, e.created_at);
    });
    return map;
  }, [events]);

  if (!errand) {
    return (
      <div className="min-h-screen bg-white">
        <Navbar />
        <div className="mx-auto max-w-3xl px-4 py-20 text-center text-muted">Loading order…</div>
      </div>
    );
  }

  const isRunner = !!myId && errand.runner_id === myId;
  const finding = errand.status === "OPEN";
  const expired = errand.status === "EXPIRED";
  const cancelled = errand.status === "CANCELLED";
  const live = !finding && !expired && !cancelled;
  // The runner doesn't get the live map — watching their own dot is pointless.
  const showMap = live && !isRunner;
  const expiresAt =
    errand.expires_at ??
    new Date(new Date(errand.created_at).getTime() + FIND_WINDOW_MS).toISOString();
  const drop: [number, number] = [errand.drop_lat, errand.drop_lng];
  const runner =
    runnerPos ??
    (errand.runner_lat != null ? ([errand.runner_lat, errand.runner_lng!] as [number, number]) : null);
  const reachedIndex = STEPS.reduce(
    (acc, s, i) => (doneEvents.has(s.key) ? i : acc),
    -1,
  );
  const cancelReason = (
    (events ?? []).find((e) => e.event_type === "CANCELLED")?.payload as
      | { reason?: string }
      | null
      | undefined
  )?.reason;

  return (
    <div className="min-h-screen bg-white">
      <Navbar />
      <div className="mx-auto max-w-3xl px-4 py-8">
        <Link to="/" className="text-sm font-semibold text-muted hover:text-brand">
          ← Back to home
        </Link>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
          <h1 className="text-2xl font-extrabold sm:text-3xl">{errand.title}</h1>
          <span className="rounded-full bg-brand-soft px-3 py-1.5 text-sm font-bold text-brand-dark">
            ₹{Number(errand.reward).toFixed(0)} reward
          </span>
        </div>
        <p className="mt-1 text-muted">
          from {errand.pickup_label}
          {errand.drop_label ? ` → ${errand.drop_label}` : ""}
        </p>

        <EscrowPanel errand={errand} isRunner={isRunner} />

        {finding && !isRunner && (
          <FindingRunner createdAt={errand.created_at} expiresAt={expiresAt} />
        )}
        {expired && <ExpiredCard />}

        {/* Runner profile card (name, rating, call) — hidden when the viewer
            IS the runner (no "your runner" card for yourself) */}
        {errand.runner && errand.runner.id !== myId && !expired && !cancelled && (
          <RunnerCard runner={errand.runner} />
        )}

        {/* Order details — shown from the moment it's posted (under the ring
            while finding), and the runner's primary content later (no map) */}
        {!expired && !cancelled && (
          <OrderDetails
            errand={errand}
            canManage={
              isRunner &&
              (errand.status === "ACCEPTED" || errand.status === "IN_PROGRESS")
            }
          />
        )}

        {/* Chat opens once a runner is assigned, for both parties */}
        {errand.runner_id && !expired && !cancelled && <ChatPanel errandId={errand.id} />}

        {/* Live map */}
        {showMap && (
          <div className="mt-6 overflow-hidden rounded-2xl border border-line shadow-sm">
            <MapContainer
              center={runner ?? drop}
              zoom={16}
              style={{ height: 340, width: "100%" }}
              scrollWheelZoom={false}
            >
              <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />
              <Marker position={drop} icon={dropIcon} />
              {runner && <Marker position={runner} icon={runnerIcon} />}
              <FollowRunner position={runner} />
            </MapContainer>
            <div className="flex items-center justify-between bg-white px-4 py-2.5 text-xs text-muted">
              <span>📍 drop point{runner ? " · 🛵 your runner (live)" : ""}</span>
              {LIVE.includes(errand.status) && (
                <span className="flex items-center gap-1.5 font-semibold text-emerald-600">
                  <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-500" />
                  live
                </span>
              )}
            </div>
          </div>
        )}

        {/* Status stepper — shown to both parties (it's progress, not location) */}
        {live && (
          <div className="mt-8 rounded-2xl border border-line p-6">
            <ol className="space-y-0">
              {STEPS.map((step, i) => {
                const at = doneEvents.get(step.key);
                const done = !!at;
                const current = i === reachedIndex + 1;
                return (
                  <li key={step.key} className="flex gap-4">
                    <div className="flex flex-col items-center">
                      <div
                        className={`flex h-10 w-10 items-center justify-center rounded-full text-lg ${
                          done
                            ? "bg-brand text-white"
                            : current
                              ? "border-2 border-brand bg-brand-soft"
                              : "border-2 border-line bg-white opacity-50"
                        }`}
                      >
                        {done ? step.icon : current ? "⏳" : step.icon}
                      </div>
                      {i < STEPS.length - 1 && (
                        <div className={`h-8 w-0.5 ${done ? "bg-brand" : "bg-line"}`} />
                      )}
                    </div>
                    <div className="pb-2 pt-2">
                      <div className={`font-bold ${done ? "" : current ? "text-brand-dark" : "text-muted"}`}>
                        {step.label}
                      </div>
                      {at && <div className="text-xs text-muted">{timeLabel(at)}</div>}
                      {current && !done && (
                        <div className="text-xs font-semibold text-brand">happening next…</div>
                      )}
                    </div>
                  </li>
                );
              })}
            </ol>
          </div>
        )}

        {cancelled && (
          <div className="mt-8 rounded-2xl border border-line p-10 text-center">
            <div className="text-4xl">🚫</div>
            <p className="mt-2 font-bold">This errand was cancelled</p>
            {cancelReason && (
              <p className="mx-auto mt-1 max-w-sm text-sm text-muted">{cancelReason}</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
