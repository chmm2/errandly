import { type FormEvent, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { type Category, createErrand } from "../api/errands";
import CampusDropPicker from "../components/CampusDropPicker";
import type { ReferenceSuggestion } from "../api/fraud";
import HoldBreakdown from "../components/HoldBreakdown";
import ItemSearchInput from "../components/ItemSearchInput";
import Navbar from "../components/Navbar";
import { apiErrorMessage } from "../lib/api";

// The three "shopping list" sub-types share one flow but keep their own
// backend category so history/analytics stay meaningful.
const SHOPPING_TYPES: { label: string; category: Category; buyFrom: string }[] = [
  { label: "Groceries", category: "GROCERY", buyFrom: "e.g. Campus store, Poorvika" },
  { label: "Stationery", category: "STATIONERY", buyFrom: "e.g. Xerox shop, stationery store" },
  { label: "Pharmacy", category: "PHARMACY", buyFrom: "e.g. Health centre, medical store" },
];

type Flow = "shopping" | "parcel" | "gate";

const inputCls =
  "w-full rounded-xl border border-line px-4 py-3 outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20";

type GeoState =
  | { status: "idle" }
  | { status: "locating" }
  | { status: "ok"; lat: number; lng: number; accuracy: number }
  | { status: "error"; message: string };

interface ShopItem {
  name: string;
  qty: number;
  note: string;
  // Set when the line was picked off the admin's non-MRP price list. It is
  // what earns the line escrow headroom, so it has to travel with the order.
  ref: ReferenceSuggestion | null;
}

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

function initialFlow(state: { mode?: string; category?: string } | null): Flow {
  if (state?.category === "Parcel pickup") return "parcel";
  if (state?.category === "Main gate") return "gate";
  return "shopping";
}

export default function NewErrand() {
  const preset = useLocation().state as { mode?: string; category?: string } | null;
  const navigate = useNavigate();
  const [flow, setFlow] = useState<Flow>(() => initialFlow(preset));

  // Shopping-list state
  const [shopType, setShopType] = useState(0); // index into SHOPPING_TYPES
  const [items, setItems] = useState<ShopItem[]>([{ name: "", qty: 1, note: "", ref: null }]);
  const [buyFrom, setBuyFrom] = useState("");

  // Pickup (parcel / main gate) state
  const [title, setTitle] = useState("");
  const [pickup, setPickup] = useState(preset?.category === "Main gate" ? "Main Gate" : "");
  const [externalRef, setExternalRef] = useState("");
  const [otp, setOtp] = useState("");
  const [collectAmount, setCollectAmount] = useState("");

  // Shared
  const [reward, setReward] = useState("30");
  const [waitMinutes, setWaitMinutes] = useState(30);
  const [notes, setNotes] = useState("");
  const [geo, setGeo] = useState<GeoState>({ status: "idle" });
  const [dropLabel, setDropLabel] = useState("");
  const [showMap, setShowMap] = useState(false);
  const [savedDrops] = useState<SavedDrop[]>(loadSavedDrops);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isPickup = flow === "parcel" || flow === "gate";

  // Only priced lines count. A hand-typed line nobody has priced contributes
  // nothing here and earns no headroom - there is no number to take 16% of.
  const nonMrpTotal =
    flow === "shopping"
      ? items.reduce(
          (sum, it) => sum + (it.ref ? it.ref.reference_price * it.qty : 0),
          0,
        )
      : 0;

  function switchFlow(next: Flow) {
    setFlow(next);
    setError(null);
    if (next === "gate" && !pickup) setPickup("Main Gate");
    if (next === "parcel" && pickup === "Main Gate") setPickup("");
  }

  function setItem(i: number, patch: Partial<ShopItem>) {
    setItems((prev) => prev.map((it, idx) => (idx === i ? { ...it, ...patch } : it)));
  }
  function addItem() {
    setItems((prev) => [...prev, { name: "", qty: 1, note: "", ref: null }]);
  }
  function removeItem(i: number) {
    setItems((prev) => (prev.length === 1 ? prev : prev.filter((_, idx) => idx !== i)));
  }

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

  function buildPayload() {
    const shared = {
      pickup_label: isPickup ? pickup : buyFrom,
      drop_lat: geo.status === "ok" ? geo.lat : 0,
      drop_lng: geo.status === "ok" ? geo.lng : 0,
      drop_label: dropLabel.trim() || undefined,
      reward: Number(reward),
      wait_minutes: waitMinutes,
    };

    if (flow === "shopping") {
      const type = SHOPPING_TYPES[shopType];
      const valid = items.filter((it) => it.name.trim());
      const summary = valid.map((it) => `${it.qty}× ${it.name.trim()}`).join(", ");
      return {
        ...shared,
        category: type.category,
        title: `${type.label}: ${summary}`.slice(0, 200),
        // Structured lines so the runner can mark one out of stock later.
        list_items: valid.map((it) => ({
          name: it.name.trim().slice(0, 120),
          quantity: it.qty,
          note: it.note.trim() ? it.note.trim().slice(0, 200) : undefined,
          // Only the id travels. The server re-reads the price from that row,
          // so nothing the client sends can change what gets held.
          reference_id: it.ref?.reference_id,
        })),
        notes: notes.trim() || undefined,
      };
    }

    // parcel / main gate
    return {
      ...shared,
      category: (flow === "parcel" ? "PARCEL" : "CUSTOM") as Category,
      title: title.trim(),
      notes: notes.trim() || undefined,
      external_ref: externalRef.trim() || undefined,
      otp: otp.trim() || undefined,
      collect_amount: collectAmount ? Number(collectAmount) : undefined,
    };
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (geo.status !== "ok") {
      setError("Set your drop location to continue.");
      return;
    }
    if (flow === "shopping" && !items.some((it) => it.name.trim())) {
      setError("Add at least one item to your list.");
      return;
    }
    setBusy(true);
    try {
      const created = await createErrand(buildPayload());
      if (dropLabel.trim() && geo.status === "ok") {
        saveDrop({ label: dropLabel.trim(), lat: geo.lat, lng: geo.lng });
      }
      // Straight to live tracking — no dead-end "posted!" screen.
      navigate(`/errands/${created.id}`);
    } catch (err) {
      setError(apiErrorMessage(err, "Could not post your errand."));
      setBusy(false);
    }
  }

  const FLOW_TABS: { key: Flow; icon: string; label: string }[] = [
    { key: "shopping", icon: "🛒", label: "Shopping list" },
    { key: "parcel", icon: "📦", label: "Parcel pickup" },
    { key: "gate", icon: "🛺", label: "Main gate" },
  ];

  return (
    <div className="min-h-screen bg-white">
      <Navbar />
      <div className="mx-auto max-w-xl px-4 py-10">
        <Link to="/" className="text-sm font-semibold text-muted hover:text-brand">
          ← Back
        </Link>
        <h1 className="mt-2 text-3xl font-extrabold">Post an errand</h1>
        <p className="mt-1 text-muted">
          Tell runners what you need and where to bring it. For food, browse the{" "}
          <Link to="/shops" state={{ category: "FOOD" }} className="font-semibold text-brand hover:underline">
            canteens
          </Link>
          .
        </p>

        {/* Flow picker */}
        <div className="mt-6 grid grid-cols-3 gap-2">
          {FLOW_TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => switchFlow(t.key)}
              className={`rounded-2xl border p-3 text-center transition ${
                flow === t.key
                  ? "border-brand bg-brand-soft"
                  : "border-line hover:border-brand"
              }`}
            >
              <div className="text-2xl">{t.icon}</div>
              <div className="mt-1 text-sm font-bold">{t.label}</div>
            </button>
          ))}
        </div>

        {error && (
          <div className="mt-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <form onSubmit={onSubmit} className="mt-8 space-y-5">
          {flow === "shopping" ? (
            <>
              {/* Sub-type */}
              <div>
                <label className="mb-1.5 block text-sm font-semibold">What are you buying?</label>
                <div className="flex flex-wrap gap-2">
                  {SHOPPING_TYPES.map((t, i) => (
                    <button
                      key={t.label}
                      type="button"
                      onClick={() => setShopType(i)}
                      className={`rounded-full border px-4 py-2 text-sm font-semibold transition ${
                        shopType === i
                          ? "border-brand bg-brand text-white"
                          : "border-line text-muted hover:border-brand hover:text-brand"
                      }`}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Item list */}
              <div>
                <label className="mb-1.5 block text-sm font-semibold">Your list</label>
                <div className="space-y-3">
                  {items.map((it, i) => (
                    <div key={i} className="rounded-2xl border border-line p-3">
                      <div className="flex items-center gap-2">
                        <ItemSearchInput
                          className="flex-1"
                          value={it.name}
                          picked={it.ref}
                          onChange={(name) => setItem(i, { name })}
                          onPick={(ref) => setItem(i, { ref })}
                          placeholder={`Item ${i + 1} — search the campus price list`}
                        />
                        <div className="flex shrink-0 items-center gap-2 rounded-xl border border-line px-2 py-1.5">
                          <button
                            type="button"
                            onClick={() => setItem(i, { qty: Math.max(1, it.qty - 1) })}
                            className="text-lg font-bold text-brand"
                            aria-label="Decrease quantity"
                          >
                            −
                          </button>
                          <span className="w-5 text-center font-bold">{it.qty}</span>
                          <button
                            type="button"
                            onClick={() => setItem(i, { qty: Math.min(99, it.qty + 1) })}
                            className="text-lg font-bold text-brand"
                            aria-label="Increase quantity"
                          >
                            +
                          </button>
                        </div>
                        {items.length > 1 && (
                          <button
                            type="button"
                            onClick={() => removeItem(i)}
                            className="shrink-0 px-1 text-lg text-muted transition hover:text-red-600"
                            aria-label="Remove item"
                          >
                            ✕
                          </button>
                        )}
                      </div>
                      <input
                        value={it.note}
                        onChange={(e) => setItem(i, { note: e.target.value })}
                        placeholder="Extra detail (brand, size, flavour…) — optional"
                        className={`${inputCls} mt-2 text-sm`}
                      />
                    </div>
                  ))}
                </div>
                <button
                  type="button"
                  onClick={addItem}
                  className="mt-3 rounded-xl border-2 border-dashed border-brand/50 px-4 py-2.5 text-sm font-bold text-brand transition hover:bg-brand-soft"
                >
                  + Add item
                </button>
              </div>

              <div>
                <label htmlFor="buyFrom" className="mb-1.5 block text-sm font-semibold">
                  Buy from
                </label>
                <input
                  id="buyFrom"
                  required
                  value={buyFrom}
                  onChange={(e) => setBuyFrom(e.target.value)}
                  placeholder={SHOPPING_TYPES[shopType].buyFrom}
                  className={inputCls}
                />
              </div>
            </>
          ) : (
            <>
              <div>
                <label htmlFor="title" className="mb-1.5 block text-sm font-semibold">
                  {flow === "parcel" ? "What's the parcel?" : "What are you picking up?"}
                </label>
                <input
                  id="title"
                  required
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder={
                    flow === "parcel"
                      ? "e.g. Amazon package — small box"
                      : "e.g. Zomato order waiting at the gate"
                  }
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
                  placeholder={flow === "parcel" ? "e.g. Parcel point, block C" : "e.g. Main Gate"}
                  className={inputCls}
                />
              </div>
            </>
          )}

          {/* Deliver to (shared) */}
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

          {isPickup && (
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

          {/* What placing this will actually take out of the wallet. On a
              shopping list there is no priced basket yet, so only the reward
              is known - and that is exactly what this then shows. */}
          <HoldBreakdown
            spend={Number(collectAmount || 0) + nonMrpTotal}
            padded={nonMrpTotal}
            fee={Number(reward || 0)}
          />

          <div>
            <label className="mb-1.5 block text-sm font-semibold">
              How long will you wait for a runner?
            </label>
            <div className="flex flex-wrap gap-2">
              {[15, 30, 45, 60].map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => setWaitMinutes(m)}
                  className={`rounded-full border px-4 py-2 text-sm font-semibold transition ${
                    waitMinutes === m
                      ? "border-brand bg-brand text-white"
                      : "border-line text-muted hover:border-brand hover:text-brand"
                  }`}
                >
                  {m} min
                </button>
              ))}
            </div>
            <p className="mt-1 text-xs text-muted">
              We keep offering your errand until then. No runner by the deadline → it expires and
              nothing is charged.
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
