import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  type LedgerEntry,
  fetchWallet,
  topupWallet,
  verifyLedger,
} from "../api/ledger";
import Navbar from "../components/Navbar";
import { useAuth } from "../stores/auth";

const TOPUP_PRESETS = [100, 200, 500];

// How each ledger entry reads in the history list.
const ENTRY_META: Record<string, { label: string; icon: string }> = {
  TOPUP: { label: "Added money", icon: "➕" },
  HOLD: { label: "Held for order", icon: "🔒" },
  REWARD: { label: "Delivery earning", icon: "🛵" },
  REIMBURSEMENT: { label: "Reimbursed", icon: "🧾" },
  REFUND: { label: "Refund", icon: "💸" },
  CONVENIENCE_FEE: { label: "Convenience fee", icon: "⚙️" },
  ESCROW: { label: "Escrow", icon: "🔐" },
};

function HistoryRow({ entry }: { entry: LedgerEntry }) {
  const meta = ENTRY_META[entry.entry_type] ?? { label: entry.entry_type, icon: "•" };
  const credit = entry.amount >= 0;
  return (
    <div className="flex items-center gap-4 rounded-2xl border border-line p-4">
      <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-brand-soft text-xl">
        {meta.icon}
      </div>
      <div className="min-w-0 flex-1">
        <div className="truncate font-bold">{meta.label}</div>
        <div className="mt-0.5 text-sm text-muted">
          {new Date(entry.created_at).toLocaleString(undefined, {
            day: "numeric",
            month: "short",
            hour: "2-digit",
            minute: "2-digit",
          })}
        </div>
      </div>
      <span className={`shrink-0 font-extrabold ${credit ? "text-green-600" : "text-muted"}`}>
        {credit ? "+" : "−"}₹{Math.abs(entry.amount).toFixed(0)}
      </span>
    </div>
  );
}

const STATIC_BADGE = (
  <span className="inline-flex items-center gap-1.5 rounded-full bg-white/20 px-3 py-1 text-xs font-bold text-white">
    🔒 Tamper-evident ledger
  </span>
);

function VerifyBadge() {
  // The live integrity check is an admin auditor tool (/ledger/verify is
  // admin-only). Everyone else sees the static assurance.
  const isAdmin = useAuth((s) => s.user?.role) === "ADMIN";
  const { data, isError } = useQuery({
    queryKey: ["ledger-verify"],
    queryFn: verifyLedger,
    enabled: isAdmin,
  });
  if (!isAdmin || isError || !data) return STATIC_BADGE;

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold ${
        data.intact ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
      }`}
      title={
        data.intact
          ? `All ${data.entries} entries verified against the hash chain`
          : `Chain broken at entry #${data.broken_seq}: ${data.reason}`
      }
    >
      {data.intact
        ? `🔒 Ledger verified · ${data.entries} entries`
        : `⚠️ Tampering at #${data.broken_seq}`}
    </span>
  );
}

export default function Wallet() {
  const queryClient = useQueryClient();
  const [custom, setCustom] = useState("");

  const { data: wallet } = useQuery({ queryKey: ["wallet"], queryFn: fetchWallet });

  const topup = useMutation({
    mutationFn: (amount: number) => topupWallet(amount),
    onSuccess: () => {
      setCustom("");
      queryClient.invalidateQueries({ queryKey: ["wallet"] });
      queryClient.invalidateQueries({ queryKey: ["earnings"] });
      queryClient.invalidateQueries({ queryKey: ["ledger-verify"] });
    },
  });

  const customAmount = Number(custom);
  const customValid = customAmount > 0 && customAmount <= 100000;

  return (
    <div className="min-h-screen bg-white">
      <Navbar />

      {/* Balance header */}
      <section className="bg-gradient-to-br from-brand to-brand-dark text-white">
        <div className="mx-auto max-w-3xl px-4 py-10">
          <div className="flex items-center justify-between">
            <p className="text-white/80">Wallet balance</p>
            <VerifyBadge />
          </div>
          <p className="mt-1 text-5xl font-extrabold">
            ₹{(wallet?.balance ?? 0).toFixed(2)}
          </p>
          <p className="mt-2 text-sm text-white/70">
            Money you post for an order is held safely in escrow and only released once you confirm
            delivery.
          </p>
        </div>
      </section>

      <div className="mx-auto max-w-3xl space-y-10 px-4 py-10">
        {/* Add money */}
        <section>
          <h2 className="text-xl font-extrabold">Add money</h2>
          <p className="mt-1 text-sm text-muted">
            Demo top-up — credited instantly, no real payment.
          </p>
          <div className="mt-4 flex flex-wrap gap-3">
            {TOPUP_PRESETS.map((amt) => (
              <button
                key={amt}
                onClick={() => topup.mutate(amt)}
                disabled={topup.isPending}
                className="rounded-xl bg-brand px-6 py-3 font-bold text-white transition hover:bg-brand-dark disabled:opacity-50"
              >
                +₹{amt}
              </button>
            ))}
            <div className="flex items-center gap-2">
              <input
                type="number"
                min={1}
                value={custom}
                onChange={(e) => setCustom(e.target.value)}
                placeholder="Custom ₹"
                className="w-28 rounded-xl border border-line px-3 py-3 focus:border-brand focus:outline-none"
              />
              <button
                onClick={() => topup.mutate(customAmount)}
                disabled={!customValid || topup.isPending}
                className="rounded-xl border border-brand px-5 py-3 font-bold text-brand transition hover:bg-brand-soft disabled:opacity-40"
              >
                Add
              </button>
            </div>
          </div>
        </section>

        {/* History */}
        <section>
          <h2 className="text-xl font-extrabold">Transactions</h2>
          {(wallet?.entries.length ?? 0) === 0 ? (
            <div className="mt-3 rounded-2xl border-2 border-dashed border-line p-10 text-center text-muted">
              No transactions yet — add money to get started.
            </div>
          ) : (
            <div className="mt-3 space-y-3">
              {wallet!.entries.map((e) => (
                <HistoryRow key={e.seq} entry={e} />
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
