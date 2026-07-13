import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { createErrand } from "../api/errands";
import { fetchMenu, type MenuItem } from "../api/vendors";
import Navbar from "../components/Navbar";
import { apiErrorMessage } from "../lib/api";

type Cart = Record<string, number>; // menu_item_id -> quantity

type Geo =
  | { status: "idle" }
  | { status: "locating" }
  | { status: "ok"; lat: number; lng: number }
  | { status: "error"; message: string };

const inputCls =
  "w-full rounded-xl border border-line px-4 py-3 outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20";

export default function Menu() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [cart, setCart] = useState<Cart>({});
  const [checkout, setCheckout] = useState(false);
  const [geo, setGeo] = useState<Geo>({ status: "idle" });
  const [dropLabel, setDropLabel] = useState("");
  const [reward, setReward] = useState("25");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: menu, refetch } = useQuery({
    queryKey: ["menu", id],
    queryFn: () => fetchMenu(id!),
    enabled: !!id,
    refetchInterval: 30_000, // sold-out states move fast at a canteen
  });

  const sections = useMemo(() => {
    const grouped = new Map<string, MenuItem[]>();
    (menu?.items ?? []).forEach((item) => {
      grouped.set(item.section, [...(grouped.get(item.section) ?? []), item]);
    });
    return [...grouped.entries()];
  }, [menu]);

  const byId = useMemo(
    () => new Map((menu?.items ?? []).map((i) => [i.id, i])),
    [menu],
  );
  const cartLines = Object.entries(cart).filter(([, q]) => q > 0);
  const cartCount = cartLines.reduce((n, [, q]) => n + q, 0);
  const cartTotal = cartLines.reduce(
    (sum, [itemId, q]) => sum + (byId.get(itemId)?.price ?? 0) * q,
    0,
  );

  function setQty(itemId: string, qty: number) {
    setCart((c) => ({ ...c, [itemId]: Math.max(0, qty) }));
  }

  function detectLocation() {
    setGeo({ status: "locating" });
    navigator.geolocation.getCurrentPosition(
      (pos) => setGeo({ status: "ok", lat: pos.coords.latitude, lng: pos.coords.longitude }),
      (err) => setGeo({ status: "error", message: err.message }),
      { enableHighAccuracy: true, timeout: 10_000 },
    );
  }

  async function placeOrder() {
    if (geo.status !== "ok" || !menu) return;
    setBusy(true);
    setError(null);
    try {
      const errand = await createErrand({
        category: menu.vendor.category,
        vendor_id: menu.vendor.id,
        items: cartLines.map(([menu_item_id, quantity]) => ({ menu_item_id, quantity })),
        title: `${menu.vendor.name}: ${cartLines
          .map(([iid, q]) => `${q}x ${byId.get(iid)?.name}`)
          .join(", ")}`.slice(0, 200),
        pickup_label: menu.vendor.name,
        drop_lat: geo.lat,
        drop_lng: geo.lng,
        drop_label: dropLabel.trim() || undefined,
        reward: Number(reward),
      });
      navigate(`/errands/${errand.id}`);
    } catch (err) {
      // Revalidation 409s land here with the diff ("X is sold out") — refresh
      // the menu so the UI matches reality.
      setError(apiErrorMessage(err, "Could not place the order."));
      refetch();
    } finally {
      setBusy(false);
    }
  }

  if (!menu) {
    return (
      <div className="min-h-screen bg-white">
        <Navbar />
        <div className="mx-auto max-w-3xl px-4 py-20 text-center text-muted">Loading menu…</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white pb-28">
      <Navbar />
      <div className="mx-auto max-w-3xl px-4 py-8">
        <Link to="/shops" className="text-sm font-semibold text-muted hover:text-brand">
          ← All stores
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="text-3xl font-extrabold">{menu.vendor.name}</h1>
          <span
            className={`rounded-full px-2.5 py-1 text-xs font-bold ${
              menu.vendor.is_open ? "bg-green-50 text-green-700" : "bg-gray-100 text-muted"
            }`}
          >
            {menu.vendor.is_open ? "● Open" : "Closed"}
          </span>
          {menu.stale && (
            <span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-bold text-amber-700">
              menu may be slightly out of date
            </span>
          )}
        </div>
        {menu.vendor.description && <p className="mt-1 text-muted">{menu.vendor.description}</p>}

        {/* Sticky section nav */}
        {sections.length > 1 && (
          <div className="sticky top-16 z-10 -mx-4 mt-6 flex gap-2 overflow-x-auto border-b border-line bg-white/95 px-4 py-2 backdrop-blur">
            {sections.map(([section]) => (
              <a
                key={section}
                href={`#section-${section}`}
                className="shrink-0 rounded-full border border-line px-3 py-1.5 text-sm font-semibold text-muted transition hover:border-brand hover:text-brand"
              >
                {section}
              </a>
            ))}
          </div>
        )}

        {error && (
          <div className="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* Menu sections */}
        {sections.map(([section, items]) => (
          <section key={section} id={`section-${section}`} className="mt-8 scroll-mt-32">
            <h2 className="text-xl font-extrabold">{section}</h2>
            <div className="mt-3 space-y-2">
              {items.map((item) => {
                const qty = cart[item.id] ?? 0;
                return (
                  <div
                    key={item.id}
                    className={`flex items-center justify-between gap-4 rounded-xl border border-line px-4 py-3 ${
                      item.is_available ? "" : "opacity-50"
                    }`}
                  >
                    <div>
                      <div className="font-semibold">{item.name}</div>
                      <div className="text-sm text-muted">
                        ₹{item.price.toFixed(0)}
                        {!item.is_available && (
                          <span className="ml-2 font-bold text-red-500">Sold out</span>
                        )}
                      </div>
                    </div>
                    {item.is_available &&
                      (qty === 0 ? (
                        <button
                          onClick={() => setQty(item.id, 1)}
                          className="rounded-xl border-2 border-brand px-5 py-1.5 text-sm font-bold text-brand transition hover:bg-brand hover:text-white"
                        >
                          ADD
                        </button>
                      ) : (
                        <div className="flex items-center gap-3 rounded-xl border-2 border-brand px-3 py-1.5">
                          <button
                            onClick={() => setQty(item.id, qty - 1)}
                            className="text-lg font-bold text-brand"
                          >
                            −
                          </button>
                          <span className="w-5 text-center font-bold">{qty}</span>
                          <button
                            onClick={() => setQty(item.id, qty + 1)}
                            className="text-lg font-bold text-brand"
                          >
                            +
                          </button>
                        </div>
                      ))}
                  </div>
                );
              })}
            </div>
          </section>
        ))}
      </div>

      {/* Bottom cart bar */}
      {cartCount > 0 && !checkout && (
        <div className="fixed inset-x-0 bottom-0 z-20 border-t border-line bg-white p-4 shadow-2xl">
          <div className="mx-auto flex max-w-3xl items-center justify-between gap-4">
            <div className="font-bold">
              {cartCount} item{cartCount > 1 ? "s" : ""} ·{" "}
              <span className="text-brand-dark">₹{cartTotal.toFixed(0)}</span>
            </div>
            <button
              onClick={() => setCheckout(true)}
              disabled={!menu.vendor.is_open}
              className="rounded-xl bg-brand px-6 py-3 font-bold text-white transition hover:bg-brand-dark disabled:opacity-50"
            >
              {menu.vendor.is_open ? "Checkout →" : "Store closed"}
            </button>
          </div>
        </div>
      )}

      {/* Checkout drawer */}
      {checkout && (
        <div className="fixed inset-x-0 bottom-0 z-20 border-t border-line bg-white p-5 shadow-2xl">
          <div className="mx-auto max-w-3xl space-y-4">
            <div className="flex items-center justify-between">
              <div className="font-extrabold">
                {cartCount} items · ₹{cartTotal.toFixed(0)}{" "}
                <span className="text-sm font-normal text-muted">+ ₹{reward || 0} runner reward</span>
              </div>
              <button onClick={() => setCheckout(false)} className="text-sm font-semibold text-muted">
                ✕ close
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {cartLines.map(([itemId, qty]) => (
                <span
                  key={itemId}
                  className="rounded-full bg-brand-soft px-3 py-1 text-xs font-semibold text-brand-dark"
                >
                  {qty}× {byId.get(itemId)?.name} · ₹{((byId.get(itemId)?.price ?? 0) * qty).toFixed(0)}
                </span>
              ))}
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-xl border border-line p-3 text-sm">
                {geo.status === "ok" ? (
                  <span className="font-semibold text-green-700">📍 Location locked</span>
                ) : (
                  <button
                    onClick={detectLocation}
                    disabled={geo.status === "locating"}
                    className="font-bold text-brand"
                  >
                    {geo.status === "locating" ? "Detecting…" : "📍 Use my location"}
                  </button>
                )}
                {geo.status === "error" && (
                  <div className="mt-1 text-xs text-red-600">{geo.message}</div>
                )}
              </div>
              <input
                value={dropLabel}
                onChange={(e) => setDropLabel(e.target.value)}
                placeholder="Room / block (optional)"
                className={inputCls}
              />
              <input
                type="number"
                min={10}
                step={5}
                value={reward}
                onChange={(e) => setReward(e.target.value)}
                className={inputCls}
                aria-label="Runner reward"
              />
            </div>
            <button
              onClick={placeOrder}
              disabled={geo.status !== "ok" || busy}
              className="w-full rounded-xl bg-brand py-3.5 font-bold text-white transition hover:bg-brand-dark disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busy ? "Placing order…" : `Place order · ₹${(cartTotal + Number(reward || 0)).toFixed(0)}`}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
