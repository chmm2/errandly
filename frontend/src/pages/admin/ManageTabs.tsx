import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  approveProposal,
  createReference,
  decideAlias,
  fetchAliases,
  fetchProposals,
  fetchReferences,
  refreshReferences,
  rejectProposal,
  sweepAliases,
} from "../../api/fraud";
import { apiErrorMessage } from "../../lib/api";
import { Icon, rupees, shortDate } from "./ui";

/* The three price-list tabs. Same behaviour as before the revamp, restyled to
   match the flags tab. */

const BLANK = { display_name: "", reference_price: 0, band_min: 0, band_max: 0, tolerance_abs: 20 };

function useInvalidate() {
  const qc = useQueryClient();
  return () => {
    for (const key of ["proposals", "references", "aliases", "flags", "overview"]) {
      qc.invalidateQueries({ queryKey: [key] });
    }
  };
}

function Empty({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-[22px] border-2 border-dashed border-ad-outline bg-white p-10 text-center">
      <p className="font-extrabold text-ad-ink">{title}</p>
      <p className="mt-1 text-sm text-ad-muted">{body}</p>
    </div>
  );
}

function ErrorLine({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <div className="mb-3 rounded-2xl border border-ad-caution-border bg-ad-caution-bg px-4 py-3 text-sm text-ad-caution">
      {error}
    </div>
  );
}

const btnPrimary =
  "rounded-2xl bg-ad-brand px-4 py-2.5 text-sm font-bold text-white shadow-[0_10px_16px_rgba(39,74,76,0.3)] transition hover:bg-ad-deep disabled:opacity-50";
const btnQuiet =
  "rounded-2xl border border-ad-outline bg-white px-4 py-2.5 text-sm font-bold text-ad-ink-soft transition hover:border-ad-brand hover:text-ad-brand disabled:opacity-50";

export function ProposalsTab() {
  const invalidate = useInvalidate();
  const [error, setError] = useState<string | null>(null);
  const { data: proposals } = useQuery({ queryKey: ["proposals"], queryFn: () => fetchProposals("PENDING") });
  const { data: references } = useQuery({ queryKey: ["references"], queryFn: fetchReferences });
  const refById = new Map((references ?? []).map((r) => [r.id, r]));
  const done = { onSuccess: () => { setError(null); invalidate(); } };
  const approve = useMutation({ mutationFn: approveProposal, ...done, onError: (e) => setError(apiErrorMessage(e, "Could not approve.")) });
  const reject = useMutation({ mutationFn: rejectProposal, ...done, onError: (e) => setError(apiErrorMessage(e, "Could not reject.")) });

  if (!proposals?.length)
    return <Empty title="Nothing to approve" body="When students keep paying a different price than the usual one, a suggested change appears here." />;

  return (
    <div className="space-y-3">
      <ErrorLine error={error} />
      {proposals.map((p) => {
        const ref = refById.get(p.reference_price_id);
        return (
          <div key={p.id} className="rounded-[22px] border border-ad-line bg-white p-5">
            <div className="text-lg font-extrabold text-ad-ink">{ref?.display_name ?? "Item"}</div>
            <p className="mt-1 text-sm text-ad-ink-soft">
              Runners keep paying about <b className="text-ad-ink">{rupees(p.observed_median)}</b>, across {p.sample_count} reports.
              {ref && <> The usual price is {rupees(ref.reference_price)}, allowed between {rupees(ref.band_min)} and {rupees(ref.band_max)}.</>}
            </p>
            <p className="mt-2 rounded-2xl bg-ad-tint px-3 py-2 text-xs text-ad-brand">{p.reason}</p>
            <div className="mt-3 text-sm text-ad-ink-soft">
              Suggested: usual price <b className="text-ad-ink">{rupees(p.proposed_price)}</b>, allowed {rupees(p.proposed_band_min)}–{rupees(p.proposed_band_max)}
            </div>
            <div className="mt-3 flex gap-2">
              <button onClick={() => approve.mutate(p.id)} disabled={approve.isPending || reject.isPending} className={btnPrimary}>
                Approve change
              </button>
              <button onClick={() => reject.mutate(p.id)} disabled={approve.isPending || reject.isPending} className={btnQuiet}>
                Keep current price
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function PricesTab() {
  const invalidate = useInvalidate();
  const [draft, setDraft] = useState({ ...BLANK });
  const [error, setError] = useState<string | null>(null);
  const { data: references } = useQuery({ queryKey: ["references"], queryFn: fetchReferences });
  const create = useMutation({
    mutationFn: createReference,
    onSuccess: () => {
      setDraft({ ...BLANK });
      setError(null);
      invalidate();
    },
    onError: (e) => setError(apiErrorMessage(e, "Could not add that price.")),
  });
  const refresh = useMutation({
    mutationFn: refreshReferences,
    onSuccess: () => { setError(null); invalidate(); },
    onError: (e) => setError(apiErrorMessage(e, "Refresh failed.")),
  });

  return (
    <div>
      <ErrorLine error={error} />
      <div className="rounded-[22px] border border-ad-line bg-white p-5">
        <h3 className="text-lg font-extrabold text-ad-ink">Add a usual price</h3>
        <p className="mt-1 text-sm text-ad-muted">
          Until an item has a usual price, nobody can be flagged for it. The allowed range is a hard limit: automatic
          updates can move the price inside it, never outside.
        </p>
        <div className="mt-3 grid gap-2 sm:grid-cols-6">
          <label className="sm:col-span-2">
            <span className="mb-1 block text-xs font-bold text-ad-ink-soft">Item</span>
            <input
              id="ref-name"
              value={draft.display_name}
              onChange={(e) => setDraft({ ...draft, display_name: e.target.value })}
              placeholder="Chicken Puff"
              className="w-full rounded-xl border border-ad-line px-3 py-2 text-sm outline-none focus:border-ad-brand"
            />
          </label>
          {(
            [
              ["reference_price", "Usual ₹"],
              ["band_min", "Lowest ₹"],
              ["band_max", "Highest ₹"],
              ["tolerance_abs", "Max extra ₹"],
            ] as const
          ).map(([field, label]) => (
            <label key={field}>
              <span className="mb-1 block text-xs font-bold text-ad-ink-soft">{label}</span>
              <input
                id={`ref-${field}`}
                type="number"
                min={0}
                value={draft[field] || ""}
                onChange={(e) => setDraft({ ...draft, [field]: Number(e.target.value) })}
                className="w-full rounded-xl border border-ad-line px-3 py-2 font-plex text-sm outline-none focus:border-ad-brand"
              />
            </label>
          ))}
        </div>
        <button
          onClick={() => create.mutate(draft)}
          disabled={create.isPending || !draft.display_name.trim()}
          className={`${btnPrimary} mt-3`}
        >
          Add price
        </button>
      </div>

      <div className="mt-6 flex items-center justify-between gap-3">
        <h3 className="text-lg font-extrabold text-ad-ink">Current usual prices</h3>
        <button onClick={() => refresh.mutate()} disabled={refresh.isPending} className={btnQuiet}>
          {refresh.isPending ? "Updating…" : "Re-estimate from reports"}
        </button>
      </div>
      {!references?.length ? (
        <div className="mt-3">
          <Empty title="No items priced yet" body="Add one above." />
        </div>
      ) : (
        <div className="mt-3 overflow-x-auto rounded-[22px] border border-ad-line bg-white">
          <table className="w-full text-sm">
            <thead className="bg-ad-soft text-left text-[11px] uppercase tracking-wider text-ad-muted">
              <tr>
                {["Item", "Usual", "Allowed range", "Max extra", "Set by", "Reports"].map((h) => (
                  <th key={h} className="px-4 py-2.5 font-bold">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-ad-hair">
              {references.map((r) => (
                <tr key={r.id}>
                  <td className="px-4 py-3 font-bold text-ad-ink">{r.display_name}</td>
                  <td className="px-4 py-3 font-plex font-medium text-ad-ink">{rupees(r.reference_price)}</td>
                  <td className="px-4 py-3 font-plex text-ad-muted">
                    {rupees(r.band_min)}–{rupees(r.band_max)}
                  </td>
                  <td className="px-4 py-3 font-plex text-ad-muted">+{rupees(r.tolerance_abs)}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-bold ${
                        r.source === "ADMIN" ? "bg-ad-tint text-ad-brand" : "bg-ad-chip text-ad-muted"
                      }`}
                    >
                      {r.source === "ADMIN" ? "an admin" : "automatic"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-ad-muted">{r.sample_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function AliasesTab() {
  const invalidate = useInvalidate();
  const [error, setError] = useState<string | null>(null);
  const { data: aliases } = useQuery({ queryKey: ["aliases"], queryFn: () => fetchAliases("PENDING") });
  const sweep = useMutation({
    mutationFn: sweepAliases,
    onSuccess: () => { setError(null); invalidate(); },
    onError: (e) => setError(apiErrorMessage(e, "Could not look for new names.")),
  });
  const decide = useMutation({
    mutationFn: ({ id, approve }: { id: string; approve: boolean }) => decideAlias(id, approve),
    onSuccess: () => { setError(null); invalidate(); },
    onError: (e) => setError(apiErrorMessage(e, "Could not save that.")),
  });

  return (
    <div>
      <ErrorLine error={error} />
      <div className="rounded-[22px] border border-ad-line bg-white p-5">
        <h3 className="text-lg font-extrabold text-ad-ink">Different names for the same item</h3>
        <p className="mt-1 text-sm text-ad-muted">
          Typos are caught automatically. These are different words for the same thing. Nothing here changes a price
          check until you approve it.
        </p>
        <button onClick={() => sweep.mutate()} disabled={sweep.isPending} className={`${btnQuiet} mt-3`}>
          {sweep.isPending ? "Looking…" : "Look for new names"}
        </button>
      </div>
      <div className="mt-4 space-y-3">
        {!aliases?.length ? (
          <Empty title="Nothing waiting" body="Suggestions appear when a reported item matches nothing you have priced." />
        ) : (
          aliases.map((a) => (
            <div key={a.id} className="rounded-[22px] border border-ad-line bg-white p-5">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className="rounded-xl bg-ad-tint px-2.5 py-1 font-bold text-ad-brand">{a.sample_raw_name}</span>
                <span className="text-ad-muted">might be the same as</span>
                <span className="rounded-xl bg-ad-tint px-2.5 py-1 font-bold text-ad-brand">{a.item_key}</span>
                <span className="ml-auto text-xs text-ad-muted">{shortDate(a.created_at)}</span>
              </div>
              {a.reason && <p className="mt-2 text-sm text-ad-ink-soft">{a.reason}</p>}
              <p className="mt-2 text-xs text-ad-muted">
                Approving means future reports with that name are checked against {a.item_key}. Choose “different”
                for another size or variant.
              </p>
              <div className="mt-3 flex gap-2">
                <button onClick={() => decide.mutate({ id: a.id, approve: true })} disabled={decide.isPending} className={btnPrimary}>
                  <span className="inline-flex items-center gap-1.5">
                    <Icon name="check" className="h-4 w-4" /> Same item
                  </span>
                </button>
                <button onClick={() => decide.mutate({ id: a.id, approve: false })} disabled={decide.isPending} className={btnQuiet}>
                  Different item
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
