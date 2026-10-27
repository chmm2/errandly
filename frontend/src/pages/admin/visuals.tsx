import type { Verdict } from "../../api/fraud";
import { rupees, shortDate } from "./ui";

/* The pictures behind each flag. Hand-drawn SVG: every one of these is a
   single, specific explanation, so a charting library would add weight
   without adding clarity. Colours: teal = normal, copper = money at stake,
   caution red = over the line. */

const TEAL = "#274A4C";
const TEAL_SOFT = "#9FB8B4";
const COPPER = "#C0803C";
const RED = "#A5473C";
const LINE = "#E4EAE8";
const MUTED = "#6B7A78";

/* ------------------------------------------------ one price against the line */

export function PriceLine({
  reference,
  line,
  claimed,
}: {
  reference: number;
  line: number;
  claimed: number;
}) {
  const max = Math.max(claimed, line) * 1.15;
  const at = (v: number) => `${Math.min(100, (v / max) * 100)}%`;
  const over = claimed > line;
  return (
    <div className="pt-7 pb-9">
      <div className="relative h-4 rounded-full bg-ad-hair">
        <div className="absolute inset-y-0 left-0 rounded-l-full bg-ad-tint" style={{ width: at(reference) }} />
        <div
          className="absolute inset-y-0 bg-ad-credit-bg"
          style={{ left: at(reference), width: `calc(${at(line)} - ${at(reference)})` }}
        />
        {over && (
          <div
            className="absolute inset-y-0 rounded-r-full"
            style={{
              left: at(line),
              width: `calc(${at(claimed)} - ${at(line)})`,
              background: "repeating-linear-gradient(135deg,#FAF0EE 0 6px,#F1D9D4 6px 12px)",
            }}
          />
        )}
        <Marker at={at(reference)} color={TEAL} top="Usual" bottom={rupees(reference)} />
        <Marker at={at(line)} color={COPPER} top="Limit" bottom={rupees(line)} dashed />
        <Marker at={at(claimed)} color={over ? RED : TEAL} top="Reported" bottom={rupees(claimed)} strong />
      </div>
    </div>
  );
}

function Marker({
  at,
  color,
  top,
  bottom,
  dashed = false,
  strong = false,
}: {
  at: string;
  color: string;
  top: string;
  bottom: string;
  dashed?: boolean;
  strong?: boolean;
}) {
  return (
    <div className="absolute -top-6 -bottom-8 flex -translate-x-1/2 flex-col items-center" style={{ left: at }}>
      <span className="text-[10.5px] font-bold uppercase tracking-wider" style={{ color }}>
        {top}
      </span>
      <span
        className="my-0.5 w-0 flex-1"
        style={{ borderLeft: `2px ${dashed ? "dashed" : "solid"} ${color}` }}
      />
      <span className={`font-plex ${strong ? "text-sm font-medium" : "text-xs"}`} style={{ color }}>
        {bottom}
      </span>
    </div>
  );
}

/* ------------------------------------------ every report of one item, in time */

export interface PricePoint {
  at: string;
  unit: number;
  verdict: Verdict;
  is_subject: boolean;
  is_this: boolean;
}

export function PriceHistory({
  points,
  reference,
  line,
}: {
  points: PricePoint[];
  reference: number | null;
  line: number | null;
}) {
  const W = 640;
  const H = 230;
  const L = 46;
  const R = 18;
  const T = 18;
  const B = 30;
  if (points.length === 0) return null;
  const times = points.map((p) => new Date(p.at).getTime());
  let t0 = Math.min(...times);
  let t1 = Math.max(...times);
  if (t1 - t0 < 86400000) {
    t0 -= 43200000;
    t1 += 43200000;
  }
  const top = Math.max(...points.map((p) => p.unit), line ?? 0, reference ?? 0) * 1.1 || 1;
  const step = niceStep(top / 4);
  const yMax = Math.ceil(top / step) * step;
  const x = (t: number) => L + ((t - t0) / (t1 - t0)) * (W - L - R);
  const y = (v: number) => H - B - (v / yMax) * (H - T - B);
  const ticks = Array.from({ length: Math.round(yMax / step) + 1 }, (_, i) => i * step);
  const ordered = [...points].sort((a, b) => Number(a.is_this) - Number(b.is_this));

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="Every price reported for this item over time">
      {ticks.map((v) => (
        <g key={v}>
          <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} stroke={LINE} />
          <text x={L - 8} y={y(v) + 4} textAnchor="end" fontSize="11" fill={MUTED} fontFamily="IBM Plex Mono">
            {rupees(v)}
          </text>
        </g>
      ))}
      {reference != null && line != null && (
        <rect x={L} width={W - L - R} y={y(line)} height={Math.max(0, y(reference) - y(line))} fill="#EDF6F0" opacity="0.8" />
      )}
      {reference != null && (
        <g>
          <line x1={L} x2={W - R} y1={y(reference)} y2={y(reference)} stroke={TEAL} strokeWidth="1.5" strokeDasharray="5 5" />
          <text x={W - R} y={y(reference) + 14} textAnchor="end" fontSize="11" fontWeight="700" fill={TEAL}>
            usual {rupees(reference)}
          </text>
        </g>
      )}
      {line != null && (
        <g>
          <line x1={L} x2={W - R} y1={y(line)} y2={y(line)} stroke={COPPER} strokeWidth="1.5" strokeDasharray="5 5" />
          <text x={W - R} y={y(line) - 6} textAnchor="end" fontSize="11" fontWeight="700" fill={COPPER}>
            limit {rupees(line)}
          </text>
        </g>
      )}
      {ordered.map((p, i) => {
        const cx = x(new Date(p.at).getTime());
        const cy = y(p.unit);
        if (p.is_this) {
          return (
            <g key={i}>
              <circle cx={cx} cy={cy} r="11" fill="none" stroke={RED} strokeWidth="2.5" />
              <circle cx={cx} cy={cy} r="5" fill={RED} />
              <text
                x={cx > W - 140 ? cx - 16 : cx + 16}
                y={cy + 4}
                textAnchor={cx > W - 140 ? "end" : "start"}
                fontSize="12"
                fontWeight="800"
                fill={RED}
              >
                this report {rupees(p.unit)}
              </text>
            </g>
          );
        }
        const fill = p.verdict === "FLAGGED" ? RED : p.is_subject ? TEAL : "#fff";
        const stroke = p.verdict === "FLAGGED" ? RED : p.is_subject ? TEAL : TEAL_SOFT;
        return <circle key={i} cx={cx} cy={cy} r="4.5" fill={fill} stroke={stroke} strokeWidth="1.8" opacity="0.9" />;
      })}
      <text x={L} y={H - 8} fontSize="11" fill={MUTED}>
        {shortDate(new Date(t0).toISOString())}
      </text>
      <text x={W - R} y={H - 8} textAnchor="end" fontSize="11" fill={MUTED}>
        {shortDate(new Date(t1).toISOString())}
      </text>
    </svg>
  );
}

/** A round axis step (1, 2 or 5 times a power of ten) near the raw one. */
function niceStep(raw: number): number {
  const p = 10 ** Math.floor(Math.log10(raw || 1));
  const f = raw / p;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p;
}

export function PriceHistoryLegend() {
  return (
    <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ad-muted">
      <Dot fill="#fff" stroke={TEAL_SOFT}>Other runners</Dot>
      <Dot fill={TEAL} stroke={TEAL}>This runner</Dot>
      <Dot fill={RED} stroke={RED}>Over the limit</Dot>
      <span className="inline-flex items-center gap-1.5">
        <span className="h-2.5 w-4 rounded-sm bg-ad-credit-bg" /> Paid in full
      </span>
    </div>
  );
}

function Dot({ fill, stroke, children }: { fill: string; stroke: string; children: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="h-2.5 w-2.5 rounded-full border-2" style={{ background: fill, borderColor: stroke }} />
      {children}
    </span>
  );
}

/* ------------------------------------- how close each report came to the limit */

export interface NearRow {
  at: string;
  item: string;
  over: number;
  used: number;
  near: boolean;
}

export function NearLineStrip({ rows, mark }: { rows: NearRow[]; mark: number }) {
  const cap = 1.15;
  const pos = (f: number) => `${(Math.min(f, cap) / cap) * 100}%`;
  return (
    <div className="space-y-2.5">
      <div className="relative ml-[132px] h-4 text-[10.5px] font-bold uppercase tracking-wider">
        <span className="absolute -translate-x-1/2 text-ad-muted" style={{ left: pos(0) }}>Usual</span>
        <span className="absolute -translate-x-1/2 text-ad-warn-text" style={{ left: pos(mark) }}>Close</span>
        <span className="absolute -translate-x-1/2 text-ad-money-text" style={{ left: pos(1) }}>Limit</span>
      </div>
      {rows.map((r, i) => (
        <div key={i} className="flex items-center gap-3">
          <div className="w-[120px] shrink-0 text-xs leading-tight">
            <div className="truncate font-bold text-ad-ink">{r.item}</div>
            <div className="text-ad-muted">{shortDate(r.at)}</div>
          </div>
          <div className="relative h-3 flex-1 rounded-full bg-ad-hair">
            <div
              className={`absolute inset-y-0 left-0 rounded-full ${r.near ? "bg-ad-money" : "bg-ad-brand/60"}`}
              style={{ width: pos(r.used) }}
            />
            <span className="absolute -top-1 -bottom-1 w-px bg-ad-warn-text/60" style={{ left: pos(mark) }} />
            <span className="absolute -top-1.5 -bottom-1.5 w-0.5 bg-ad-money-text" style={{ left: pos(1) }} />
          </div>
          <div className={`w-12 shrink-0 text-right font-plex text-xs ${r.near ? "text-ad-money-text" : "text-ad-muted"}`}>
            +{rupees(r.over)}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ---------------------------------------------- locked money vs what's needed */

export function PayoutBars({ held, payable }: { held: number; payable: number }) {
  const max = Math.max(held, payable, 1);
  const w = (v: number) => `${(v / max) * 100}%`;
  return (
    <div className="space-y-3">
      <BarRow label="Money locked" value={rupees(held)} color="bg-ad-brand" width={w(held)} />
      <div>
        <div className="mb-1 flex justify-between text-xs font-bold">
          <span className="text-ad-ink-soft">Needed to pay the runner</span>
          <span className="font-plex text-ad-money-text">{rupees(payable)}</span>
        </div>
        <div className="relative h-4 overflow-hidden rounded-full bg-ad-hair">
          <div className="absolute inset-y-0 left-0 bg-ad-money" style={{ width: w(Math.min(held, payable)) }} />
          {payable > held && (
            <div
              className="absolute inset-y-0"
              style={{
                left: w(held),
                width: `calc(${w(payable)} - ${w(held)})`,
                background: "repeating-linear-gradient(135deg,#A5473C 0 6px,#C46A5E 6px 12px)",
              }}
            />
          )}
        </div>
        {payable > held && (
          <div className="mt-1 text-right text-xs font-bold text-ad-caution">
            {rupees(payable - held)} more than was ever locked
          </div>
        )}
      </div>
    </div>
  );
}

function BarRow({ label, value, color, width }: { label: string; value: string; color: string; width: string }) {
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs font-bold">
        <span className="text-ad-ink-soft">{label}</span>
        <span className="font-plex text-ad-brand">{value}</span>
      </div>
      <div className="h-4 overflow-hidden rounded-full bg-ad-hair">
        <div className={`h-full rounded-full ${color}`} style={{ width }} />
      </div>
    </div>
  );
}

/* ----------------------------------------------- who paid whom inside a group */

export interface Leg {
  from: string;
  to: string;
  errands: number;
  value: number;
  counts: boolean;
}

export function RingDiagram({
  members,
  legs,
  friends,
}: {
  members: string[];
  legs: Leg[];
  friends: { a: string; b: string; status: string }[];
}) {
  const W = 420;
  const H = 320;
  const cx = W / 2;
  const cy = H / 2 + 4;
  const R = members.length <= 2 ? 105 : 112;
  const pos: Record<string, { x: number; y: number }> = {};
  members.forEach((m, i) => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / Math.max(members.length, 1);
    pos[m] = { x: cx + R * Math.cos(a), y: cy + R * Math.sin(a) };
  });
  const r = 30;

  const curve = (a: { x: number; y: number }, b: { x: number; y: number }, inward = false) => {
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const len = Math.hypot(dx, dy) || 1;
    let nx = -dy / len;
    let ny = dx / len;
    // Bend away from the middle so the amounts sit outside the triangle
    // instead of piling up in its centre.
    const outward = ((a.x + b.x) / 2 - cx) * nx + ((a.y + b.y) / 2 - cy) * ny >= 0;
    if (members.length > 2 && outward === inward) {
      nx = -nx;
      ny = -ny;
    }
    const off = 40;
    const mx = (a.x + b.x) / 2 + nx * off;
    const my = (a.y + b.y) / 2 + ny * off;
    const ua = Math.hypot(mx - a.x, my - a.y) || 1;
    const ub = Math.hypot(mx - b.x, my - b.y) || 1;
    const sx = a.x + ((mx - a.x) / ua) * (r + 3);
    const sy = a.y + ((my - a.y) / ua) * (r + 3);
    const ex = b.x + ((mx - b.x) / ub) * (r + 7);
    const ey = b.y + ((my - b.y) / ub) * (r + 7);
    return { d: `M${sx},${sy} Q${mx},${my} ${ex},${ey}`, lx: (a.x + b.x) / 2 + nx * (off / 2), ly: (a.y + b.y) / 2 + ny * (off / 2) };
  };

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="mx-auto h-auto w-full max-w-[460px]" role="img" aria-label="Payments between the group's members">
      <defs>
        {[
          ["live", RED],
          ["weak", TEAL_SOFT],
        ].map(([id, c]) => (
          <marker key={id} id={`ring-${id}`} viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="12" markerHeight="12" markerUnits="userSpaceOnUse" orient="auto">
            <path d="M0,0 L10,5 L0,10 z" fill={c} />
          </marker>
        ))}
      </defs>
      {friends
        .filter((f) => f.status === "ACCEPTED" && pos[f.a] && pos[f.b])
        .map((f, i) => (
          <line key={i} x1={pos[f.a].x} y1={pos[f.a].y} x2={pos[f.b].x} y2={pos[f.b].y} stroke="#B9CBC8" strokeWidth="2" strokeDasharray="5 6" />
        ))}
      {legs
        .filter((l) => pos[l.from] && pos[l.to])
        .map((l, i) => {
          // Money both ways between the same two people: one arrow bends out,
          // the other in, so they don't sit on top of each other.
          const twoWay = legs.some((o) => o.from === l.to && o.to === l.from);
          const c = curve(pos[l.from], pos[l.to], twoWay && l.from > l.to);
          const label = `${rupees(l.value)} · ${l.errands}`;
          const w = label.length * 7 + 16;
          return (
            <g key={i}>
              <path
                d={c.d}
                fill="none"
                stroke={l.counts ? RED : TEAL_SOFT}
                strokeWidth={l.counts ? 3 : 2}
                strokeDasharray={l.counts ? undefined : "5 5"}
                markerEnd={`url(#ring-${l.counts ? "live" : "weak"})`}
              />
              <rect x={c.lx - w / 2} y={c.ly - 11} width={w} height="22" rx="7" fill="#fff" stroke={l.counts ? RED : LINE} />
              <text x={c.lx} y={c.ly + 4} textAnchor="middle" fontSize="11.5" fontWeight="700" fontFamily="IBM Plex Mono" fill={l.counts ? RED : MUTED}>
                {label}
              </text>
            </g>
          );
        })}
      {members.map((m) => (
        <g key={m}>
          <circle cx={pos[m].x} cy={pos[m].y} r={r} fill="#FAF0EE" stroke={RED} strokeWidth="2.5" />
          <text x={pos[m].x} y={pos[m].y + 4.5} textAnchor="middle" fontSize="12.5" fontWeight="800" fill="#17201F" fontFamily="Plus Jakarta Sans">
            {short(m)}
          </text>
        </g>
      ))}
    </svg>
  );
}

/** First name, trimmed to fit inside a circle. */
function short(name: string): string {
  const first = name.split(" ")[0];
  return first.length > 9 ? `${first.slice(0, 8)}…` : first;
}

export function RingLegend() {
  return (
    <div className="mt-1 flex flex-wrap justify-center gap-x-4 gap-y-1 text-xs text-ad-muted">
      <span className="inline-flex items-center gap-1.5">
        <span className="w-5 border-t-2 border-dashed border-[#B9CBC8]" /> Friends
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="w-5 border-t-[3px] border-ad-caution" /> Payments that count (₹ · errands)
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="w-5 border-t-2 border-dashed border-[#9FB8B4]" /> Too small to count
      </span>
    </div>
  );
}

/* --------------------------------------- what the matcher explains vs reality */

export function PolicyCompare({
  expected,
  observed,
  z,
}: {
  expected: number;
  observed: number;
  z: number;
}) {
  const w = (v: number) => `${Math.max(2, Math.min(100, v * 100))}%`;
  return (
    <div className="space-y-3">
      <div>
        <div className="mb-1 flex justify-between text-xs font-bold">
          <span className="text-ad-ink-soft">Our matcher alone would explain</span>
          <span className="font-plex text-ad-brand">{Math.round(expected * 100)}%</span>
        </div>
        <div className="h-4 overflow-hidden rounded-full bg-ad-hair">
          <div className="h-full rounded-full bg-ad-brand" style={{ width: w(expected) }} />
        </div>
      </div>
      <div>
        <div className="mb-1 flex justify-between text-xs font-bold">
          <span className="text-ad-ink-soft">What actually happened</span>
          <span className="font-plex text-ad-caution">{Math.round(observed * 100)}%</span>
        </div>
        <div className="h-4 overflow-hidden rounded-full bg-ad-hair">
          <div className="h-full rounded-full bg-ad-caution" style={{ width: w(observed) }} />
        </div>
      </div>
      <p className="text-xs text-ad-muted">
        Share of the group's errands that went to each other.{" "}
        <span className={`font-bold ${z >= 3 ? "text-ad-caution" : "text-ad-credit"}`}>z = {z}</span>
        {z >= 3 ? " — 3 or more means our matcher can't explain it." : " — under 3, so our matcher explains it."}
      </p>
    </div>
  );
}

/* ------------------------------------------- where a runner's ratings came from */

export function RatingsSplit({
  inside,
  outside,
  meanIn,
  meanOut,
}: {
  inside: number;
  outside: number;
  meanIn: number | null;
  meanOut: number | null;
}) {
  const total = inside + outside || 1;
  return (
    <div>
      <div className="flex h-5 overflow-hidden rounded-full">
        <div className="bg-ad-caution" style={{ width: `${(inside / total) * 100}%` }} />
        <div className="bg-ad-brand/45" style={{ width: `${(outside / total) * 100}%` }} />
      </div>
      <div className="mt-3 grid grid-cols-2 gap-3">
        <div className="rounded-2xl border border-ad-caution-border bg-ad-caution-bg p-3">
          <div className="text-xs font-bold text-ad-caution">From their friends</div>
          <div className="mt-0.5 text-xl font-extrabold text-ad-ink">{inside} ratings</div>
          <div className="text-xs text-ad-ink-soft">average {meanIn != null ? `${meanIn.toFixed(1)} ★` : "—"}</div>
        </div>
        <div className="rounded-2xl border border-ad-line bg-ad-soft p-3">
          <div className="text-xs font-bold text-ad-brand">From everyone else</div>
          <div className="mt-0.5 text-xl font-extrabold text-ad-ink">{outside} ratings</div>
          <div className="text-xs text-ad-ink-soft">average {meanOut != null ? `${meanOut.toFixed(1)} ★` : "—"}</div>
        </div>
      </div>
    </div>
  );
}
