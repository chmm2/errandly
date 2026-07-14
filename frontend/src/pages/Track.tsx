import { useQuery, useQueryClient } from "@tanstack/react-query";
import L from "leaflet";
import { useCallback, useEffect, useMemo, useState } from "react";
import { MapContainer, Marker, TileLayer, useMap } from "react-leaflet";
import { Link, useParams } from "react-router-dom";

import type { Errand, ErrandEvent, ErrandStatus, RunnerSummary } from "../api/errands";
import Navbar from "../components/Navbar";
import { api } from "../lib/api";
import { useSocket } from "../lib/ws";

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

/** Full-width "we're finding you a runner" state with a live countdown. */
function FindingRunner({ createdAt }: { createdAt: string }) {
  const deadline = new Date(createdAt).getTime() + FIND_WINDOW_MS;
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const remaining = Math.max(0, deadline - now);
  const mm = Math.floor(remaining / 60000);
  const ss = Math.floor((remaining % 60000) / 1000);
  const outOfTime = remaining === 0;

  return (
    <div className="mt-8 rounded-2xl border border-line bg-brand-soft/40 p-10 text-center">
      <div className="relative mx-auto h-24 w-24">
        <span className="absolute inset-0 animate-ping rounded-full bg-brand/20" />
        <span className="absolute inset-2 animate-pulse rounded-full bg-brand/20" />
        <span className="absolute inset-0 flex items-center justify-center text-5xl">🛵</span>
      </div>
      <h2 className="mt-6 text-2xl font-extrabold">
        {outOfTime ? "Still searching…" : "Finding a runner nearby"}
      </h2>
      <p className="mx-auto mt-2 max-w-md text-muted">
        {outOfTime
          ? "No one has accepted yet. Hang on — we're widening the search one last time."
          : "We're offering your errand to verified students heading your way."}
      </p>
      {!outOfTime && (
        <div className="mt-6">
          <div className="text-5xl font-extrabold tabular-nums text-brand-dark">
            {mm}:{String(ss).padStart(2, "0")}
          </div>
          <div className="mt-1 text-xs font-semibold uppercase tracking-wide text-muted">
            we'll keep trying for 10 minutes
          </div>
        </div>
      )}
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
        Nothing was charged. Try again in a bit, or offer a slightly higher reward to
        catch more attention.
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

  const finding = errand.status === "OPEN";
  const expired = errand.status === "EXPIRED";
  const cancelled = errand.status === "CANCELLED";
  const showMap = !finding && !expired && !cancelled;
  const drop: [number, number] = [errand.drop_lat, errand.drop_lng];
  const runner =
    runnerPos ??
    (errand.runner_lat != null ? ([errand.runner_lat, errand.runner_lng!] as [number, number]) : null);
  const reachedIndex = STEPS.reduce(
    (acc, s, i) => (doneEvents.has(s.key) ? i : acc),
    -1,
  );

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

        {finding && <FindingRunner createdAt={errand.created_at} />}
        {expired && <ExpiredCard />}

        {/* Runner profile card (name, rating, call) */}
        {errand.runner && !expired && !cancelled && <RunnerCard runner={errand.runner} />}

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

        {/* Status stepper */}
        {showMap && (
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
          </div>
        )}
      </div>
    </div>
  );
}
