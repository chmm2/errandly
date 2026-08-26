import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  approveProposal,
  createReference,
  fetchFlags,
  fetchProposals,
  decideAlias,
  fetchAliases,
  fetchReferences,
  type ItemAlias,
  sweepAliases,
  sweepCollusion,
  type Flag,
  type Proposal,
  type ReferencePrice,
  refreshReferences,
  rejectProposal,
  reviewFlag,
} from "../api/fraud";
import Navbar from "../components/Navbar";
import { apiErrorMessage } from "../lib/api";

type Tab = "flags" | "proposals" | "prices" | "aliases";

const BLANK = {
  display_name: "",
  reference_price: 0,
  band_min: 0,
  band_max: 0,
  tolerance_abs: 20,
};

function FlagCard({
  flag,
  onReview,
  busy,
}: {
  flag: Flag;
  onReview: (uphold: boolean) => void;
  busy: boolean;
}) {
  const d = flag.details ?? {};
  const nearLine = flag.rule === "PERSISTENT_NEAR_THRESHOLD";
  const ring = flag.rule === "COLLUSION_RING";
  return (
    <div className="rounded-2xl border border-line p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="font-extrabold text-ink">
            {ring
              ? `Money circulating in a group of ${d.size ?? "?"}`
              : nearLine
                ? "Consistently just under the line"
                : (d.item ?? flag.rule)}
          </div>
          {ring ? (
            /* The finding is about a group, so name the group. Every member
               carries an identical flag — the graph shows no ringleader, and
               picking one would be inventing a fact. */
            <div className="mt-1 text-sm text-muted">
              <span className="font-bold text-ink">{(d.names ?? []).join(" → ")}</span>
              {" → "}
              <span className="font-bold text-ink">{(d.names ?? [])[0]}</span>
              <div className="mt-1">
                ₹{Number(d.total_value ?? 0).toFixed(0)} went round this circle{" "}
                <span className="font-bold text-ink">{d.laps}×</span>, smallest leg ₹
                {Number(d.min_leg_value ?? 0).toFixed(0)}. They are mutual friends and{" "}
                {Math.round(Number(d.closure ?? 0) * 100)}% of their friendships stay
                inside the group.
              </div>
            </div>
          ) : nearLine ? (
            /* No single claim broke a rule here — the evidence is the shape of
               the distribution, so show that rather than one price. */
            <div className="mt-1 text-sm text-muted">
              <span className="font-bold text-ink">{d.near_line_claims}</span> of{" "}
              <span className="font-bold text-ink">{d.judged_claims}</span> priced claims
              landed near the flag threshold over {d.window_days} days — averaging{" "}
              <span className="font-bold text-amber-700">
                ₹{Number(d.avg_rupees_over ?? 0).toFixed(0)}
              </span>{" "}
              over the reference each time. Nothing was withheld.
            </div>
          ) : (
            <div className="mt-1 text-sm text-muted">
              Claimed{" "}
              <span className="font-bold text-amber-700">
                ₹{Number(d.claimed ?? 0).toFixed(0)}
              </span>{" "}
              against a reference of{" "}
              <span className="font-bold text-ink">₹{Number(d.reference ?? 0).toFixed(0)}</span>
              {d.delta_pct != null && (
                <>
                  {" "}
                  · <span className="font-bold">+{Number(d.delta_pct).toFixed(0)}%</span>
                </>
              )}
            </div>
          )}
        </div>
        <span
          className={`rounded-full px-2.5 py-1 text-xs font-bold ${
            flag.severity >= 3
              ? "bg-red-100 text-red-700"
              : flag.severity === 2
                ? "bg-amber-100 text-amber-800"
                : "bg-brand-soft text-brand-dark"
          }`}
        >
          severity {flag.severity}
        </span>
      </div>

      {ring && d.semantic && (
        /* Advisory. Rendered so an admin can weigh it, and labelled so nobody
           mistakes it for a verdict - it can support clearing a group, never
           condemn one. */
        <div
          className={`mt-3 rounded-xl border p-3 ${
            d.semantic.exculpatory
              ? "border-emerald-200 bg-emerald-50"
              : "border-line bg-brand-soft/40"
          }`}
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs font-bold uppercase tracking-wide text-muted">
              What their errands say &middot; advisory
            </span>
            <span className="text-xs font-semibold text-ink">
              coherence {d.semantic.coherence.toFixed(2)} &middot; across{" "}
              {d.semantic.errands_considered} errands
            </span>
          </div>
          <p className="mt-1.5 text-sm font-semibold text-ink">
            {d.semantic.exculpatory
              ? "Reads like genuine, varied campus life."
              : d.semantic.reads_as_genuine
                ? "Reads as genuine, but not strongly enough to count in their favour."
                : "Does not read as varied campus life."}
          </p>
          {d.semantic.observations.length > 0 && (
            <ul className="mt-1.5 list-disc space-y-0.5 pl-4 text-xs text-muted">
              {d.semantic.observations.map((o, i) => (
                <li key={i}>{o}</li>
              ))}
            </ul>
          )}
          <p className="mt-2 text-xs text-muted">
            A low reading is never evidence of fraud on its own &mdash; people
            write tersely for many reasons. Weigh it only alongside the money.
          </p>
        </div>
      )}
      {ring && d.semantic === null && (
        <p className="mt-3 text-xs text-muted">
          No language reading for this group &mdash; either no model is
          configured, or they share too little history to judge.
        </p>
      )}

      <p className="mt-3 text-xs text-muted">
        {ring
          ? "No money is held. A cycle is strong evidence about a group but names no single dishonest errand, and these payouts settled long ago. Upholding keeps the group discounted in matching; dismissing clears every member."
          : nearLine
            ? "No money is held on this one. Dismissing restores the runner's claims as evidence for reference prices; upholding keeps them excluded."
            : "Dismissing pays the runner the withheld amount and lets this claim count as evidence again. Upholding returns it to the requester."}
      </p>

      <div className="mt-3 flex gap-2">
        <button
          onClick={() => onReview(false)}
          disabled={busy}
          className="rounded-xl border-2 border-emerald-300 px-4 py-2 text-sm font-bold text-emerald-700 transition hover:bg-emerald-50 disabled:opacity-50"
        >
          {ring
            ? "Dismiss — genuine friends"
            : nearLine
              ? "Dismiss — normal variation"
              : "Dismiss — runner was honest"}
        </button>
        <button
          onClick={() => onReview(true)}
          disabled={busy}
          className="rounded-xl border-2 border-red-300 px-4 py-2 text-sm font-bold text-red-700 transition hover:bg-red-50 disabled:opacity-50"
        >
          {ring
            ? "Uphold — collusion ring"
            : nearLine
              ? "Uphold — gaming the threshold"
              : "Uphold — overcharge"}
        </button>
      </div>
    </div>
  );
}

function ProposalCard({
  proposal,
  reference,
  onApprove,
  onReject,
  busy,
}: {
  proposal: Proposal;
  reference?: ReferencePrice;
  onApprove: () => void;
  onReject: () => void;
  busy: boolean;
}) {
  return (
    <div className="rounded-2xl border border-line p-5">
      <div className="font-extrabold text-ink">
        {reference?.display_name ?? "Item"}
      </div>
      <div className="mt-1 text-sm text-muted">
        Runners are consistently paying{" "}
        <span className="font-bold text-ink">
          ₹{Number(proposal.observed_median).toFixed(0)}
        </span>{" "}
        — across {proposal.sample_count} claims.
        {reference && (
          <>
            {" "}
            Current band is ₹{Number(reference.band_min).toFixed(0)}–₹
            {Number(reference.band_max).toFixed(0)}.
          </>
        )}
      </div>
      <p className="mt-2 rounded-lg bg-brand-soft px-3 py-2 text-xs text-brand-dark">
        {proposal.reason}
      </p>
      <div className="mt-3 text-sm">
        Proposed: reference{" "}
        <span className="font-bold">₹{Number(proposal.proposed_price).toFixed(0)}</span>, band
        ₹{Number(proposal.proposed_band_min).toFixed(0)}–₹
        {Number(proposal.proposed_band_max).toFixed(0)}
      </div>
      <div className="mt-3 flex gap-2">
        <button
          onClick={onApprove}
          disabled={busy}
          className="rounded-xl bg-brand px-4 py-2 text-sm font-bold text-white transition hover:bg-brand-dark disabled:opacity-50"
        >
          Approve
        </button>
        <button
          onClick={onReject}
          disabled={busy}
          className="rounded-xl border border-line px-4 py-2 text-sm font-semibold text-muted transition hover:border-brand hover:text-brand disabled:opacity-50"
        >
          Reject
        </button>
      </div>
    </div>
  );
}

export default function FraudAdmin() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("flags");
  const [draft, setDraft] = useState({ ...BLANK });
  const [error, setError] = useState<string | null>(null);

  const { data: flags } = useQuery({ queryKey: ["flags"], queryFn: () => fetchFlags("OPEN") });
  const { data: proposals } = useQuery({
    queryKey: ["proposals"],
    queryFn: () => fetchProposals("PENDING"),
  });
  const { data: aliases } = useQuery({
    queryKey: ["aliases"],
    queryFn: () => fetchAliases("PENDING"),
  });
  const { data: references } = useQuery({
    queryKey: ["references"],
    queryFn: fetchReferences,
  });

  function invalidate() {
    setError(null);
    qc.invalidateQueries({ queryKey: ["flags"] });
    qc.invalidateQueries({ queryKey: ["proposals"] });
    qc.invalidateQueries({ queryKey: ["references"] });
    qc.invalidateQueries({ queryKey: ["aliases"] });
  }
  const fail = (fallback: string) => (err: unknown) =>
    setError(apiErrorMessage(err, fallback));

  const review = useMutation({
    mutationFn: ({ id, uphold }: { id: string; uphold: boolean }) => reviewFlag(id, uphold),
    onSuccess: invalidate,
    onError: fail("Could not review that flag."),
  });
  const approve = useMutation({
    mutationFn: approveProposal,
    onSuccess: invalidate,
    onError: fail("Could not approve."),
  });
  const reject = useMutation({
    mutationFn: rejectProposal,
    onSuccess: invalidate,
    onError: fail("Could not reject."),
  });
  const create = useMutation({
    mutationFn: createReference,
    onSuccess: () => {
      setDraft({ ...BLANK });
      invalidate();
    },
    onError: fail("Could not add that price."),
  });
  const sweep = useMutation({
    mutationFn: sweepCollusion,
    onSuccess: invalidate,
    onError: fail("Collusion sweep failed."),
  });
  const aliasSweep = useMutation({
    mutationFn: sweepAliases,
    onSuccess: invalidate,
    onError: fail("Alias sweep failed."),
  });
  const alias = useMutation({
    mutationFn: ({ id, approve }: { id: string; approve: boolean }) =>
      decideAlias(id, approve),
    onSuccess: invalidate,
    onError: fail("Could not decide that alias."),
  });
  const refresh = useMutation({
    mutationFn: refreshReferences,
    onSuccess: invalidate,
    onError: fail("Refresh failed."),
  });

  const refById = new Map((references ?? []).map((r) => [r.id, r]));
  const tabs: [Tab, string, number][] = [
    ["flags", "Flags", flags?.length ?? 0],
    ["proposals", "Price proposals", proposals?.length ?? 0],
    ["prices", "Reference prices", references?.length ?? 0],
    ["aliases", "Item names", aliases?.length ?? 0],
  ];

  return (
    <div className="min-h-screen bg-white">
      <Navbar />

      <section className="bg-gradient-to-br from-ink to-[#3d4152] text-white">
        <div className="mx-auto max-w-5xl px-4 py-10">
          <h1 className="text-3xl font-extrabold sm:text-4xl">Price integrity</h1>
          <p className="mt-2 max-w-2xl text-white/85">
            Runners are reimbursed for what they spend. For items with no printed price,
            these references are the only thing separating an honest claim from an invented
            one — so the platform never moves a band without you.
          </p>
        </div>
      </section>

      <div className="mx-auto max-w-5xl px-4 py-8">
        <div className="flex flex-wrap gap-2 border-b border-line pb-3">
          {tabs.map(([key, label, count]) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`rounded-xl px-4 py-2 text-sm font-bold transition ${
                tab === key
                  ? "bg-brand text-white"
                  : "text-muted hover:bg-brand-soft hover:text-brand-dark"
              }`}
            >
              {label}
              {count > 0 && <span className="ml-1.5 opacity-70">{count}</span>}
            </button>
          ))}
        </div>

        {error && (
          <div className="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {tab === "flags" && (
          <section className="mt-6 space-y-3">
            <div className="flex justify-end">
              <button
                onClick={() => sweep.mutate()}
                disabled={sweep.isPending}
                className="rounded-xl border border-line px-4 py-2 text-sm font-semibold text-muted transition hover:border-brand hover:text-brand disabled:opacity-50"
              >
                {sweep.isPending ? "…" : "🔗 Scan for collusion rings"}
              </button>
            </div>
            {(flags ?? []).length === 0 ? (
              <div className="rounded-2xl border-2 border-dashed border-line p-10 text-center">
                <div className="text-4xl">✅</div>
                <p className="mt-3 font-semibold">No open flags</p>
                <p className="text-sm text-muted">
                  Every reported price is sitting within its campus reference.
                </p>
              </div>
            ) : (
              flags!.map((f) => (
                <FlagCard
                  key={f.id}
                  flag={f}
                  busy={review.isPending}
                  onReview={(uphold) => review.mutate({ id: f.id, uphold })}
                />
              ))
            )}
          </section>
        )}

        {tab === "proposals" && (
          <section className="mt-6 space-y-3">
            {(proposals ?? []).length === 0 ? (
              <div className="rounded-2xl border-2 border-dashed border-line p-10 text-center">
                <div className="text-4xl">📊</div>
                <p className="mt-3 font-semibold">Nothing to approve</p>
                <p className="text-sm text-muted">
                  Proposals appear here when the going rate drifts against an approved band.
                </p>
              </div>
            ) : (
              proposals!.map((p) => (
                <ProposalCard
                  key={p.id}
                  proposal={p}
                  reference={refById.get(p.reference_price_id)}
                  busy={approve.isPending || reject.isPending}
                  onApprove={() => approve.mutate(p.id)}
                  onReject={() => reject.mutate(p.id)}
                />
              ))
            )}
          </section>
        )}

        {tab === "aliases" && (
          <section className="mt-6">
            <div className="rounded-2xl border border-line p-5">
              <h2 className="font-extrabold">Names that might mean a priced item</h2>
              <p className="mt-1 text-sm text-muted">
                Spelling checks already catch typos. These are the ones spelling
                cannot reach &mdash; a different word for the same thing.
                Nothing here affects a price check until you approve it.
              </p>
              <button
                onClick={() => aliasSweep.mutate()}
                disabled={aliasSweep.isPending}
                className="mt-3 rounded-xl border border-line px-4 py-2 text-sm font-semibold text-muted transition hover:border-brand hover:text-brand disabled:opacity-50"
              >
                {aliasSweep.isPending ? "..." : "\u{1F524} Look for new name matches"}
              </button>
            </div>

            {(aliases ?? []).length === 0 ? (
              <div className="mt-4 rounded-2xl border-2 border-dashed border-line p-10 text-center">
                <p className="font-semibold">Nothing waiting</p>
                <p className="text-sm text-muted">
                  Suggestions appear when a reported item name matches nothing
                  you have priced.
                </p>
              </div>
            ) : (
              <div className="mt-3 space-y-3">
                {aliases!.map((a: ItemAlias) => (
                  <div key={a.id} className="rounded-2xl border border-line p-5">
                    <div className="flex flex-wrap items-center gap-2 text-sm">
                      <span className="rounded-lg bg-brand-soft px-2.5 py-1 font-bold text-brand-dark">
                        {a.sample_raw_name}
                      </span>
                      <span className="text-muted">is the same item as</span>
                      <span className="rounded-lg bg-brand-soft px-2.5 py-1 font-bold text-brand-dark">
                        {a.item_key}
                      </span>
                    </div>
                    {a.reason && <p className="mt-2 text-sm text-muted">{a.reason}</p>}
                    <p className="mt-2 text-xs text-muted">
                      Approving means future claims for that name are checked
                      against {a.item_key}. Reject anything that is a different
                      size or variant &mdash; those are priced separately.
                    </p>
                    <div className="mt-3 flex gap-2">
                      <button
                        onClick={() => alias.mutate({ id: a.id, approve: true })}
                        disabled={alias.isPending}
                        className="rounded-xl bg-brand px-4 py-2 text-sm font-bold text-white transition hover:bg-brand-dark disabled:opacity-50"
                      >
                        Same item
                      </button>
                      <button
                        onClick={() => alias.mutate({ id: a.id, approve: false })}
                        disabled={alias.isPending}
                        className="rounded-xl border border-line px-4 py-2 text-sm font-semibold text-muted transition hover:border-brand hover:text-brand disabled:opacity-50"
                      >
                        Different item
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        {tab === "prices" && (
          <section className="mt-6">
            <div className="rounded-2xl border border-line p-5">
              <h2 className="font-extrabold">Price a new item</h2>
              <p className="mt-1 text-sm text-muted">
                Until an item is priced here, nobody can be flagged for it. The band is a
                hard limit — automatic updates can move the reference inside it, never
                outside.
              </p>
              <div className="mt-3 grid gap-2 sm:grid-cols-6">
                <input
                  value={draft.display_name}
                  onChange={(e) => setDraft({ ...draft, display_name: e.target.value })}
                  placeholder="Chicken Puff"
                  className="rounded-lg border border-line px-3 py-2 text-sm outline-none focus:border-brand sm:col-span-2"
                />
                {(
                  [
                    ["reference_price", "₹ typical"],
                    ["band_min", "₹ min"],
                    ["band_max", "₹ max"],
                    ["tolerance_abs", "₹ flag over"],
                  ] as const
                ).map(([field, placeholder]) => (
                  <input
                    key={field}
                    type="number"
                    min={0}
                    value={draft[field] || ""}
                    onChange={(e) => setDraft({ ...draft, [field]: Number(e.target.value) })}
                    placeholder={placeholder}
                    className="rounded-lg border border-line px-3 py-2 text-sm outline-none focus:border-brand"
                  />
                ))}
              </div>
              <button
                onClick={() => create.mutate(draft)}
                disabled={create.isPending || !draft.display_name.trim()}
                className="mt-3 rounded-xl bg-brand px-5 py-2 text-sm font-bold text-white transition hover:bg-brand-dark disabled:opacity-50"
              >
                Add price
              </button>
            </div>

            <div className="mt-6 flex items-center justify-between">
              <h2 className="text-xl font-extrabold">Current references</h2>
              <button
                onClick={() => refresh.mutate()}
                disabled={refresh.isPending}
                className="rounded-xl border border-line px-4 py-2 text-sm font-semibold text-muted transition hover:border-brand hover:text-brand disabled:opacity-50"
              >
                {refresh.isPending ? "…" : "Re-estimate from claims"}
              </button>
            </div>

            {(references ?? []).length === 0 ? (
              <div className="mt-4 rounded-2xl border-2 border-dashed border-line p-10 text-center text-muted">
                No items priced yet.
              </div>
            ) : (
              <div className="mt-3 overflow-x-auto rounded-2xl border border-line">
                <table className="w-full text-sm">
                  <thead className="bg-brand-soft/60 text-left text-xs uppercase tracking-wide text-muted">
                    <tr>
                      <th className="px-4 py-2.5 font-bold">Item</th>
                      <th className="px-4 py-2.5 font-bold">Reference</th>
                      <th className="px-4 py-2.5 font-bold">Band</th>
                      <th className="px-4 py-2.5 font-bold">Flag over</th>
                      <th className="px-4 py-2.5 font-bold">Source</th>
                      <th className="px-4 py-2.5 font-bold">Samples</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {references!.map((r) => (
                      <tr key={r.id}>
                        <td className="px-4 py-3 font-semibold text-ink">{r.display_name}</td>
                        <td className="px-4 py-3 font-bold">
                          ₹{Number(r.reference_price).toFixed(0)}
                        </td>
                        <td className="px-4 py-3 text-muted">
                          ₹{Number(r.band_min).toFixed(0)}–₹{Number(r.band_max).toFixed(0)}
                        </td>
                        <td className="px-4 py-3 text-muted">
                          +₹{Number(r.tolerance_abs).toFixed(0)}
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`rounded-full px-2 py-0.5 text-xs font-bold ${
                              r.source === "ADMIN"
                                ? "bg-brand-soft text-brand-dark"
                                : "bg-slate-100 text-slate-600"
                            }`}
                          >
                            {r.source === "ADMIN" ? "you" : "auto"}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-muted">{r.sample_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}
      </div>
    </div>
  );
}
