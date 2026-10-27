import type { ReactNode } from "react";

import type { FlagKind, Verdict } from "../../api/fraud";

/* Small shared pieces for the admin console: formatting, icons and pills.
   Colours follow the mobile revamp: teal for the product, copper only where
   money is involved, and the caution red for things a person must look at. */

export function rupees(n: number | null | undefined): string {
  if (n == null || Number.isNaN(Number(n))) return "₹—";
  const v = Number(n);
  return Math.abs(v - Math.round(v)) < 0.005
    ? `₹${Math.round(v).toLocaleString("en-IN")}`
    : `₹${v.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "";
  const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 45) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24);
  return d < 60 ? `${d}d ago` : shortDate(iso);
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString("en-IN", {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  });
}

export const KIND: Record<
  FlagKind,
  { label: string; plural: string; tone: string; soft: string }
> = {
  price: {
    label: "Price",
    plural: "Prices",
    tone: "text-ad-money-text",
    soft: "bg-ad-warn-bg border-ad-warn-border",
  },
  pattern: {
    label: "Pattern",
    plural: "Patterns",
    tone: "text-ad-warn-text",
    soft: "bg-ad-warn-bg border-ad-warn-border",
  },
  payout: {
    label: "Payout",
    plural: "Payouts",
    tone: "text-ad-money-text",
    soft: "bg-ad-warn-bg border-ad-warn-border",
  },
  ring: {
    label: "Ring",
    plural: "Rings",
    tone: "text-ad-caution",
    soft: "bg-ad-caution-bg border-ad-caution-border",
  },
  ratings: {
    label: "Ratings",
    plural: "Ratings",
    tone: "text-ad-brand",
    soft: "bg-ad-tint border-ad-line",
  },
  other: { label: "Other", plural: "Other", tone: "text-ad-muted", soft: "bg-ad-chip border-ad-line" },
};

const PATHS: Record<string, ReactNode> = {
  price: (
    <>
      <path d="M3.5 12.2V4.5a1 1 0 0 1 1-1h7.7l8.3 8.3a1 1 0 0 1 0 1.4l-7.3 7.3a1 1 0 0 1-1.4 0z" />
      <circle cx="8" cy="8" r="1.4" />
    </>
  ),
  pattern: <path d="M3 13h3.5l2.5-7 4 13 2.5-8H21" />,
  payout: (
    <>
      <rect x="4.5" y="10.5" width="15" height="10" rx="2.2" />
      <path d="M8 10.5V7.5a4 4 0 0 1 8 0v3" />
    </>
  ),
  ring: (
    <>
      <path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3" />
      <path d="M19.5 3.8v3.6h-3.6" />
    </>
  ),
  ratings: (
    <path d="M12 3.6l2.6 5.3 5.8.8-4.2 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8L3.6 9.7l5.8-.8z" />
  ),
  other: <circle cx="12" cy="12" r="7.5" />,
  shield: <path d="M12 3l7.5 3v5.6c0 4.4-3.1 8.2-7.5 9.4-4.4-1.2-7.5-5-7.5-9.4V6z" />,
  check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  x: <path d="M6.5 6.5l11 11M17.5 6.5l-11 11" />,
  clock: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </>
  ),
  user: (
    <>
      <circle cx="12" cy="8.5" r="3.8" />
      <path d="M4.5 20c1.3-3.6 4.2-5.4 7.5-5.4s6.2 1.8 7.5 5.4" />
    </>
  ),
  bag: (
    <>
      <path d="M5.5 8h13l-1 12h-11z" />
      <path d="M9 8V6.5a3 3 0 0 1 6 0V8" />
    </>
  ),
  history: (
    <>
      <path d="M4 12a8 8 0 1 0 2.4-5.7" />
      <path d="M4 4.5V8h3.5" />
      <path d="M12 8v4.2l2.8 1.8" />
    </>
  ),
  bolt: <path d="M13 3L5 13.5h6L10 21l8-10.5h-6z" />,
  logout: (
    <>
      <path d="M14 4.5h4a1.5 1.5 0 0 1 1.5 1.5v12a1.5 1.5 0 0 1-1.5 1.5h-4" />
      <path d="M10 8l-4 4 4 4M6 12h9" />
    </>
  ),
};

export function Icon({ name, className = "h-5 w-5" }: { name: string; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {PATHS[name] ?? PATHS.other}
    </svg>
  );
}

export function KindBadge({ kind, big = false }: { kind: FlagKind; big?: boolean }) {
  const k = KIND[kind] ?? KIND.other;
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-2xl border ${k.soft} ${k.tone} ${
        big ? "h-12 w-12" : "h-10 w-10"
      }`}
    >
      <Icon name={kind} className={big ? "h-6 w-6" : "h-5 w-5"} />
    </span>
  );
}

export function SeverityDots({ level }: { level: number }) {
  return (
    <span className="inline-flex items-center gap-1" title={`Severity ${level} of 3`}>
      {[1, 2, 3].map((i) => (
        <span
          key={i}
          className={`h-1.5 w-1.5 rounded-full ${
            i <= level ? (level >= 3 ? "bg-ad-caution" : "bg-ad-money") : "bg-ad-line"
          }`}
        />
      ))}
    </span>
  );
}

const VERDICT_STYLE: Record<Verdict, [string, string]> = {
  OK: ["Normal", "bg-ad-credit-bg text-ad-credit"],
  ELEVATED: ["A bit high, paid", "bg-ad-warn-bg text-ad-warn-text"],
  FLAGGED: ["Over the limit", "bg-ad-caution-bg text-ad-caution"],
  NO_REFERENCE: ["No usual price", "bg-ad-chip text-ad-muted"],
};

export function VerdictPill({ verdict }: { verdict: Verdict }) {
  const [label, cls] = VERDICT_STYLE[verdict] ?? ["?", "bg-ad-chip text-ad-muted"];
  return (
    <span className={`inline-block whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-bold ${cls}`}>
      {label}
    </span>
  );
}

export function Panel({
  title,
  icon,
  hint,
  children,
  className = "",
}: {
  title: string;
  icon?: string;
  hint?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-[22px] border border-ad-line bg-white p-5 ${className}`}>
      <div className="mb-3 flex items-start gap-2.5">
        {icon && (
          <span className="mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-xl bg-ad-tint text-ad-brand">
            <Icon name={icon} className="h-4 w-4" />
          </span>
        )}
        <div className="min-w-0">
          <h3 className="text-[15px] font-extrabold text-ad-ink">{title}</h3>
          {hint && <p className="text-[13px] leading-snug text-ad-muted">{hint}</p>}
        </div>
      </div>
      {children}
    </section>
  );
}

export function Stat({ label, value, sub }: { label: string; value: ReactNode; sub?: string }) {
  return (
    <div className="rounded-2xl bg-ad-soft px-3.5 py-3">
      <div className="text-[11px] font-bold uppercase tracking-wider text-ad-muted">{label}</div>
      <div className="mt-0.5 text-lg font-extrabold text-ad-ink">{value}</div>
      {sub && <div className="text-xs text-ad-muted">{sub}</div>}
    </div>
  );
}
