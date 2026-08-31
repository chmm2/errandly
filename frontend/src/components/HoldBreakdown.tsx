import { useQuery } from "@tanstack/react-query";

import { fetchWallet, quoteHold } from "../api/ledger";

interface Props {
  /** Estimated cost of the items themselves. */
  spend: number;
  /** The runner's fee. Shown, but never padded. */
  fee: number;
}

/**
 * What placing this order will actually take out of the wallet.
 *
 * Escrow holds the estimate plus headroom, so a screen that totals items and
 * fee alone quotes a number the wallet then disagrees with - the requester
 * sees more money vanish than the button promised. This names the headroom,
 * says plainly that it comes back, and warns before the order fails when the
 * available partition cannot cover it.
 */
export default function HoldBreakdown({ spend, fee }: Props) {
  const { data: wallet } = useQuery({ queryKey: ["wallet"], queryFn: fetchWallet });

  // Until the wallet answers, assume no headroom rather than inventing one:
  // quoting 15% the server might not apply is its own kind of wrong.
  const pct = wallet?.buffer_pct ?? 0;
  const q = quoteHold(spend, fee, pct);
  if (q.total <= 0) return null;

  const available = wallet?.balance;
  const short = available !== undefined && available < q.total;

  return (
    <div className="rounded-xl border border-line bg-neutral-50 p-3 text-sm">
      <div className="flex justify-between py-0.5">
        <span className="text-muted">Items (estimated)</span>
        <span className="font-medium">₹{q.spend.toFixed(0)}</span>
      </div>

      {q.buffer > 0 && (
        <div className="flex justify-between py-0.5">
          <span className="text-muted">
            Price headroom ({Math.round(pct * 100)}%)
          </span>
          <span className="font-medium">+₹{q.buffer.toFixed(0)}</span>
        </div>
      )}

      <div className="flex justify-between py-0.5">
        <span className="text-muted">Runner reward</span>
        <span className="font-medium">+₹{q.fee.toFixed(0)}</span>
      </div>

      <div className="mt-2 flex justify-between border-t border-line pt-2">
        <span className="font-semibold">Locked from your wallet</span>
        <span className="text-base font-extrabold">₹{q.total.toFixed(0)}</span>
      </div>

      {q.buffer > 0 && (
        <p className="mt-2 text-xs text-muted">
          The headroom covers the price being higher at the counter than we
          estimated. Whatever the runner does not spend comes back to you the
          moment the order completes.
        </p>
      )}

      {short && (
        <p className="mt-2 text-xs font-semibold text-red-600">
          Only ₹{available!.toFixed(0)} available — add ₹
          {(q.total - available!).toFixed(0)} to place this order.
          {(wallet?.held ?? 0) > 0 &&
            ` (₹${wallet!.held.toFixed(0)} is held on your live orders.)`}
        </p>
      )}
    </div>
  );
}
