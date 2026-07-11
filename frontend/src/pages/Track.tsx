import { useQuery, useQueryClient } from "@tanstack/react-query";
import L from "leaflet";
import { useCallback, useMemo, useState } from "react";
import { MapContainer, Marker, TileLayer } from "react-leaflet";
import { Link, useParams } from "react-router-dom";

import type { Errand, ErrandEvent, ErrandStatus } from "../api/errands";
import Navbar from "../components/Navbar";
import { api } from "../lib/api";
import { useSocket } from "../lib/ws";

import "leaflet/dist/leaflet.css";

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

async function fetchErrand(id: string): Promise<Errand> {
  return (await api.get<Errand>(`/errands/${id}`)).data;
}

async function fetchEvents(id: string): Promise<ErrandEvent[]> {
  return (await api.get<ErrandEvent[]>(`/errands/${id}/events`)).data;
}

function timeLabel(iso: string) {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
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

  const cancelled = errand.status === "CANCELLED" || errand.status === "EXPIRED";
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

        {/* Live map */}
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

        {/* Status stepper */}
        <div className="mt-8 rounded-2xl border border-line p-6">
          {cancelled ? (
            <div className="text-center">
              <div className="text-4xl">🚫</div>
              <p className="mt-2 font-bold">This errand was cancelled</p>
            </div>
          ) : (
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
          )}
        </div>
      </div>
    </div>
  );
}
