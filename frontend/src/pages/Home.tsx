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

const CATEGORIES = [
  { icon: "🍔", name: "Food run", desc: "Canteen, food court, night mess" },
  { icon: "🛒", name: "Groceries", desc: "Campus store & beyond the gate" },
  { icon: "📦", name: "Parcel pickup", desc: "Amazon / Flipkart collection point" },
  { icon: "📚", name: "Stationery", desc: "Prints, records, lab supplies" },
  { icon: "💊", name: "Pharmacy", desc: "Health centre & medical store" },
  { icon: "✨", name: "Custom errand", desc: "Anything else — name your task" },
];

const STEPS = [
  { n: "1", title: "Post your errand", desc: "What you need, where it goes, what you'll pay." },
  {
    n: "2",
    title: "We match a runner",
    desc: "Live geo-matching finds a verified student already heading your way.",
  },
  {
    n: "3",
    title: "Track to your door",
    desc: "Follow the run in real time and rate your runner after handoff.",
  },
];

const LIVE_STATUSES: ErrandStatus[] = ["OPEN", "ACCEPTED", "IN_PROGRESS", "DELIVERED"];

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
  const past = (mine?.requested ?? []).filter((e) =>
    ["COMPLETED", "CANCELLED", "EXPIRED"].includes(e.status),
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
          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              to="/errands/new"
              className="rounded-xl bg-white px-6 py-3.5 font-bold text-brand shadow-lg transition hover:-translate-y-0.5"
            >
              Post an errand →
            </Link>
            <button
              disabled
              title="Runner mode ships in Sprint 3 — with timetable-aware availability"
              className="cursor-not-allowed rounded-xl border-2 border-white/60 px-6 py-3.5 font-bold text-white/80"
            >
              Become a runner · soon
            </button>
          </div>
        </div>
      </section>

      {/* Categories */}
      <section className="mx-auto max-w-6xl px-4 py-12">
        <h2 className="text-2xl font-extrabold">What can we get you?</h2>
        <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-3">
          {CATEGORIES.map((c) => (
            <Link
              key={c.name}
              to={
                ["Parcel pickup", "Custom errand"].includes(c.name) ? "/errands/new" : "/shops"
              }
              state={{ category: c.name }}
              className="group rounded-2xl border border-line p-5 transition hover:-translate-y-1 hover:border-brand hover:shadow-lg"
            >
              <div className="text-4xl">{c.icon}</div>
              <div className="mt-3 font-bold group-hover:text-brand">{c.name}</div>
              <div className="mt-1 text-sm text-muted">{c.desc}</div>
            </Link>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section className="bg-brand-soft">
        <div className="mx-auto max-w-6xl px-4 py-12">
          <h2 className="text-2xl font-extrabold">How Errandly works</h2>
          <div className="mt-6 grid gap-6 sm:grid-cols-3">
            {STEPS.map((s) => (
              <div key={s.n} className="rounded-2xl bg-white p-6 shadow-sm">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-brand font-extrabold text-white">
                  {s.n}
                </div>
                <div className="mt-4 font-bold">{s.title}</div>
                <div className="mt-1 text-sm text-muted">{s.desc}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Active errands — live from the order service */}
      <section className="mx-auto max-w-6xl px-4 py-12">
        <h2 className="text-2xl font-extrabold">Your active errands</h2>
        {active.length === 0 ? (
          <div className="mt-6 rounded-2xl border-2 border-dashed border-line p-12 text-center">
            <div className="text-5xl">🌤️</div>
            <p className="mt-4 font-semibold">Nothing in flight</p>
            <p className="mt-1 text-sm text-muted">
              Post your first errand and it will show up here with live status.
            </p>
          </div>
        ) : (
          <div className="mt-6 space-y-3">
            {active.map((e) => (
              <ErrandCard key={e.id} errand={e} onConfirmed={setRatingFor} />
            ))}
          </div>
        )}

        {past.length > 0 && (
          <>
            <h2 className="mt-12 text-2xl font-extrabold">History</h2>
            <div className="mt-6 space-y-3">
              {past.map((e) => (
                <ErrandCard key={e.id} errand={e} onConfirmed={setRatingFor} />
              ))}
            </div>
          </>
        )}
      </section>

      {ratingFor && (
        <RatingModal errandId={ratingFor} onDone={() => setRatingFor(null)} />
      )}

      <footer className="border-t border-line py-8 text-center text-sm text-muted">
        errandly · built by students, for students · VIT Vellore
      </footer>
    </div>
  );
}
