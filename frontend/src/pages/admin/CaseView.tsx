import { useState, type ReactNode } from "react";

import { STRIKE_LABELS, type FlagCase, type Verdict } from "../../api/fraud";
import {
  Icon,
  KIND,
  KindBadge,
  Panel,
  SeverityDots,
  Stat,
  VerdictPill,
  dateTime,
  rupees,
  shortDate,
  timeAgo,
} from "./ui";
import {
  NearLineStrip,
  PayoutBars,
  PolicyCompare,
  PriceHistory,
  PriceHistoryLegend,
  PriceLine,
  RatingsSplit,
  RingDiagram,
  RingLegend,
} from "./visuals";

/* One flag, laid out the way a reviewer reads it: what happened, why the
   system raised it, the history that puts it in context, the person's record,
   and finally the two choices with what each one does. */

export default function CaseView({
  data,
  busy,
  onDecide,
}: {
  data: FlagCase;
  busy: boolean;
  onDecide: (uphold: boolean) => void;
}) {
  const k = KIND[data.kind] ?? KIND.other;
  return (
    <div className="space-y-4">
      <header className="rounded-[22px] border border-ad-line bg-white p-5">
        <div className="flex items-start gap-3.5">
          <KindBadge kind={data.kind} big />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`text-[11px] font-extrabold uppercase tracking-wider ${k.tone}`}>{k.label} flag</span>
              <SeverityDots level={data.severity} />
              <span className="text-xs text-ad-muted">· raised {timeAgo(data.created_at)}</span>
            </div>
            <h2 className="mt-0.5 text-xl font-extrabold leading-tight text-ad-ink sm:text-2xl">{data.title}</h2>
            <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ad-ink-soft">
              <span className="inline-flex items-center gap-1.5 font-bold">
                <Icon name="user" className="h-4 w-4 text-ad-muted" />
                {data.kind === "ring" && data.evidence?.members?.length
                  ? data.evidence.members.join(", ")
                  : data.subject.name}
              </span>
              {data.errand && (
                <span className="inline-flex items-center gap-1.5">
                  <Icon name="bag" className="h-4 w-4 text-ad-muted" />
                  “{data.errand.title}”
                </span>
              )}
              {data.decision && data.status === "OPEN" && (
                <a href="#decision" className="ml-auto text-xs font-extrabold text-ad-brand hover:underline">
                  Jump to decision ↓
                </a>
              )}
            </div>
          </div>
        </div>
      </header>

      <Panel title="What happened" icon="clock" hint="In plain words, from the system's own records.">
        <ol className="space-y-2.5">
          {data.story.map((s, i) => (
            <li key={i} className="flex gap-3 text-[15px] leading-relaxed text-ad-ink">
              <span className="mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-ad-tint font-plex text-xs font-medium text-ad-brand">
                {i + 1}
              </span>
              <span>{s}</span>
            </li>
          ))}
        </ol>
      </Panel>

      {data.kind === "price" && <PriceSections data={data} />}
      {data.kind === "pattern" && <PatternSections data={data} />}
      {data.kind === "payout" && <PayoutSections data={data} />}
      {data.kind === "ring" && <RingSections data={data} />}
      {data.kind === "ratings" && <RatingsSections data={data} />}

      {data.errand && <ErrandPanel errand={data.errand} />}
      {data.kind !== "ring" && <RecordPanel data={data} />}

      {data.decision && data.status === "OPEN" && (
        <section
          id="decision"
          className="scroll-mt-20 rounded-[22px] border-2 border-ad-brand/25 bg-white p-5 shadow-[0_14px_26px_rgba(23,32,31,0.10)]"
        >
          <h3 className="text-[15px] font-extrabold text-ad-ink">Your decision</h3>
          <p className="mb-3 text-[13px] text-ad-muted">Nothing happens to anyone until you choose.</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <DecisionButton
              tone="credit"
              icon="check"
              label={data.decision.dismiss}
              effect={data.decision.dismiss_effect}
              busy={busy}
              onClick={() => onDecide(false)}
            />
            <DecisionButton
              tone="caution"
              icon="x"
              label={data.decision.uphold}
              effect={data.decision.uphold_effect}
              busy={busy}
              onClick={() => onDecide(true)}
            />
          </div>
        </section>
      )}
    </div>
  );
}

function DecisionButton({
  tone,
  icon,
  label,
  effect,
  busy,
  onClick,
}: {
  tone: "credit" | "caution";
  icon: string;
  label: string;
  effect: string;
  busy: boolean;
  onClick: () => void;
}) {
  const cls =
    tone === "credit"
      ? "border-ad-credit/40 hover:border-ad-credit hover:bg-ad-credit-bg text-ad-credit"
      : "border-ad-caution/40 hover:border-ad-caution hover:bg-ad-caution-bg text-ad-caution";
  return (
    <button
      onClick={onClick}
      disabled={busy}
      className={`group rounded-2xl border-2 bg-white p-3.5 text-left transition hover:-translate-y-0.5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ad-brand disabled:opacity-50 ${cls}`}
    >
      <span className="flex items-center gap-2 text-[15px] font-extrabold">
        <Icon name={icon} className="h-5 w-5" />
        {busy ? "Saving…" : label}
      </span>
      <span className="mt-1 block text-xs leading-snug text-ad-ink-soft">{effect}</span>
    </button>
  );
}

/* ---------------------------------------------------------------- price */

function PriceSections({ data }: { data: FlagCase }) {
  const e = data.evidence ?? {};
  const h = data.history;
  return (
    <>
      {e.reference != null && e.line != null && (
        <Panel
          title="Why it was flagged"
          icon="price"
          hint="Anything up to the limit is paid in full. Past it, only the usual price is paid and the rest waits for you."
        >
          <PriceLine reference={e.reference} line={e.line} claimed={e.claimed_unit} />
          <div className="grid grid-cols-3 gap-2">
            <Stat label="Reported" value={rupees(e.claimed_unit * (e.quantity ?? 1))} sub={e.quantity > 1 ? `${e.quantity} × ${rupees(e.claimed_unit)}` : undefined} />
            <Stat label="Paid now" value={<span className="text-ad-credit">{rupees(e.eligible)}</span>} />
            <Stat label="Held for you" value={<span className="text-ad-money-text">{rupees(e.withheld)}</span>} />
          </div>
          {e.store && (
            <p className="mt-3 text-xs text-ad-muted">
              Bought at <span className="font-bold text-ad-ink-soft">{e.store}</span>
              {e.store_reports != null && ` · ${e.store_reports} other runner${e.store_reports === 1 ? " has" : "s have"} priced it there`}
            </p>
          )}
        </Panel>
      )}
      {h && h.item_claims?.length > 0 && (
        <Panel
          title={`Price history: ${e.item}`}
          icon="history"
          hint={`Every report of this item on campus in the last 90 days. Most paid about ${rupees(h.item_stats?.median_honest)}.`}
        >
          <PriceHistory points={h.item_claims} reference={e.reference ?? null} line={e.line ?? null} />
          <PriceHistoryLegend />
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Stat label="Reports" value={h.item_stats.count} />
            <Stat label="Runners" value={h.item_stats.runners} />
            <Stat label="Lowest–highest" value={`${rupees(h.item_stats.lowest)}–${rupees(h.item_stats.highest)}`} />
            <Stat label="Over the limit" value={h.item_stats.flagged} />
          </div>
          <Expandable
            rows={h.item_claims}
            head={["When", "Runner", "Shop", "Price", ""]}
            render={(r) => [
              shortDate(r.at),
              <span key="n" className="font-bold text-ad-ink">
                {r.runner}
                {r.is_subject && <span className="ml-1.5 rounded-full bg-ad-tint px-1.5 py-0.5 text-[10px] font-bold text-ad-brand">this runner</span>}
              </span>,
              r.store ?? "—",
              <span key="p" className={`font-plex ${r.is_this ? "font-medium text-ad-caution" : ""}`}>{rupees(r.unit)}</span>,
              <VerdictPill key="v" verdict={r.verdict as Verdict} />,
            ]}
            highlight={(r) => r.is_this}
          />
        </Panel>
      )}
      {h && h.runner_claims?.length > 0 && (
        <Panel
          title={`${data.subject.name}'s recent price reports`}
          icon="user"
          hint="Everything they reported in the last 90 days, any item. One high price is common. A habit is not."
        >
          <VerdictSummary counts={h.runner_verdicts} />
          <Expandable
            rows={h.runner_claims}
            head={["When", "Item", "Price", "Usual", ""]}
            render={(r) => [
              shortDate(r.at),
              <span key="i" className="font-bold text-ad-ink">{r.item}</span>,
              <span key="p" className="font-plex">{rupees(r.unit)}</span>,
              <span key="r" className="font-plex text-ad-muted">{r.reference != null ? rupees(r.reference) : "—"}</span>,
              <VerdictPill key="v" verdict={r.verdict as Verdict} />,
            ]}
            highlight={(r) => r.is_this}
          />
        </Panel>
      )}
    </>
  );
}

function VerdictSummary({ counts }: { counts: Record<string, number> }) {
  const order: Verdict[] = ["OK", "ELEVATED", "FLAGGED", "NO_REFERENCE"];
  return (
    <div className="mb-3 flex flex-wrap gap-2">
      {order
        .filter((v) => counts?.[v])
        .map((v) => (
          <span key={v} className="inline-flex items-center gap-1.5 rounded-full border border-ad-line px-2.5 py-1 text-xs">
            <VerdictPill verdict={v} />
            <span className="font-plex font-medium text-ad-ink">{counts[v]}</span>
          </span>
        ))}
    </div>
  );
}

/* -------------------------------------------------------------- pattern */

function PatternSections({ data }: { data: FlagCase }) {
  const e = data.evidence ?? {};
  const rows = data.history?.claims ?? [];
  return (
    <Panel
      title="Why it was flagged"
      icon="pattern"
      hint={`Each bar is one report. The further right, the closer it came to the limit. Flagged when ${Math.round(
        (e.share_needed ?? 0.6) * 100,
      )}% or more of someone's reports land in the copper zone.`}
    >
      {rows.length ? (
        <NearLineStrip rows={rows} mark={e.near_mark ?? 0.6} />
      ) : (
        <p className="text-sm text-ad-muted">The individual reports are no longer available.</p>
      )}
      <div className="mt-4 grid grid-cols-3 gap-2">
        <Stat label="Close to limit" value={`${e.near} of ${e.judged}`} />
        <Stat label="This runner" value={e.judged ? `${Math.round((e.near / e.judged) * 100)}%` : "—"} />
        <Stat
          label="Rest of campus"
          value={e.campus_near_share != null ? `${Math.round(e.campus_near_share * 100)}%` : "—"}
        />
      </div>
    </Panel>
  );
}

/* --------------------------------------------------------------- payout */

function PayoutSections({ data }: { data: FlagCase }) {
  const e = data.evidence ?? {};
  const h = data.history ?? {};
  return (
    <>
      <Panel title="Why it was flagged" icon="payout" hint="A runner can never be paid more than the requester agreed to lock.">
        <PayoutBars held={Number(e.held ?? 0)} payable={Number(e.payable ?? 0)} />
        <p className="mt-3 text-xs text-ad-muted">Includes the {rupees(e.reward)} reward. Nothing has moved yet.</p>
      </Panel>
      {(h.reported_lines?.length > 0 || h.ordered_items?.length > 0) && (
        <Panel title="What was ordered, and what was reported" icon="bag">
          {h.ordered_items?.length > 0 && (
            <SimpleTable
              head={["Ordered", "Qty", "Listed price"]}
              rows={h.ordered_items.map((i: { item: string; quantity: number; unit: number | null }) => [
                i.item,
                i.quantity,
                i.unit != null ? rupees(i.unit) : "priced at pickup",
              ])}
            />
          )}
          {h.reported_lines?.length > 0 && (
            <div className="mt-3">
              <SimpleTable
                head={["Reported", "Qty", "Price", "Usual", ""]}
                rows={h.reported_lines.map(
                  (l: { item: string; quantity: number; unit: number; reference: number | null; verdict: Verdict }) => [
                    l.item,
                    l.quantity,
                    rupees(l.unit),
                    l.reference != null ? rupees(l.reference) : "—",
                    <VerdictPill key="v" verdict={l.verdict} />,
                  ],
                )}
              />
            </div>
          )}
        </Panel>
      )}
    </>
  );
}

/* ----------------------------------------------------------------- ring */

function RingSections({ data }: { data: FlagCase }) {
  const e = data.evidence ?? {};
  const h = data.history ?? {};
  const legs = h.legs ?? [];
  return (
    <>
      <Panel
        title="Why it was flagged"
        icon="ring"
        hint={`A payment between two members counts only with at least ${e.leg_rule?.min_errands ?? 2} errands and ${rupees(
          e.leg_rule?.min_value ?? 150,
        )} or ${e.leg_rule?.or_errands ?? 5} errands. When money can go round the whole group and come back, it's a ring.`}
      >
        {e.members?.length ? (
          <>
            <RingDiagram members={e.members} legs={legs} friends={h.friendships ?? []} />
            <RingLegend />
          </>
        ) : (
          <p className="text-sm text-ad-muted">This flag doesn't list its members.</p>
        )}
        <div className="mt-4 grid grid-cols-3 gap-2">
          <Stat label="Errands inside" value={h.occurrences?.length ?? 0} />
          <Stat label="Money round the loop" value={rupees(e.total_value)} />
          <Stat label="Times round" value={e.laps ?? 0} />
        </div>
      </Panel>

      {e.policy && (
        <Panel
          title="Did our matcher cause it?"
          icon="bolt"
          hint="Our app offers friends' errands to friends first, so honest friends also pay each other. This checks whether that explains it."
        >
          <PolicyCompare expected={e.policy.expected_share} observed={e.policy.observed_share} z={e.policy.z} />
          <p className="mt-2 text-xs text-ad-muted">
            Based on {e.policy.rounds} offer rounds, {e.policy.explored_rounds} of them with the friend bonus switched off.
          </p>
        </Panel>
      )}

      {e.semantic && (
        <Panel title="What their errands say" icon="bag" hint="A local language model's opinion. Advice only, never evidence on its own.">
          <p className="text-sm font-bold text-ad-ink">
            {e.semantic.exculpatory
              ? "Reads like genuine, varied campus life."
              : e.semantic.reads_as_genuine
                ? "Reads as genuine, but not strongly."
                : "Does not read like varied campus life."}
          </p>
          {e.semantic.observations?.length > 0 && (
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ad-ink-soft">
              {e.semantic.observations.map((o: string, i: number) => (
                <li key={i}>{o}</li>
              ))}
            </ul>
          )}
        </Panel>
      )}

      {h.occurrences?.length > 0 && (
        <Panel
          title="Every errand between them"
          icon="history"
          hint={`Completed in the last ${h.window_days} days. Arrows point from the person who paid to the runner.`}
        >
          <Expandable
            rows={h.occurrences}
            head={["When", "Who paid → who ran it", "Errand", "Value"]}
            render={(o) => [
              shortDate(o.at),
              <span key="w" className="font-bold text-ad-ink">
                {o.from} <span className="text-ad-caution">→</span> {o.to}
              </span>,
              o.title,
              <span key="v" className="font-plex">{rupees(o.value)}</span>,
            ]}
          />
        </Panel>
      )}

      {h.outside?.length > 0 && (
        <Panel title="Do they also work with other people?" icon="user" hint="Honest friends usually run errands for strangers too.">
          <div className="space-y-2.5">
            {h.outside.map((m: { name: string; inside: number; outside: number }) => {
              const total = m.inside + m.outside || 1;
              return (
                <div key={m.name} className="flex items-center gap-3 text-sm">
                  <span className="w-24 shrink-0 truncate font-bold text-ad-ink">{m.name}</span>
                  <div className="flex h-3 flex-1 overflow-hidden rounded-full bg-ad-hair">
                    <div className="bg-ad-caution" style={{ width: `${(m.inside / total) * 100}%` }} />
                    <div className="bg-ad-brand/45" style={{ width: `${(m.outside / total) * 100}%` }} />
                  </div>
                  <span className="w-28 shrink-0 text-right text-xs text-ad-muted">
                    {m.inside} inside · {m.outside} outside
                  </span>
                </div>
              );
            })}
          </div>
        </Panel>
      )}
    </>
  );
}

/* -------------------------------------------------------------- ratings */

function RatingsSections({ data }: { data: FlagCase }) {
  const e = data.evidence ?? {};
  const ratings = data.history?.ratings ?? [];
  return (
    <>
      <Panel title="Why it was flagged" icon="ratings" hint="A rating means more when it comes from someone who isn't already a friend.">
        <RatingsSplit inside={e.in_cluster ?? 0} outside={e.out_cluster ?? 0} meanIn={e.mean_in ?? null} meanOut={e.mean_out ?? null} />
        {e.last_penalty && (
          <p className="mt-3 text-xs text-ad-muted">Last penalty: {dateTime(e.last_penalty)}. Ratings right after it are marked below.</p>
        )}
      </Panel>
      {ratings.length > 0 && (
        <Panel title="Every rating they received" icon="history">
          <Expandable
            rows={ratings}
            head={["When", "From", "Stars", "Note"]}
            render={(r) => [
              shortDate(r.at),
              <span key="f" className="font-bold text-ad-ink">
                {r.rater}
                {r.from_friend && (
                  <span className="ml-1.5 rounded-full bg-ad-caution-bg px-1.5 py-0.5 text-[10px] font-bold text-ad-caution">friend</span>
                )}
                {e.last_penalty && new Date(r.at) >= new Date(e.last_penalty) && (
                  <span className="ml-1.5 rounded-full bg-ad-warn-bg px-1.5 py-0.5 text-[10px] font-bold text-ad-warn-text">after penalty</span>
                )}
              </span>,
              <span key="s" className="text-ad-money">{"★".repeat(r.stars)}<span className="text-ad-line">{"★".repeat(5 - r.stars)}</span></span>,
              <span key="c" className="text-ad-muted">{r.comment ?? "—"}</span>,
            ]}
          />
        </Panel>
      )}
    </>
  );
}

/* --------------------------------------------------------- shared blocks */

function ErrandPanel({ errand }: { errand: NonNullable<FlagCase["errand"]> }) {
  return (
    <Panel title="The errand" icon="bag">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Requester" value={<span className="text-base">{errand.requester}</span>} />
        <Stat label="Runner" value={<span className="text-base">{errand.runner ?? "—"}</span>} />
        <Stat label="Reward" value={rupees(errand.reward)} />
        <Stat
          label="Locked money"
          value={errand.hold ? rupees(errand.hold.remaining) : "—"}
          sub={errand.hold ? `${holdLabel(errand.hold.status)} · of ${rupees(errand.hold.amount)}` : undefined}
        />
      </div>
      <p className="mt-2 text-xs text-ad-muted">
        {errand.pickup && <>From {errand.pickup} · </>}posted {dateTime(errand.created_at)}
      </p>
    </Panel>
  );
}

function holdLabel(status: string): string {
  return (
    { HELD: "still locked", RELEASED: "paid out", REFUNDED: "refunded", PENDING_REVIEW: "waiting for you" }[status] ??
    status.toLowerCase()
  );
}

function RecordPanel({ data }: { data: FlagCase }) {
  const s = data.subject;
  const r = data.record;
  const others = r.flags.filter((f) => !f.is_this);
  return (
    <Panel title={`${s.name}'s record`} icon="shield" hint="So one flag is read in the context of everything else.">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Runs completed" value={s.runs_completed} sub={`${s.errands_posted} errands posted`} />
        <Stat
          label="Rating"
          value={s.rating != null ? `${Number(s.rating).toFixed(1)} ★` : "—"}
          sub={`${s.rating_count} ratings`}
        />
        <Stat
          label="Price flags, 30 days"
          value={r.price_flags_in_window}
          sub={r.next_action_at ? `next step at ${r.next_action_at}` : "at the last step"}
        />
        <Stat label="Past decisions" value={`${r.upheld_before} / ${r.dismissed_before}`} sub="upheld / dismissed" />
      </div>
      {r.strikes.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {r.strikes.map((st, i) => (
            <span key={i} className="rounded-full bg-ad-caution-bg px-2.5 py-1 text-xs font-bold text-ad-caution">
              {STRIKE_LABELS[st.action]} · {shortDate(st.created_at)}
              {st.lifted_at && " (lifted)"}
            </span>
          ))}
        </div>
      )}
      {others.length > 0 ? (
        <div className="mt-3">
          <div className="mb-1.5 text-xs font-bold text-ad-ink-soft">Other flags in the last 90 days</div>
          <ul className="divide-y divide-ad-hair rounded-2xl border border-ad-line">
            {others.slice(0, 6).map((f) => (
              <li key={f.id} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                <span className="truncate text-ad-ink">{f.title}</span>
                <span className="flex shrink-0 items-center gap-2 text-xs text-ad-muted">
                  {shortDate(f.created_at)}
                  <StatusPill status={f.status} />
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="mt-3 text-xs text-ad-muted">No other flags in the last 90 days.</p>
      )}
    </Panel>
  );
}

function StatusPill({ status }: { status: string }) {
  const map: Record<string, string> = {
    OPEN: "bg-ad-warn-bg text-ad-warn-text",
    UPHELD: "bg-ad-caution-bg text-ad-caution",
    DISMISSED: "bg-ad-credit-bg text-ad-credit",
  };
  const label: Record<string, string> = { OPEN: "waiting", UPHELD: "upheld", DISMISSED: "dismissed" };
  return <span className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${map[status] ?? ""}`}>{label[status] ?? status}</span>;
}

// History rows come straight from the case payload, whose shape varies by flag kind.
type Row = any;

function Expandable({
  rows,
  head,
  render,
  highlight,
  initial = 6,
}: {
  rows: Row[];
  head: string[];
  render: (row: Row) => ReactNode[];
  highlight?: (row: Row) => boolean;
  initial?: number;
}) {
  const [all, setAll] = useState(false);
  const shown = all ? rows : rows.slice(0, initial);
  return (
    <div className="mt-3">
      <div className="overflow-x-auto rounded-2xl border border-ad-line">
        <table className="w-full text-sm">
          <thead className="bg-ad-soft text-left text-[11px] uppercase tracking-wider text-ad-muted">
            <tr>
              {head.map((h, i) => (
                <th key={i} className="whitespace-nowrap px-3 py-2 font-bold">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-ad-hair">
            {shown.map((r, i) => (
              <tr key={i} className={highlight?.(r) ? "bg-ad-caution-bg/60" : ""}>
                {render(r).map((c, j) => (
                  <td key={j} className="whitespace-nowrap px-3 py-2 text-ad-ink-soft">
                    {c}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > initial && (
        <button
          onClick={() => setAll(!all)}
          className="mt-2 text-xs font-bold text-ad-brand hover:underline"
        >
          {all ? "Show fewer" : `Show all ${rows.length}`}
        </button>
      )}
    </div>
  );
}

function SimpleTable({ head, rows }: { head: string[]; rows: ReactNode[][] }) {
  return (
    <div className="overflow-x-auto rounded-2xl border border-ad-line">
      <table className="w-full text-sm">
        <thead className="bg-ad-soft text-left text-[11px] uppercase tracking-wider text-ad-muted">
          <tr>
            {head.map((h, i) => (
              <th key={i} className="px-3 py-2 font-bold">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-ad-hair">
          {rows.map((r, i) => (
            <tr key={i}>
              {r.map((c, j) => (
                <td key={j} className="px-3 py-2 text-ad-ink-soft">
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
