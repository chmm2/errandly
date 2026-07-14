import { type FormEvent, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { type Category, createErrand } from "../api/errands";
import CampusDropPicker from "../components/CampusDropPicker";
import Navbar from "../components/Navbar";
import { apiErrorMessage } from "../lib/api";

const CATEGORY_MAP: Record<string, Category> = {
  "Food run": "FOOD",
  Groceries: "GROCERY",
  "Parcel pickup": "PARCEL",
  Stationery: "STATIONERY",
  Pharmacy: "PHARMACY",
  "Custom errand": "CUSTOM",
};

const CATEGORY_NAMES = Object.keys(CATEGORY_MAP);

type GeoState =
  | { status: "idle" }
  | { status: "locating" }
  | { status: "ok"; lat: number; lng: number; accuracy: number }
  | { status: "error"; message: string };

const inputCls =
  "w-full rounded-xl border border-line px-4 py-3 outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20";

// Saved drop points — you always deliver to the same 2-3 places on campus.
const SAVED_DROPS_KEY = "errandly-saved-drops";

interface SavedDrop {
  label: string;
  lat: number;
  lng: number;
}

function loadSavedDrops(): SavedDrop[] {
  try {
    return JSON.parse(localStorage.getItem(SAVED_DROPS_KEY) ?? "[]");
  } catch {
    return [];
  }
}

function saveDrop(drop: SavedDrop) {
  const drops = [drop, ...loadSavedDrops().filter((d) => d.label !== drop.label)].slice(0, 4);
  localStorage.setItem(SAVED_DROPS_KEY, JSON.stringify(drops));
}

export default function NewErrand() {
  const preset = (useLocation().state as { category?: string })?.category;
  const [category, setCategory] = useState(preset ?? "Food run");
  const [title, setTitle] = useState("");
  const [pickup, setPickup] = useState("");
  const [reward, setReward] = useState("30");
  const [notes, setNotes] = useState("");
  const [geo, setGeo] = useState<GeoState>({ status: "idle" });
  const [dropLabel, setDropLabel] = useState("");
  const [showMap, setShowMap] = useState(false);
  const [savedDrops] = useState<SavedDrop[]>(loadSavedDrops);
  const [externalRef, setExternalRef] = useState("");
  const [otp, setOtp] = useState("");
  const [collectAmount, setCollectAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);

  const isPickupMode = category === "Custom errand" || category === "Parcel pickup";

  function detectLocation() {
    if (!navigator.geolocation) {
      setGeo({ status: "error", message: "Geolocation is not supported by this browser." });
      return;
    }
    setGeo({ status: "locating" });
    navigator.geolocation.getCurrentPosition(
      (pos) =>
        setGeo({
          status: "ok",
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          accuracy: Math.round(pos.coords.accuracy),
        }),
      (err) => setGeo({ status: "error", message: err.message }),
      { enableHighAccuracy: true, timeout: 10_000 },
    );
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (geo.status !== "ok") return;
    setError(null);
    setBusy(true);
    try {
      await createErrand({
        category: CATEGORY_MAP[category] ?? "CUSTOM",
        title,
        notes: notes.trim() || undefined,
        pickup_label: pickup,
        drop_lat: geo.lat,
        drop_lng: geo.lng,
        drop_label: dropLabel.trim() || undefined,
        reward: Number(reward),
        external_ref: isPickupMode && externalRef.trim() ? externalRef.trim() : undefined,
        otp: isPickupMode && otp.trim() ? otp.trim() : undefined,
        collect_amount: isPickupMode && collectAmount ? Number(collectAmount) : undefined,
      });
      if (dropLabel.trim()) {
        saveDrop({ label: dropLabel.trim(), lat: geo.lat, lng: geo.lng });
      }
      setSubmitted(true);
    } catch (err) {
      setError(apiErrorMessage(err, "Could not post your errand."));
    } finally {
      setBusy(false);
    }
  }

  if (submitted) {
    return (
      <div className="min-h-screen bg-white">
        <Navbar />
        <div className="mx-auto max-w-xl px-4 py-24 text-center">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-brand-soft text-3xl">
            🚀
          </div>
          <h1 className="mt-6 text-3xl font-extrabold">Errand posted!</h1>
          <p className="mt-3 text-muted">
            It's live on the campus feed. You'll see the status change here the moment a runner
            accepts it.
          </p>
          <Link
            to="/"
            className="mt-8 inline-block rounded-xl bg-brand px-8 py-3.5 font-bold text-white transition hover:bg-brand-dark"
          >
            Back to home
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white">
      <Navbar />
      <div className="mx-auto max-w-xl px-4 py-10">
        <Link to="/" className="text-sm font-semibold text-muted hover:text-brand">
          ← Back
        </Link>
        <h1 className="mt-2 text-3xl font-extrabold">Post an errand</h1>
        <p className="mt-1 text-muted">Tell runners what you need and where to bring it.</p>

        {error && (
          <div className="mt-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <form onSubmit={onSubmit} className="mt-8 space-y-5">
          <div>
            <label className="mb-1.5 block text-sm font-semibold">Category</label>
            <div className="flex flex-wrap gap-2">
              {CATEGORY_NAMES.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setCategory(c)}
                  className={`rounded-full border px-4 py-2 text-sm font-semibold transition ${
                    category === c
                      ? "border-brand bg-brand text-white"
                      : "border-line text-muted hover:border-brand hover:text-brand"
                  }`}
                >
                  {c}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label htmlFor="title" className="mb-1.5 block text-sm font-semibold">
              What do you need?
            </label>
            <input
              id="title"
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. 2x veg rolls from the night canteen"
              className={inputCls}
            />
          </div>

          <div>
            <label htmlFor="pickup" className="mb-1.5 block text-sm font-semibold">
              Pickup point
            </label>
            <input
              id="pickup"
              required
              value={pickup}
              onChange={(e) => setPickup(e.target.value)}
              placeholder="e.g. Foodys, near Main Gate"
              className={inputCls}
            />
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-semibold">Deliver to</label>
            {savedDrops.length > 0 && (
              <div className="mb-2 flex flex-wrap gap-2">
                {savedDrops.map((d) => (
                  <button
                    key={d.label}
                    type="button"
                    onClick={() => {
                      setGeo({ status: "ok", lat: d.lat, lng: d.lng, accuracy: 0 });
                      setDropLabel(d.label);
                    }}
                    className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition ${
                      dropLabel === d.label && geo.status === "ok"
                        ? "border-brand bg-brand text-white"
                        : "border-line text-muted hover:border-brand hover:text-brand"
                    }`}
                  >
                    📌 {d.label}
                  </button>
                ))}
              </div>
            )}
            <div className="rounded-xl border border-line p-4">
              {geo.status === "ok" ? (
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-semibold text-green-700">📍 Location locked</div>
                    <div className="mt-0.5 text-sm text-muted">
                      {geo.lat.toFixed(5)}, {geo.lng.toFixed(5)} · ±{geo.accuracy} m
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={detectLocation}
                    className="text-sm font-semibold text-brand hover:underline"
                  >
                    Re-detect
                  </button>
                </div>
              ) : (
                <div className="flex items-center justify-between gap-4">
                  <div className="text-sm text-muted">
                    {geo.status === "error"
                      ? `Couldn't detect: ${geo.message}`
                      : "We auto-detect your drop point — no typing hostel blocks."}
                  </div>
                  <button
                    type="button"
                    onClick={detectLocation}
                    disabled={geo.status === "locating"}
                    className="shrink-0 rounded-xl bg-brand px-4 py-2.5 text-sm font-bold text-white transition hover:bg-brand-dark disabled:opacity-60"
                  >
                    {geo.status === "locating" ? "Detecting…" : "📍 Use my location"}
                  </button>
                </div>
              )}
            </div>

            <button
              type="button"
              onClick={() => setShowMap((v) => !v)}
              className="mt-2 text-sm font-semibold text-brand hover:underline"
            >
              {showMap ? "Hide campus map" : "🗺️ Or pick a spot on the campus map"}
            </button>
            {showMap && (
              <div className="mt-2">
                <CampusDropPicker
                  onConfirm={(s) => {
                    setGeo({ status: "ok", lat: s.lat, lng: s.lng, accuracy: 0 });
                    setDropLabel(s.label);
                    setShowMap(false);
                  }}
                />
              </div>
            )}

            <input
              value={dropLabel}
              onChange={(e) => setDropLabel(e.target.value)}
              placeholder="Label this spot, e.g. Block A Room 402 (saved for next time)"
              maxLength={200}
              className={`${inputCls} mt-2 text-sm`}
            />
          </div>

          {isPickupMode && (
            <div className="space-y-4 rounded-2xl border-2 border-dashed border-brand/40 bg-brand-soft/50 p-4">
              <div className="text-sm font-bold text-brand-dark">
                🔐 Pickup verification{" "}
                <span className="font-normal text-muted">
                  — only the runner who accepts can see these, every view is logged
                </span>
              </div>
              <div className="grid gap-4 sm:grid-cols-3">
                <div>
                  <label htmlFor="externalRef" className="mb-1.5 block text-sm font-semibold">
                    Order / tracking no.
                  </label>
                  <input
                    id="externalRef"
                    value={externalRef}
                    onChange={(e) => setExternalRef(e.target.value)}
                    placeholder="e.g. SWGY-123456"
                    className={inputCls}
                  />
                </div>
                <div>
                  <label htmlFor="otp" className="mb-1.5 block text-sm font-semibold">
                    Delivery OTP
                  </label>
                  <input
                    id="otp"
                    value={otp}
                    onChange={(e) => setOtp(e.target.value)}
                    placeholder="e.g. 4471"
                    maxLength={12}
                    className={inputCls}
                  />
                </div>
                <div>
                  <label htmlFor="collectAmount" className="mb-1.5 block text-sm font-semibold">
                    Cash at pickup (₹)
                  </label>
                  <input
                    id="collectAmount"
                    type="number"
                    min={0}
                    step={1}
                    value={collectAmount}
                    onChange={(e) => setCollectAmount(e.target.value)}
                    placeholder="0"
                    className={inputCls}
                  />
                </div>
              </div>
              <p className="text-xs text-muted">
                Don't put the OTP in notes — notes are visible to everyone on the feed.
              </p>
            </div>
          )}

          <div>
            <label htmlFor="reward" className="mb-1.5 block text-sm font-semibold">
              Runner reward (₹)
            </label>
            <input
              id="reward"
              type="number"
              min={10}
              step={5}
              required
              value={reward}
              onChange={(e) => setReward(e.target.value)}
              className={inputCls}
            />
            <p className="mt-1 text-xs text-muted">
              What you pay the runner on top of item cost. ₹20–₹50 is typical.
            </p>
          </div>

          <div>
            <label htmlFor="notes" className="mb-1.5 block text-sm font-semibold">
              Notes <span className="font-normal text-muted">(optional)</span>
            </label>
            <textarea
              id="notes"
              rows={3}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Anything the runner should know"
              className={inputCls}
            />
          </div>

          <button
            type="submit"
            disabled={geo.status !== "ok" || busy}
            className="w-full rounded-xl bg-brand py-3.5 font-bold text-white transition hover:bg-brand-dark disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy
              ? "Posting…"
              : geo.status === "ok"
                ? "Post errand"
                : "Detect your location to continue"}
          </button>
        </form>
      </div>
    </div>
  );
}
