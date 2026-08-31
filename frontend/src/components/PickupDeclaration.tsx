import { useState } from "react";

import type { Errand } from "../api/errands";

interface Props {
  errand: Errand;
  busy: boolean;
  onConfirm: (amountSpent: number) => void;
}

/** What the order was expected to cost — the sensible starting figure. */
function expectedSpend(e: Errand): number {
  return Number(e.collect_amount || 0) + Number(e.items_total || 0);
}

/**
 * The runner states what they actually paid, as they mark the errand picked up.
 *
 * Escrow reimburses this number, so it cannot be skipped. On a run with
 * nothing to buy there is nothing to state, and the step collapses back to a
 * plain button rather than asking a parcel courier how much the parcel cost.
 */
export default function PickupDeclaration({ errand, busy, onConfirm }: Props) {
  const expected = expectedSpend(errand);
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState(String(expected || ""));

  if (expected <= 0) {
    return (
      <button
        onClick={() => onConfirm(0)}
        disabled={busy}
        className="rounded-xl bg-brand px-4 py-2 text-sm font-bold text-white transition hover:bg-brand-dark disabled:opacity-60"
      >
        Picked up 📦
      </button>
    );
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="rounded-xl bg-brand px-4 py-2 text-sm font-bold text-white transition hover:bg-brand-dark"
      >
        Picked up 📦
      </button>
    );
  }

  const spent = Number(value);
  // An empty box is not zero. Requiring a real entry is the whole point:
  // a blank that silently submits the estimate would defeat asking at all.
  const valid = value.trim() !== "" && Number.isFinite(spent) && spent >= 0;
  const over = valid && spent > expected;

  return (
    <div className="w-full rounded-xl border border-brand/40 bg-brand-soft p-3">
      <label htmlFor={`spent-${errand.id}`} className="block text-sm font-bold">
        What did you actually pay?
      </label>
      <p className="mt-0.5 text-xs text-muted">
        Estimated ₹{expected.toFixed(0)}. Enter the real amount from the counter —
        this is what you get reimbursed, on top of your ₹
        {Number(errand.reward).toFixed(0)} reward.
      </p>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1">
          <span className="text-lg font-bold">₹</span>
          <input
            id={`spent-${errand.id}`}
            type="number"
            min={0}
            step={1}
            autoFocus
            value={value}
            onChange={(e) => setValue(e.target.value)}
            className="w-28 rounded-lg border border-line px-3 py-2 font-semibold outline-none focus:border-brand focus:ring-2 focus:ring-brand/20"
          />
        </div>
        <button
          onClick={() => onConfirm(spent)}
          disabled={!valid || busy}
          className="rounded-xl bg-brand px-4 py-2 text-sm font-bold text-white transition hover:bg-brand-dark disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy ? "Saving…" : "Confirm pickup 📦"}
        </button>
        <button
          onClick={() => setOpen(false)}
          className="px-2 text-sm font-semibold text-muted hover:text-ink"
        >
          Cancel
        </button>
      </div>

      {over && (
        <p className="mt-2 text-xs font-semibold text-amber-700">
          ₹{(spent - expected).toFixed(0)} over the estimate. Covered by the headroom
          held on this order, as long as it is within it.
        </p>
      )}
    </div>
  );
}
