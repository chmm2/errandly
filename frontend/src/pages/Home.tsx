import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { fetchMe } from "../api/auth";
import {
  cancelErrand,
  completeErrand,
  type Errand,
  type ErrandStatus,
  fetchMyErrands,
  rateErrand,
} from "../api/errands";
import Navbar from "../components/Navbar";
import { useSocket } from "../lib/ws";
import { useAuth } from "../stores/auth";

const STATUS_STYLES: Record<ErrandStatus, { label: string; cls: string }> = {
  OPEN: { label: "Waiting for a runner", cls: "bg-blue-50 text-blue-700" },
  ACCEPTED: { label: "Runner assigned", cls: "bg-amber-50 text-amber-700" },
  IN_PROGRESS: { label: "On the way", cls: "bg-brand-soft text-brand-dark" },
  DELIVERED: { label: "Delivered — confirm it", cls: "bg-purple-50 text-purple-700" },
  COMPLETED: { label: "Completed", cls: "bg-green-50 text-green-700" },
  CANCELLED: { label: "Cancelled", cls: "bg-gray-100 text-muted" },
  EXPIRED: { label: "Expired", cls: "bg-gray-100 text-muted" },
};

const CATEGORY_ICONS: Record<string, string> = {
  FOOD: "🍔",
  GROCERY: "🛒",
  PARCEL: "📦",
  STATIONERY: "📚",
  PHARMACY: "💊",
  CUSTOM: "✨",
};

// Four ways to start an errand. Grocery/stationery/pharmacy all share the
// same "shopping list" flow; food browses the canteens; parcel & main gate
// are verified pickups.
const CATEGORIES = [
  {
    icon: "🛒",
    name: "Shopping list",
    desc: "Groceries, stationery, medicines — list what you need",
    to: "/errands/new",
    state: { mode: "shopping" },
  },
  {
    icon: "🍔",
    name: "Food",
    desc: "Canteens, food court, night mess",
    to: "/shops",
    state: { category: "FOOD" },
  },
  {
    icon: "📦",
    name: "Parcel pickup",
    desc: "Amazon / Flipkart collection point",
    to: "/errands/new",
    state: { category: "Parcel pickup" },
  },
  {
    icon: "🛺",
    name: "Main gate",
    desc: "Collect a delivery waiting at the gate",
    to: "/errands/new",
    state: { category: "Main gate" },
  },
];

const LIVE_STATUSES: ErrandStatus[] = ["OPEN", "ACCEPTED", "IN_PROGRESS", "DELIVERED"];

// Rough end-to-end estimate once a runner is on it — enough to set the
// requester's expectation ("~12 min") without a full routing model.
const ETA_MINUTES = 15;

function useNow(intervalMs = 20_000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(t);
  }, [intervalMs]);
  return now;
}

function minsAgo(from: number, now: number) {
  return Math.max(0, Math.round((now - from) / 60_000));
}

/** Live "how long" line for an active errand so the requester always knows
 * where things stand — time since posting, or an ETA once accepted. */
function EtaBadge({ errand }: { errand: Errand }) {
  const now = useNow();
  if (errand.status === "OPEN") {
    const m = minsAgo(new Date(errand.created_at).getTime(), now);
    return (
      <span className="inline-flex items-center gap-1 text-xs font-semibold text-amber-600">
        ⏳ Finding a runner · posted {m === 0 ? "just now" : `${m} min ago`}
      </span>
    );
  }
  if (errand.status === "ACCEPTED" || errand.status === "IN_PROGRESS") {
    const base = errand.accepted_at ? new Date(errand.accepted_at).getTime() : now;
    const remaining = Math.round((base + ETA_MINUTES * 60_000 - now) / 60_000);
    return (
      <span className="inline-flex items-center gap-1 text-xs font-semibold text-brand-dark">
        ⏱️ {remaining > 1 ? `ETA ~${remaining} min` : "Arriving any moment"}
      </span>
    );
  }
  if (errand.status === "DELIVERED") {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-semibold text-purple-600">
        ✅ Handed over — confirm to close
      </span>
    );
  }
  return null;
}

function RatingModal({ errandId, onDone }: { errandId: string; onDone: () => void }) {
  const [stars, setStars] = useState(0);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    try {
      await rateErrand(errandId, stars);
    } finally {
      onDone();
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-sm rounded-3xl bg-white p-6 text-center shadow-2xl">
        <div className="text-4xl">🎉</div>
        <h3 className="mt-2 text-xl font-extrabold">Delivered! Rate your runner</h3>
        <div className="mt-4 flex justify-center gap-1 text-4xl">
          {[1, 2, 3, 4, 5].map((n) => (
            <button key={n} onClick={() => setStars(n)} aria-label={`${n} stars`}>
              {n <= stars ? "★" : "☆"}
            </button>
          ))}
        </div>
        <div className="mt-5 flex gap-3">
          <button
            onClick={onDone}
            className="flex-1 rounded-xl border border-line py-2.5 font-semibold text-muted"
          >
            Skip
          </button>
          <button
            onClick={submit}
            disabled={stars === 0 || busy}
            className="flex-1 rounded-xl bg-brand py-2.5 font-bold text-white transition hover:bg-brand-dark disabled:opacity-50"
          >
            Submit
          </button>
        </div>
      </div>
    </div>
  );
}

function ErrandCard({
  errand,
  onConfirmed,
}: {
  errand: Errand;
  onConfirmed: (errandId: string) => void;
}) {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["my-errands"] });
  const cancel = useMutation({
    mutationFn: () => cancelErrand(errand.id),
    onSettled: refresh,
  });
  const confirm = useMutation({
    mutationFn: () => completeErrand(errand.id),
    // Rating modal lives on the PAGE: confirming moves this card from the
    // active list to History, which unmounts it (and any state it held).
    onSuccess: () => onConfirmed(errand.id),
    onSettled: refresh,
  });
  const status = STATUS_STYLES[errand.status];
  const cancellable = errand.status === "OPEN" || errand.status === "ACCEPTED";

  // Live status: the backend publishes every transition to this errand's
  // channel; refetch the moment one arrives (polling stays as fallback).
  useSocket(
    LIVE_STATUSES.includes(errand.status) ? `/ws/errands/${errand.id}` : null,
    useCallback(
      () => queryClient.invalidateQueries({ queryKey: ["my-errands"] }),
      [queryClient],
    ),
  );

  return (
    <div className="flex items-center gap-4 rounded-2xl border border-line p-5 transition hover:shadow-md">
      <Link
        to={`/errands/${errand.id}`}
        className="flex min-w-0 flex-1 items-center gap-4"
      >
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-brand-soft text-2xl">
          {CATEGORY_ICONS[errand.category] ?? "✨"}
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate font-bold hover:text-brand">{errand.title}</div>
          <div className="mt-0.5 truncate text-sm text-muted">
            from {errand.pickup_label} · ₹{Number(errand.reward).toFixed(0)} reward · track →
          </div>
          <div className="mt-1">
            <EtaBadge errand={errand} />
          </div>
        </div>
      </Link>
      <span className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-bold ${status.cls}`}>
        {status.label}
      </span>
      {errand.status === "DELIVERED" && (
        <button
          onClick={() => confirm.mutate()}
          disabled={confirm.isPending}
          className="shrink-0 rounded-xl bg-emerald-600 px-4 py-2 text-sm font-bold text-white transition hover:bg-emerald-700 disabled:opacity-60"
        >
          Confirm ✓
        </button>
      )}
      {errand.status === "COMPLETED" && !errand.rated && (
        <button
          onClick={() => onConfirmed(errand.id)}
          className="shrink-0 rounded-xl border border-brand px-4 py-2 text-sm font-bold text-brand transition hover:bg-brand-soft"
        >
          Rate ★
        </button>
      )}
      {cancellable && (
        <button
          onClick={() => cancel.mutate()}
          disabled={cancel.isPending}
          className="shrink-0 text-sm font-semibold text-muted transition hover:text-red-600 disabled:opacity-50"
        >
          {cancel.isPending ? "Cancelling…" : "Cancel"}
        </button>
      )}
    </div>
  );
}

export default function Home() {
  const user = useAuth((s) => s.user);
  const setUser = useAuth((s) => s.setUser);
  const [ratingFor, setRatingFor] = useState<string | null>(null);

  const queryClient = useQueryClient();
  const { data: me } = useQuery({ queryKey: ["me"], queryFn: fetchMe });
  useEffect(() => {
    if (me) setUser(me);
  }, [me, setUser]);

  const { data: mine } = useQuery({
    queryKey: ["my-errands"],
    queryFn: fetchMyErrands,
    refetchInterval: 15_000, // poll until WebSocket tracking lands in Sprint 3
  });
  const active = (mine?.requested ?? []).filter(
    (e) => !["COMPLETED", "CANCELLED", "EXPIRED"].includes(e.status),
  );

  return (
    <div className="min-h-screen bg-white">
      <Navbar />

      {/* Hero */}
      <section className="bg-gradient-to-br from-brand to-brand-dark text-white">
        <div className="mx-auto max-w-6xl px-4 py-16">
          <h1 className="max-w-2xl text-4xl font-extrabold leading-tight sm:text-5xl">
            Hey {user?.display_name?.split(" ")[0] ?? "there"}, what do you need today?
          </h1>
          <p className="mt-3 max-w-xl text-lg text-white/90">
            A verified student runner is minutes away. Post an errand or pick one up on your way
            back to the hostel.
          </p>
          <div className="mt-8">
            <Link
              to="/errands/new"
              className="inline-block rounded-xl bg-white px-6 py-3.5 font-bold text-brand shadow-lg transition hover:-translate-y-0.5"
            >
              Post an errand →
            </Link>
          </div>
        </div>
      </section>

      {/* Active errands first — the moment something's in flight, it's the
          top thing you want to see. */}
      {active.length > 0 && (
        <section className="mx-auto max-w-6xl px-4 pt-10">
          <h2 className="text-2xl font-extrabold">Your active errands</h2>
          <div className="mt-6 space-y-3">
            {active.map((e) => (
              <ErrandCard key={e.id} errand={e} onConfirmed={setRatingFor} />
            ))}
          </div>
        </section>
      )}

      {/* Categories */}
      <section className="mx-auto max-w-6xl px-4 py-12">
        <h2 className="text-2xl font-extrabold">What can we get you?</h2>
        <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
          {CATEGORIES.map((c) => (
            <Link
              key={c.name}
              to={c.to}
              state={c.state}
              className="group rounded-2xl border border-line p-5 transition hover:-translate-y-1 hover:border-brand hover:shadow-lg"
            >
              <div className="text-4xl">{c.icon}</div>
              <div className="mt-3 font-bold group-hover:text-brand">{c.name}</div>
              <div className="mt-1 text-sm text-muted">{c.desc}</div>
            </Link>
          ))}
        </div>
        {active.length === 0 && (
          <p className="mt-6 text-sm text-muted">
            Nothing in flight right now — pick a category above to post your first errand. Past
            errands live in your{" "}
            <Link to="/profile" className="font-semibold text-brand hover:underline">
              profile
            </Link>
            .
          </p>
        )}
      </section>

      {ratingFor && (
        <RatingModal
          errandId={ratingFor}
          onDone={() => {
            setRatingFor(null);
            queryClient.invalidateQueries({ queryKey: ["my-errands"] });
          }}
        />
      )}

      <footer className="border-t border-line py-8 text-center text-sm text-muted">
        errandly · built by students, for students · VIT Vellore
      </footer>
    </div>
  );
}
