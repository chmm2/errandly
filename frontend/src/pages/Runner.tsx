import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import {
  acceptErrand,
  deliverErrand,
  type Errand,
  fetchFeed,
  fetchHandoffSecret,
  fetchMyErrands,
  type HandoffSecret,
  pickupErrand,
  releaseErrand,
} from "../api/errands";
import { setPhoto } from "../api/auth";
import { fetchEarnings } from "../api/ledger";
import { fetchRunnerProfile, setAvailability, updateLocation } from "../api/runners";
import Navbar from "../components/Navbar";
import PriceClaimPanel from "../components/PriceClaimPanel";
import { apiErrorMessage } from "../lib/api";
import { useSocket } from "../lib/ws";
import { useAuth } from "../stores/auth";

type Geo = { lat: number; lng: number };

/** Center-crop + shrink an image file to a small square data URL, so avatars
 * stay tiny (a few KB) — no object storage needed. */
function resizeImage(file: File, size = 128): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = canvas.height = size;
      const ctx = canvas.getContext("2d");
      if (!ctx) return reject(new Error("no canvas"));
      const min = Math.min(img.width, img.height);
      ctx.drawImage(img, (img.width - min) / 2, (img.height - min) / 2, min, min, 0, 0, size, size);
      URL.revokeObjectURL(img.src);
      resolve(canvas.toDataURL("image/jpeg", 0.8));
    };
    img.onerror = reject;
    img.src = URL.createObjectURL(file);
  });
}

interface Offer {
  errand_id: string;
  title: string;
  reward: number;
  distance_m?: number;
}

const CATEGORY_ICONS: Record<string, string> = {
  FOOD: "🍔",
  GROCERY: "🛒",
  PARCEL: "📦",
  STATIONERY: "📚",
  PHARMACY: "💊",
  CUSTOM: "✨",
};

function metersLabel(m: number | null | undefined) {
  if (m == null) return null;
  return m < 1000 ? `${Math.round(m)} m` : `${(m / 1000).toFixed(1)} km`;
}

function HandoffPanel({ errandId }: { errandId: string }) {
  const [secret, setSecret] = useState<HandoffSecret | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function reveal() {
    try {
      setSecret(await fetchHandoffSecret(errandId));
    } catch (err) {
      setError(apiErrorMessage(err, "Could not fetch handoff details."));
    }
  }

  if (secret) {
    return (
      <div className="mt-3 rounded-xl border-2 border-dashed border-brand bg-brand-soft p-4">
        <div className="text-xs font-bold uppercase tracking-wide text-brand-dark">
          Pickup verification — viewing is logged
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-x-8 gap-y-2">
          {secret.otp && (
            <div>
              <div className="text-xs text-muted">Delivery OTP</div>
              <div className="text-3xl font-extrabold tracking-[0.3em] text-ink">
                {secret.otp}
              </div>
            </div>
          )}
          {secret.external_ref && (
            <div>
              <div className="text-xs text-muted">Order no.</div>
              <div className="font-bold">{secret.external_ref}</div>
            </div>
          )}
          {secret.collect_amount > 0 && (
            <div>
              <div className="text-xs text-muted">Pay at pickup (reimbursed)</div>
              <div className="font-bold text-brand-dark">₹{secret.collect_amount.toFixed(0)}</div>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="mt-3">
      <button
        onClick={reveal}
        className="rounded-lg border border-brand px-3 py-1.5 text-sm font-bold text-brand transition hover:bg-brand-soft"
      >
        🔐 Reveal pickup OTP / order no.
      </button>
      {error && <span className="ml-3 text-sm text-red-600">{error}</span>}
    </div>
  );
}

export default function Runner() {
  const user = useAuth((s) => s.user);
  const setUser = useAuth((s) => s.setUser);
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);

  async function onPhoto(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      setUser(await setPhoto(await resizeImage(file)));
    } catch {
      /* ignore bad image */
    }
  }
  const [geo, setGeo] = useState<Geo | null>(null);
  const [toggleBusy, setToggleBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [offers, setOffers] = useState<Offer[]>([]);

  const { data: profile } = useQuery({
    queryKey: ["runner-profile"],
    queryFn: fetchRunnerProfile,
  });
  const { data: earnings } = useQuery({ queryKey: ["earnings"], queryFn: fetchEarnings });
  const available = profile?.is_available ?? false;

  // While online, stream position: watchPosition fires on movement, we
  // forward at most one update per 10s (the server throttles again at 5s —
  // belt and braces on both ends of the wire).
  const lastSentRef = useRef(0);
  useEffect(() => {
    if (!available || !navigator.geolocation.watchPosition) return;
    const watchId = navigator.geolocation.watchPosition(
      (pos) => {
        const now = Date.now();
        if (now - lastSentRef.current < 10_000) return;
        lastSentRef.current = now;
        const loc = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        setGeo(loc);
        updateLocation(loc.lat, loc.lng).catch(() => {});
      },
      () => {},
      { enableHighAccuracy: true },
    );
    return () => navigator.geolocation.clearWatch(watchId);
  }, [available]);

  // Live offers pushed by the matching engine (Redis pub/sub → WS)
  useSocket(
    available ? "/ws/runner" : null,
    useCallback(
      (data: Record<string, unknown>) => {
        if (data.type === "offer") {
          setOffers((prev) =>
            prev.some((o) => o.errand_id === data.errand_id)
              ? prev
              : [data as unknown as Offer, ...prev].slice(0, 5),
          );
          queryClient.invalidateQueries({ queryKey: ["runner-feed"] });
        }
      },
      [queryClient],
    ),
  );

  const { data: feed } = useQuery({
    queryKey: ["runner-feed", geo?.lat, geo?.lng],
    queryFn: () => fetchFeed(20, 0, geo ?? undefined),
    enabled: available,
    refetchInterval: 20_000,
  });

  const { data: mine } = useQuery({ queryKey: ["my-errands"], queryFn: fetchMyErrands });
  const activeRuns = (mine?.running ?? []).filter((e) =>
    ["ACCEPTED", "IN_PROGRESS"].includes(e.status),
  );

  function refresh() {
    queryClient.invalidateQueries({ queryKey: ["runner-feed"] });
    queryClient.invalidateQueries({ queryKey: ["my-errands"] });
    queryClient.invalidateQueries({ queryKey: ["runner-profile"] });
  }

  const accept = useMutation({
    mutationFn: acceptErrand,
    onSuccess: (errand) => {
      setOffers((prev) => prev.filter((o) => o.errand_id !== errand.id));
      refresh();
    },
    onError: (err, errandId) => {
      // Lost the race (someone else accepted) or hit the load cap — either
      // way this offer is dead; drop the card instead of leaving a trap.
      setOffers((prev) => prev.filter((o) => o.errand_id !== errandId));
      setError(apiErrorMessage(err, "Could not accept."));
    },
    onSettled: refresh,
  });
  const pickup = useMutation({ mutationFn: pickupErrand, onSettled: refresh });
  const deliver = useMutation({ mutationFn: deliverErrand, onSettled: refresh });
  const release = useMutation({
    mutationFn: releaseErrand,
    onError: (err) => setError(apiErrorMessage(err, "Could not release this errand.")),
    onSettled: refresh,
  });

  async function toggle() {
    setError(null);
    setToggleBusy(true);
    try {
      if (available) {
        await setAvailability(false);
        setOffers([]);
      } else {
        const pos = await new Promise<GeolocationPosition>((resolve, reject) =>
          navigator.geolocation.getCurrentPosition(resolve, reject, {
            enableHighAccuracy: true,
            timeout: 10_000,
          }),
        );
        const loc = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        setGeo(loc);
        await setAvailability(true, loc);
      }
      refresh();
    } catch (err) {
      setError(
        err instanceof GeolocationPositionError
          ? `Location needed to go online: ${err.message}`
          : apiErrorMessage(err, "Could not update availability."),
      );
    } finally {
      setToggleBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-white">
      <Navbar />

      {/* Availability hero */}
      <section
        className={`text-white transition-colors ${
          available
            ? "bg-gradient-to-br from-emerald-500 to-emerald-700"
            : "bg-gradient-to-br from-ink to-[#3d4152]"
        }`}
      >
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-6 px-4 py-10">
          <div>
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              title="Change your photo"
              className="mb-3 flex items-center gap-3"
            >
              {user?.photo_url ? (
                <img
                  src={user.photo_url}
                  alt="You"
                  className="h-12 w-12 rounded-full object-cover ring-2 ring-white/60"
                />
              ) : (
                <span className="flex h-12 w-12 items-center justify-center rounded-full bg-white/20 text-lg font-extrabold">
                  {(user?.display_name ?? "?").charAt(0).toUpperCase()}
                </span>
              )}
              <span className="text-xs font-semibold text-white/80 underline">
                {user?.photo_url ? "Change photo" : "📷 Add a photo"}
              </span>
            </button>
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={onPhoto}
            />
            <h1 className="text-3xl font-extrabold sm:text-4xl">
              {available ? "You're online 🟢" : "Runner mode"}
            </h1>
            <p className="mt-2 max-w-md text-white/85">
              {available
                ? "Nearby errands are being offered to you live. Deliver, earn, repeat."
                : `Hey ${user?.display_name?.split(" ")[0] ?? "runner"} — flip the switch when you're heading out and pick up errands on your way.`}
            </p>
            {profile && (
              <p className="mt-3 text-sm font-semibold text-white/90">
                Active runs: {profile.active_load} / {profile.max_load}
              </p>
            )}
            {earnings && (
              <div className="mt-4 inline-flex gap-6 rounded-2xl bg-white/10 px-5 py-3 backdrop-blur-sm">
                <div>
                  <div className="text-xl font-extrabold">₹{earnings.week_total.toFixed(0)}</div>
                  <div className="text-xs text-white/80">this week · {earnings.week_runs} runs</div>
                </div>
                <div>
                  <div className="text-xl font-extrabold">₹{earnings.balance.toFixed(0)}</div>
                  <div className="text-xs text-white/80">earned all-time</div>
                </div>
                <Link to="/wallet" className="self-center text-xs font-bold underline">
                  Wallet →
                </Link>
              </div>
            )}
          </div>
          <button
            onClick={toggle}
            disabled={toggleBusy}
            className={`rounded-2xl px-8 py-4 text-lg font-extrabold shadow-xl transition hover:-translate-y-0.5 disabled:opacity-60 ${
              available ? "bg-white text-emerald-700" : "bg-brand text-white"
            }`}
          >
            {toggleBusy ? "…" : available ? "Go offline" : "📍 Go online"}
          </button>
        </div>
      </section>

      <div className="mx-auto max-w-6xl px-4 py-8">
        {error && (
          <div className="mb-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* Live offers */}
        {offers.length > 0 && (
          <section className="mb-8">
            <h2 className="text-xl font-extrabold">⚡ Offered to you just now</h2>
            <div className="mt-3 space-y-2">
              {offers.map((o) => (
                <div
                  key={o.errand_id}
                  className="flex items-center justify-between gap-4 rounded-2xl border-2 border-brand bg-brand-soft p-4 shadow-sm"
                >
                  <div className="min-w-0">
                    <div className="truncate font-bold">{o.title}</div>
                    <div className="text-sm text-muted">
                      ₹{Number(o.reward).toFixed(0)} reward
                      {o.distance_m != null && <> · {metersLabel(o.distance_m)} away</>}
                    </div>
                  </div>
                  <button
                    onClick={() => accept.mutate(o.errand_id)}
                    disabled={accept.isPending}
                    className="shrink-0 rounded-xl bg-brand px-5 py-2.5 font-bold text-white transition hover:bg-brand-dark disabled:opacity-60"
                  >
                    Accept
                  </button>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* My active runs */}
        <section className="mb-8">
          <h2 className="text-xl font-extrabold">Your active runs</h2>
          {activeRuns.length === 0 ? (
            <p className="mt-3 text-sm text-muted">
              Nothing yet — accept an errand below and it appears here.
            </p>
          ) : (
            <div className="mt-3 space-y-3">
              {activeRuns.map((e: Errand) => (
                <div key={e.id} className="rounded-2xl border border-line p-5">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex min-w-0 items-center gap-3">
                      <span className="text-2xl">{CATEGORY_ICONS[e.category] ?? "✨"}</span>
                      <div className="min-w-0">
                        <div className="truncate font-bold">{e.title}</div>
                        <div className="truncate text-sm text-muted">
                          {e.pickup_label} → drop · ₹{Number(e.reward).toFixed(0)}
                          {e.collect_amount > 0 && (
                            <span className="font-semibold text-brand-dark">
                              {" "}
                              · pay ₹{Number(e.collect_amount).toFixed(0)} at pickup
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      {e.status === "ACCEPTED" &&
                        e.accepted_at != null &&
                        Date.now() - new Date(e.accepted_at).getTime() < 5 * 60 * 1000 && (
                          <button
                            onClick={() => release.mutate(e.id)}
                            disabled={release.isPending}
                            title="Hand it back to the queue for another runner (within 5 min)"
                            className="rounded-xl border border-line px-4 py-2 text-sm font-semibold text-muted transition hover:border-red-400 hover:text-red-600 disabled:opacity-60"
                          >
                            Not for me ↩
                          </button>
                        )}
                      {e.status === "ACCEPTED" && (
                        <button
                          onClick={() => pickup.mutate(e.id)}
                          disabled={pickup.isPending}
                          className="rounded-xl bg-brand px-4 py-2 text-sm font-bold text-white transition hover:bg-brand-dark disabled:opacity-60"
                        >
                          Picked up 📦
                        </button>
                      )}
                      {e.status === "IN_PROGRESS" && (
                        <button
                          onClick={() => deliver.mutate(e.id)}
                          disabled={deliver.isPending}
                          className="rounded-xl bg-emerald-600 px-4 py-2 text-sm font-bold text-white transition hover:bg-emerald-700 disabled:opacity-60"
                        >
                          Arrived ✅
                        </button>
                      )}
                    </div>
                  </div>
                  {e.has_handoff_secret && <HandoffPanel errandId={e.id} />}
                  {/* Report prices BEFORE delivery — once the errand completes,
                      settlement has already drawn on whatever was claimed. */}
                  <PriceClaimPanel errandId={e.id} />
                  <Link
                    to={`/errands/${e.id}`}
                    className="mt-3 inline-block text-sm font-semibold text-brand hover:underline"
                  >
                    💬 Chat &amp; order details →
                  </Link>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Nearby feed */}
        <section>
          <h2 className="text-xl font-extrabold">
            {available ? "Open errands near you" : "Open errands"}
          </h2>
          {!available ? (
            <div className="mt-4 rounded-2xl border-2 border-dashed border-line p-10 text-center text-muted">
              Go online to see nearby errands sorted by distance.
            </div>
          ) : (feed?.items ?? []).length === 0 ? (
            <div className="mt-4 rounded-2xl border-2 border-dashed border-line p-10 text-center">
              <div className="text-4xl">🌤️</div>
              <p className="mt-3 font-semibold">No open errands right now</p>
              <p className="text-sm text-muted">New ones will be offered to you live.</p>
            </div>
          ) : (
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              {feed!.items.map((e) => (
                <div
                  key={e.id}
                  className="flex flex-col rounded-2xl border border-line p-5 transition hover:shadow-md"
                >
                  <div className="flex items-start justify-between gap-3">
                    <span className="text-3xl">{CATEGORY_ICONS[e.category] ?? "✨"}</span>
                    {e.distance_m != null && (
                      <span className="rounded-full bg-brand-soft px-2.5 py-1 text-xs font-bold text-brand-dark">
                        {metersLabel(e.distance_m)}
                      </span>
                    )}
                  </div>
                  <div className="mt-2 font-bold">{e.title}</div>
                  <div className="mt-0.5 text-sm text-muted">from {e.pickup_label}</div>
                  <div className="mt-3 flex items-center justify-between">
                    <div className="text-lg font-extrabold text-ink">
                      ₹{Number(e.reward).toFixed(0)}
                      {e.has_handoff_secret && (
                        <span className="ml-2 align-middle text-xs font-bold text-muted">
                          🔐 OTP
                        </span>
                      )}
                    </div>
                    <button
                      onClick={() => accept.mutate(e.id)}
                      disabled={accept.isPending}
                      className="rounded-xl bg-brand px-4 py-2 text-sm font-bold text-white transition hover:bg-brand-dark disabled:opacity-60"
                    >
                      Accept
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
