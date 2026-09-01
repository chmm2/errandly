import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { type ClaimLine, type ClaimResult, submitClaims } from "../api/fraud";
import { fetchEscrow } from "../api/ledger";
import { apiErrorMessage } from "../lib/api";

/**
 * What the runner actually paid, reported at the counter.
 *
 * Deliberately shown BEFORE delivery: the runner finds out here that something
 * will be held back, rather than discovering a smaller number in their wallet
 * hours later with no explanation attached to it.
 */
export default function PriceClaimPanel({ errandId }: { errandId: string }) {
  const [open, setOpen] = useState(false);
  const [lines, setLines] = useState<ClaimLine[]>([
    { name: "", unit_price: 0, quantity: 1 },
  ]);
  const [result, setResult] = useState<ClaimResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function update(i: number, patch: Partial<ClaimLine>) {
    setLines((prev) => prev.map((l, idx) => (idx === i ? { ...l, ...patch } : l)));
  }

  const filled = lines.filter((l) => l.name.trim() && l.unit_price > 0);
  const runningTotal = filled.reduce((sum, l) => sum + l.unit_price * l.quantity, 0);

  // The ceiling comes from the hold itself rather than being recomputed here:
  // it is the exact figure settlement measures against, and a client doing its
  // own arithmetic will eventually disagree with it.
  const { data: escrow } = useQuery({
    queryKey: ["escrow", errandId],
    queryFn: () => fetchEscrow(errandId),
    enabled: open,
  });
  const ceiling = escrow ? Number(escrow.amount) : null;
  const owed = runningTotal + (escrow ? Number(escrow.reward) : 0);
  const overCeiling = ceiling != null && owed > ceiling;

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      setResult(await submitClaims(errandId, filled));
    } catch (err) {
      setError(apiErrorMessage(err, "Could not submit prices."));
    } finally {
      setBusy(false);
    }
  }

  if (result) {
    const held = result.withheld > 0;
    return (
      <div
        className={`mt-3 rounded-xl border-2 p-4 ${
          held ? "border-amber-300 bg-amber-50" : "border-emerald-200 bg-emerald-50"
        }`}
      >
        <div className="flex items-center justify-between gap-3">
          <div className="text-sm font-extrabold text-ink">
            {held ? "⚠️ Part of this is on hold" : "✅ Prices recorded"}
          </div>
          <div className="text-sm font-bold text-ink">
            ₹{result.total_eligible.toFixed(0)} to be paid
          </div>
        </div>

        <ul className="mt-3 space-y-1.5 text-sm">
          {result.claims.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center justify-between gap-x-3">
              <span className="text-ink">
                {c.raw_name} × {c.quantity}
                {(c.verdict === "FLAGGED" || c.verdict === "ELEVATED") &&
                  c.reference_snapshot != null && (
                    <span className="ml-1 text-xs text-muted">
                      (campus reference ₹{Number(c.reference_snapshot).toFixed(0)})
                    </span>
                  )}
                {c.verdict === "NO_REFERENCE" && (
                  <span className="ml-1 text-xs text-muted">(not priced yet)</span>
                )}
              </span>
              <span
                className={`font-semibold ${
                  c.verdict === "FLAGGED"
                    ? "text-amber-700"
                    : c.verdict === "ELEVATED"
                      ? "text-ink"
                      : "text-emerald-700"
                }`}
              >
                ₹{(Number(c.claimed_unit_price) * c.quantity).toFixed(0)}
                {c.verdict === "FLAGGED" && (
                  <> → ₹{Number(c.eligible_amount).toFixed(0)}</>
                )}
              </span>
            </li>
          ))}
        </ul>

        {result.message && (
          <p className="mt-3 border-t border-amber-200 pt-3 text-xs text-amber-800">
            {result.message}
          </p>
        )}

        <button
          onClick={() => {
            setResult(null);
            setLines([{ name: "", unit_price: 0, quantity: 1 }]);
          }}
          className="mt-3 text-xs font-semibold text-brand hover:underline"
        >
          Correct these prices
        </button>
      </div>
    );
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="mt-3 rounded-xl border-2 border-dashed border-line px-4 py-2.5 text-sm font-bold text-muted transition hover:border-brand hover:text-brand"
      >
        🧾 Report what you paid
      </button>
    );
  }

  return (
    <div className="mt-3 rounded-xl border border-line bg-white p-4">
      <div className="text-xs font-bold uppercase tracking-wide text-muted">
        What you paid at the counter
      </div>
      <p className="mt-1 text-xs text-muted">
        Enter the real price per item. Claims well above the campus reference are held
        for review, so a receipt helps if a price was genuinely higher today.
      </p>

      <div className="mt-3 space-y-2">
        {lines.map((line, i) => (
          <div key={i} className="flex gap-2">
            <input
              value={line.name}
              onChange={(e) => update(i, { name: e.target.value })}
              placeholder="Item, e.g. Chicken Puff"
              className="min-w-0 flex-1 rounded-lg border border-line px-3 py-2 text-sm outline-none focus:border-brand"
            />
            <input
              type="number"
              min={0}
              value={line.unit_price || ""}
              onChange={(e) => update(i, { unit_price: Number(e.target.value) })}
              placeholder="₹ each"
              className="w-24 rounded-lg border border-line px-3 py-2 text-sm outline-none focus:border-brand"
            />
            <input
              type="number"
              min={1}
              value={line.quantity}
              onChange={(e) => update(i, { quantity: Math.max(1, Number(e.target.value)) })}
              className="w-16 rounded-lg border border-line px-3 py-2 text-sm outline-none focus:border-brand"
            />
            {lines.length > 1 && (
              <button
                onClick={() => setLines((p) => p.filter((_, idx) => idx !== i))}
                className="shrink-0 px-1 text-muted transition hover:text-red-600"
                title="Remove line"
              >
                ✕
              </button>
            )}
          </div>
        ))}
      </div>

      <button
        onClick={() => setLines((p) => [...p, { name: "", unit_price: 0, quantity: 1 }])}
        className="mt-2 text-xs font-semibold text-brand hover:underline"
      >
        + Add another item
      </button>

      {error && (
        <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          {error}
        </div>
      )}

      {overCeiling && (
        <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2">
          <p className="text-xs font-bold text-red-700">
            ₹{owed.toFixed(0)} is more than the ₹{ceiling!.toFixed(0)} held for this
            errand.
          </p>
          <p className="mt-1 text-xs text-red-700">
            Report it anyway if it is what you really paid — but nothing is paid out
            on delivery. An admin reviews the difference first.
          </p>
        </div>
      )}

      <div className="mt-4 flex items-center justify-between gap-3">
        <span className="text-sm font-bold text-ink">
          Total ₹{runningTotal.toFixed(0)}
        </span>
        <div className="flex gap-2">
          <button
            onClick={() => setOpen(false)}
            className="rounded-xl border border-line px-4 py-2 text-sm font-semibold text-muted transition hover:border-brand hover:text-brand"
          >
            Cancel
          </button>
          <button
            onClick={submit}
            disabled={busy || filled.length === 0}
            className="rounded-xl bg-brand px-5 py-2 text-sm font-bold text-white transition hover:bg-brand-dark disabled:opacity-50"
          >
            {busy ? "…" : "Submit prices"}
          </button>
        </div>
      </div>
    </div>
  );
}
