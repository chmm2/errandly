import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { fetchStanding, STRIKE_LABELS } from "../api/fraud";
import { ENTRY_LABELS, fetchWallet, type LedgerEntry, topUp } from "../api/ledger";
import Navbar from "../components/Navbar";
import { apiErrorMessage } from "../lib/api";

const TOP_UP_PRESETS = [100, 250, 500];

function entryTone(entry: LedgerEntry): string {
  if (entry.direction === "DEBIT") return "text-muted";
  return "text-emerald-700";
}

function formatWhen(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function Wallet() {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const { data: wallet, isLoading } = useQuery({
    queryKey: ["wallet"],
    queryFn: fetchWallet,
  });
  const { data: standing } = useQuery({ queryKey: ["standing"], queryFn: fetchStanding });

  const add = useMutation({
    mutationFn: topUp,
    onSuccess: () => {
      setError(null);
      qc.invalidateQueries({ queryKey: ["wallet"] });
    },
    onError: (err) => setError(apiErrorMessage(err, "Top-up failed.")),
  });

  const activeStrike = standing?.strikes.find((s) => !s.lifted_at);
  const blocked = standing?.blocked_until && new Date(standing.blocked_until) > new Date();

  return (
    <div className="min-h-screen bg-white">
      <Navbar />

      <section className="bg-gradient-to-br from-ink to-[#3d4152] text-white">
        <div className="mx-auto max-w-4xl px-4 py-10">
          <h1 className="text-3xl font-extrabold sm:text-4xl">Wallet</h1>
          <p className="mt-2 max-w-lg text-white/85">
            Orders are paid from here. Money moves into escrow when you place an order and
            reaches the runner only once it is delivered.
          </p>

          <div className="mt-6 flex flex-wrap gap-4">
            <div className="rounded-2xl bg-white/10 px-6 py-4 backdrop-blur-sm">
              <div className="text-3xl font-extrabold">
                ₹{(wallet?.balance ?? 0).toFixed(0)}
              </div>
              <div className="text-xs text-white/80">available to spend</div>
            </div>
            {(wallet?.held ?? 0) > 0 && (
              <div className="rounded-2xl bg-white/10 px-6 py-4 backdrop-blur-sm">
                <div className="text-3xl font-extrabold">₹{wallet!.held.toFixed(0)}</div>
                <div className="text-xs text-white/80">held on live orders</div>
              </div>
            )}
          </div>
        </div>
      </section>

      <div className="mx-auto max-w-4xl px-4 py-8">
        {error && (
          <div className="mb-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* Fraud standing — only shown when there is something to say. */}
        {standing && standing.flags_in_window > 0 && (
          <section
            className={`mb-8 rounded-2xl border-2 p-5 ${
              blocked ? "border-red-300 bg-red-50" : "border-amber-300 bg-amber-50"
            }`}
          >
            <h2 className="font-extrabold text-ink">
              {blocked ? "Running is paused" : "Price reports under review"}
            </h2>
            <p className="mt-1 text-sm text-ink/80">
              {standing.flags_in_window} of your reported prices came in above the campus
              reference in the last 30 days.
              {standing.next_action_at != null && !blocked && (
                <>
                  {" "}
                  At {standing.next_action_at} the next restriction applies — report the
                  real amount you paid and this clears on its own.
                </>
              )}
            </p>
            {activeStrike && (
              <p className="mt-2 text-sm font-semibold text-ink">
                Current: {STRIKE_LABELS[activeStrike.action]} — {activeStrike.reason}
              </p>
            )}
            {blocked && (
              <p className="mt-2 text-sm font-semibold text-red-700">
                You can take runs again after{" "}
                {formatWhen(standing.blocked_until!)}. If you believe this is wrong, ask an
                admin to review your flags.
              </p>
            )}
          </section>
        )}

        {/* Demo top-up. The backend 404s this outside development. */}
        <section className="mb-8 rounded-2xl border border-line p-5">
          <h2 className="font-extrabold">Add money</h2>
          <p className="mt-1 text-sm text-muted">
            KARMA credit for the campus pilot — UPI lands later.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {TOP_UP_PRESETS.map((amount) => (
              <button
                key={amount}
                onClick={() => add.mutate(amount)}
                disabled={add.isPending}
                className="rounded-xl border-2 border-line px-5 py-2.5 font-bold transition hover:border-brand hover:text-brand disabled:opacity-50"
              >
                +₹{amount}
              </button>
            ))}
          </div>
        </section>

        <section>
          <h2 className="text-xl font-extrabold">Activity</h2>
          {isLoading ? (
            <p className="mt-3 text-sm text-muted">Loading…</p>
          ) : (wallet?.recent ?? []).length === 0 ? (
            <div className="mt-4 rounded-2xl border-2 border-dashed border-line p-10 text-center">
              <div className="text-4xl">🧾</div>
              <p className="mt-3 font-semibold">Nothing here yet</p>
              <p className="text-sm text-muted">
                Add money, then{" "}
                <Link to="/errands/new" className="font-semibold text-brand hover:underline">
                  post an errand
                </Link>
                .
              </p>
            </div>
          ) : (
            <ul className="mt-3 divide-y divide-line rounded-2xl border border-line">
              {wallet!.recent.map((entry) => (
                <li
                  key={entry.id}
                  className="flex items-center justify-between gap-4 px-5 py-3.5"
                >
                  <div className="min-w-0">
                    <div className="truncate font-semibold text-ink">
                      {ENTRY_LABELS[entry.entry_type] ?? entry.entry_type}
                    </div>
                    <div className="truncate text-xs text-muted">
                      {entry.memo ? `${entry.memo} · ` : ""}
                      {formatWhen(entry.created_at)}
                    </div>
                  </div>
                  <div className={`shrink-0 font-extrabold ${entryTone(entry)}`}>
                    {entry.direction === "DEBIT" ? "−" : "+"}₹
                    {Number(entry.amount).toFixed(0)}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
