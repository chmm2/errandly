import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import type { Errand } from "../api/errands";
import { fetchEscrow } from "../api/ledger";

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

  // The ceiling comes from the hold itself rather than being recomputed here.
  // It is the exact figure settlement measures against, and a client doing its
  // own arithmetic will eventually disagree with it.
  const { data: escrow } = useQuery({
    queryKey: ["escrow", errand.id],
    queryFn: () => fetchEscrow(errand.id),
    enabled: open,
  });

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

  // Past the hold nobody gets paid on delivery: the requester never committed
  // that much, so it goes to an admin instead.
  const ceiling = escrow ? Number(escrow.amount) : null;
  const owed = spent + Number(errand.reward || 0);
  const pastCeiling = valid && ceiling != null && owed > ceiling;

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

      {pastCeiling ? (
        <div className="mt-2 rounded-lg border border-red-200 bg-red-50 p-3">
          <p className="text-xs font-bold text-red-700">
            More than the ₹{ceiling!.toFixed(0)} held for this order.
          </p>
          <p className="mt-1 text-xs text-red-700">
            Paying you ₹{owed.toFixed(0)} would charge your requester more than they
            agreed to lock, so nothing is paid out on delivery — an admin reviews it
            first. Report it anyway if it is what you really paid.
          </p>
        </div>
      ) : (
        over && (
          <p className="mt-2 text-xs font-semibold text-amber-700">
            ₹{(spent - expected).toFixed(0)} over the estimate. Covered by the headroom
            held on this order.
          </p>
        )
      )}
    </div>
  );
}
