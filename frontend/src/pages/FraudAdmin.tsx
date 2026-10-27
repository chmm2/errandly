import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  FLAG_KIND,
  fetchAliases,
  fetchCase,
  fetchFlags,
  fetchOverview,
  fetchProposals,
  fetchReferences,
  reviewFlag,
  sweepCollusion,
  sweepRatingFarming,
  type Flag,
  type FlagKind,
} from "../api/fraud";
import { apiErrorMessage } from "../lib/api";
import { useAuth } from "../stores/auth";
import CaseView from "./admin/CaseView";
import { AliasesTab, PricesTab, ProposalsTab } from "./admin/ManageTabs";
import { Icon, KIND, KindBadge, SeverityDots, rupees, timeAgo } from "./admin/ui";

/* The admin console. Everything the system flags lands in one queue, and
   opening a flag shows what happened, why, and the history behind it. The
   queue polls every few seconds so a flag raised from the app shows up
   without anyone refreshing. */

// How often the queue and the totals are re-read. Price flags are written in
// the same request as the runner's report, so this is the whole delay
// between a flag being raised in the app and it appearing here.
const LIVE_MS = 3000;
// How long a newly arrived flag keeps its "New" badge.
const FRESH_MS = 90_000;

type Tab = "flags" | "proposals" | "prices" | "aliases";
type Filter = "all" | FlagKind;

interface Toast {
  id: number;
  tone: "new" | "done" | "error";
  title: string;
  body?: string;
  flagId?: string;
}

const kindOf = (f: Flag): FlagKind => FLAG_KIND[f.rule] ?? "other";

export default function FraudAdmin() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const user = useAuth((s) => s.user);
  const logout = useAuth((s) => s.logout);

  const [tab, setTab] = useState<Tab>("flags");
  const [filter, setFilter] = useState<Filter>("all");
  const [selected, setSelected] = useState<string | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [fresh, setFresh] = useState<Record<string, number>>({});
  const [, setTick] = useState(0);
  const seen = useRef<Set<string> | null>(null);
  const toastId = useRef(0);
  const detailRef = useRef<HTMLDivElement>(null);

  const live = { refetchInterval: LIVE_MS, refetchIntervalInBackground: true } as const;
  const flagsQ = useQuery({ queryKey: ["flags"], queryFn: () => fetchFlags("OPEN"), ...live });
  const overviewQ = useQuery({ queryKey: ["overview"], queryFn: fetchOverview, ...live });
  const proposalsQ = useQuery({ queryKey: ["proposals"], queryFn: () => fetchProposals("PENDING"), refetchInterval: 15_000 });
  const referencesQ = useQuery({ queryKey: ["references"], queryFn: fetchReferences });
  const aliasesQ = useQuery({ queryKey: ["aliases"], queryFn: () => fetchAliases("PENDING"), refetchInterval: 15_000 });

  // A ring is stored as one flag per member but is one case to review, so the
  // queue shows it once. Deciding it closes every member's flag.
  // The member flags share a timestamp, so the one that stands for the ring is
  // picked by id: picking by position would swap it between polls and make
  // the same ring look new every few seconds.
  const flags = useMemo(() => {
    const all = flagsQ.data ?? [];
    const pick = new Map<string, string>();
    for (const f of all) {
      const sig = f.rule === "COLLUSION_RING" ? f.details?.signature : undefined;
      if (sig && (!pick.has(sig) || f.id < pick.get(sig)!)) pick.set(sig, f.id);
    }
    return all.filter((f) => {
      const sig = f.rule === "COLLUSION_RING" ? f.details?.signature : undefined;
      return !sig || pick.get(sig) === f.id;
    });
  }, [flagsQ.data]);
  const visible = useMemo(
    () => (filter === "all" ? flags : flags.filter((f) => kindOf(f) === filter)),
    [flags, filter],
  );
  const counts = useMemo(() => {
    const c: Partial<Record<FlagKind, number>> = {};
    for (const f of flags) c[kindOf(f)] = (c[kindOf(f)] ?? 0) + 1;
    return c;
  }, [flags]);

  const caseQ = useQuery({
    queryKey: ["case", selected],
    queryFn: () => fetchCase(selected!),
    enabled: !!selected,
    refetchInterval: 10_000,
  });

  function pushToast(t: Omit<Toast, "id">) {
    const id = ++toastId.current;
    setToasts((prev) => [...prev.slice(-3), { ...t, id }]);
    window.setTimeout(() => setToasts((prev) => prev.filter((x) => x.id !== id)), 7000);
  }

  function open(id: string) {
    setTab("flags");
    setSelected(id);
    if (window.innerWidth < 1024) {
      window.setTimeout(() => detailRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
    }
  }

  // "checked Ns ago" and the fading New badges need a clock.
  useEffect(() => {
    const t = window.setInterval(() => setTick((n) => n + 1), 1000);
    return () => window.clearInterval(t);
  }, []);

  // Anything not in the previous poll has just been raised: badge it and say so.
  useEffect(() => {
    if (!flagsQ.data) return;
    const ids = new Set(flags.map((f) => f.id));
    if (seen.current === null) {
      seen.current = ids;
      return;
    }
    const arrived = flags.filter((f) => !seen.current!.has(f.id));
    seen.current = ids;
    if (!arrived.length) return;
    const now = Date.now();
    setFresh((prev) => ({ ...prev, ...Object.fromEntries(arrived.map((f) => [f.id, now])) }));
    for (const f of arrived.slice(0, 3)) {
      pushToast({
        tone: "new",
        title: `New ${KIND[kindOf(f)].label.toLowerCase()} flag`,
        body: `${f.subject_name ?? "A student"} · ${f.headline ?? ""}`,
        flagId: f.id,
      });
    }
  }, [flags, flagsQ.data]);

  // Always have something open while there is something to open.
  useEffect(() => {
    if (!visible.length) {
      if (selected && !flags.some((f) => f.id === selected)) setSelected(null);
      return;
    }
    if (!selected || !visible.some((f) => f.id === selected)) setSelected(visible[0].id);
  }, [visible, flags, selected]);

  const review = useMutation({
    mutationFn: ({ id, uphold }: { id: string; uphold: boolean }) => reviewFlag(id, uphold),
    onSuccess: (_flag, { id, uphold }) => {
      const i = visible.findIndex((f) => f.id === id);
      const next = visible[i + 1] ?? visible[i - 1];
      const who = visible[i]?.subject_name ?? "the student";
      setSelected(next ? next.id : null);
      pushToast({
        tone: "done",
        title: uphold ? "Flag upheld" : "Flag dismissed",
        body: `Saved for ${who}.${next ? " Showing the next one." : ""}`,
      });
      for (const key of ["flags", "overview", "case"]) qc.invalidateQueries({ queryKey: [key] });
    },
    onError: (e) => pushToast({ tone: "error", title: "Couldn't save that decision", body: apiErrorMessage(e, "Try again.") }),
  });

  const ringSweep = useMutation({
    mutationFn: sweepCollusion,
    onSuccess: (raised) => {
      pushToast({
        tone: raised.length ? "new" : "done",
        title: raised.length ? `${raised.length} new ring flag${raised.length === 1 ? "" : "s"}` : "No new rings found",
        body: "Checked every group of friends for money going round in a loop.",
      });
      qc.invalidateQueries({ queryKey: ["flags"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
    },
    onError: (e) => pushToast({ tone: "error", title: "Ring check failed", body: apiErrorMessage(e, "Try again.") }),
  });
  const ratingSweep = useMutation({
    mutationFn: sweepRatingFarming,
    onSuccess: (raised) => {
      pushToast({
        tone: raised.length ? "new" : "done",
        title: raised.length ? `${raised.length} new ratings flag${raised.length === 1 ? "" : "s"}` : "No new rating problems",
        body: "Checked whose rating comes mostly from their own friends.",
      });
      qc.invalidateQueries({ queryKey: ["flags"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
    },
    onError: (e) => pushToast({ tone: "error", title: "Ratings check failed", body: apiErrorMessage(e, "Try again.") }),
  });

  const ov = overviewQ.data;
  const checkedAgo = flagsQ.dataUpdatedAt ? Math.max(0, Math.round((Date.now() - flagsQ.dataUpdatedAt) / 1000)) : null;
  const offline = flagsQ.isError;

  const tabs: [Tab, string, number][] = [
    ["flags", "Flags", flags.length],
    ["proposals", "Price changes", proposalsQ.data?.length ?? 0],
    ["prices", "Usual prices", referencesQ.data?.length ?? 0],
    ["aliases", "Item names", aliasesQ.data?.length ?? 0],
  ];
  const filters: [Filter, string][] = [
    ["all", "All"],
    ...(["price", "pattern", "payout", "ring", "ratings"] as FlagKind[])
      .filter((k) => counts[k])
      .map((k) => [k, KIND[k].plural] as [Filter, string]),
  ];

  return (
    <div className="min-h-screen bg-ad-soft font-jakarta text-ad-ink">
      {/* ---------------------------------------------------------- top bar */}
      <header className="sticky top-0 z-30 bg-ad-deep text-white">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between gap-3 px-4">
          <div className="flex items-center gap-2.5">
            <span className="inline-flex h-8 w-8 items-center justify-center rounded-xl bg-white/15 text-lg font-extrabold">e</span>
            <span className="text-lg font-extrabold tracking-tight">errandly</span>
            <span className="rounded-full bg-white/15 px-2.5 py-0.5 text-xs font-bold text-white/85">Admin</span>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <span
              className="hidden items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-xs font-bold sm:inline-flex"
              title="The queue checks for new flags every 3 seconds"
            >
              <span className={`h-2 w-2 rounded-full ${offline ? "bg-ad-money-light" : "ad-live bg-ad-credit-light"}`} />
              {offline ? "Can't reach the server" : `Live · checked ${checkedAgo ?? 0}s ago`}
            </span>
            <span className="hidden text-white/70 md:inline">{user?.display_name}</span>
            <button
              onClick={() => {
                logout();
                navigate("/login");
              }}
              className="inline-flex items-center gap-1.5 rounded-xl bg-white/10 px-3 py-1.5 text-xs font-bold transition hover:bg-white/20"
            >
              <Icon name="logout" className="h-4 w-4" />
              Log out
            </button>
          </div>
        </div>
      </header>

      {/* ------------------------------------------------------------- hero */}
      <section className="relative overflow-hidden bg-[linear-gradient(135deg,#2F5A5B_0%,#274A4C_45%,#16302F_100%)] text-white">
        <div className="ad-drift pointer-events-none absolute -top-40 -right-24 h-[460px] w-[460px] rounded-full bg-white/5" />
        <div className="ad-drift-slow pointer-events-none absolute -bottom-36 left-[8%] h-72 w-72 rounded-full bg-[rgba(192,128,60,0.13)]" />
        <div className="relative mx-auto max-w-7xl px-4 pt-9 pb-24">
          <div className="text-xs font-bold uppercase tracking-[0.18em] text-white/60">Admin · VIT Vellore</div>
          <h1 className="mt-1.5 text-4xl font-extrabold tracking-tight sm:text-5xl">Fraud review</h1>
          <p className="mt-2 max-w-2xl text-[15px] text-white/80">
            Every flag waits here for a person. Open one to see what happened, why the system flagged it, and the
            history behind it. Nothing is decided without you.
          </p>
        </div>
      </section>

      {/* ------------------------------------------------------- totals */}
      <div className="relative z-10 mx-auto -mt-16 max-w-7xl px-4">
        <div className="grid grid-cols-2 gap-px overflow-hidden rounded-[22px] bg-ad-line shadow-[0_14px_26px_rgba(23,32,31,0.14)] lg:grid-cols-4">
          <Tile
            label="Waiting for you"
            value={ov ? String(ov.open) : "—"}
            sub={
              ov
                ? (["price", "pattern", "payout", "ring", "ratings"] as FlagKind[])
                    .filter((k) => ov.by_kind[k])
                    .map((k) => `${ov.by_kind[k]} ${KIND[k].label.toLowerCase()}`)
                    .join(" · ") || "Nothing open"
                : ""
            }
          />
          <Tile label="Held from price reports" value={ov ? rupees(ov.withheld) : "—"} money sub="Paid out or returned when you decide" />
          <Tile label="Payouts frozen" value={ov ? rupees(ov.frozen) : "—"} money sub="Went over the money locked" />
          <Tile label="People flagged" value={ov ? String(ov.people) : "—"} sub={ov?.latest_at ? `Latest ${timeAgo(ov.latest_at)}` : ""} />
        </div>

        {/* -------------------------------------------------------- tabs */}
        <nav className="mt-5 flex gap-1 overflow-x-auto rounded-2xl border border-ad-line bg-white p-1" aria-label="Admin sections">
          {tabs.map(([key, label, count]) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`flex shrink-0 items-center gap-2 rounded-xl px-4 py-2 text-sm font-bold transition ${
                tab === key ? "bg-ad-brand text-white shadow-[0_8px_14px_rgba(39,74,76,0.3)]" : "text-ad-muted hover:bg-ad-wash hover:text-ad-brand"
              }`}
            >
              {label}
              {count > 0 && (
                <span className={`rounded-full px-1.5 text-xs ${tab === key ? "bg-white/20" : "bg-ad-chip"}`}>{count}</span>
              )}
            </button>
          ))}
        </nav>
      </div>

      <main className="mx-auto max-w-7xl px-4 pt-5 pb-16">
        {tab === "flags" &&
          (flags.length === 0 ? (
            <div className="rounded-[22px] border border-ad-line bg-white px-6 py-14 text-center">
              <span className="mx-auto inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-ad-credit-bg text-ad-credit">
                <Icon name="check" className="h-7 w-7" />
              </span>
              <p className="mt-3 text-lg font-extrabold">All clear</p>
              <p className="mx-auto mt-1 max-w-md text-sm text-ad-muted">
                Nothing is waiting. A new flag from the app shows up here within a few seconds, no refresh needed.
              </p>
              <SweepButtons ring={ringSweep} rating={ratingSweep} />
            </div>
          ) : (
            <div className="grid gap-5 lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
              {/* ------------------------------------------------ queue */}
              <aside className="lg:sticky lg:top-[4.5rem] lg:self-start">
                <div className="rounded-[22px] border border-ad-line bg-white">
                  <div className="border-b border-ad-hair p-4">
                    <div className="flex items-center justify-between">
                      <h2 className="text-[15px] font-extrabold">Queue</h2>
                      <span className="text-xs text-ad-muted">newest first</span>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {filters.map(([key, label]) => (
                        <button
                          key={key}
                          onClick={() => setFilter(key)}
                          className={`rounded-full px-3 py-1 text-xs font-bold transition ${
                            filter === key ? "bg-ad-brand text-white" : "bg-ad-chip text-ad-ink-soft hover:bg-ad-tint"
                          }`}
                        >
                          {label} {key === "all" ? flags.length : counts[key as FlagKind]}
                        </button>
                      ))}
                    </div>
                  </div>
                  <ul className="max-h-[calc(100vh-17rem)] space-y-1 overflow-y-auto p-2">
                    {visible.map((f) => {
                      const k = kindOf(f);
                      const isFresh = fresh[f.id] && Date.now() - fresh[f.id] < FRESH_MS;
                      const active = f.id === selected;
                      return (
                        <li key={f.id} className={isFresh ? "ad-arrive" : ""}>
                          <button
                            onClick={() => open(f.id)}
                            aria-current={active ? "true" : undefined}
                            className={`flex w-full gap-3 rounded-2xl border p-3 text-left transition focus-visible:outline-2 focus-visible:outline-ad-brand ${
                              active
                                ? "border-ad-brand/40 bg-ad-wash shadow-[0_6px_14px_rgba(23,32,31,0.06)]"
                                : "border-transparent hover:bg-ad-soft"
                            }`}
                          >
                            <KindBadge kind={k} />
                            <span className="min-w-0 flex-1">
                              <span className="flex items-center justify-between gap-2">
                                <span className="truncate text-sm font-extrabold text-ad-ink">{f.subject_name ?? "Unknown student"}</span>
                                <span className="shrink-0 text-[11px] text-ad-muted">{timeAgo(f.created_at)}</span>
                              </span>
                              <span className="mt-0.5 block truncate text-[13px] text-ad-ink-soft">{f.headline}</span>
                              <span className="mt-1 flex items-center gap-2">
                                <span className={`text-[11px] font-bold ${KIND[k].tone}`}>{KIND[k].label}</span>
                                <SeverityDots level={f.severity} />
                                {isFresh && (
                                  <span className="rounded-full bg-ad-money px-1.5 py-px text-[10px] font-extrabold uppercase text-white">New</span>
                                )}
                              </span>
                            </span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                  <div className="border-t border-ad-hair p-3">
                    <SweepButtons ring={ringSweep} rating={ratingSweep} compact />
                  </div>
                </div>
              </aside>

              {/* ------------------------------------------------ case */}
              <div ref={detailRef} className="min-w-0 scroll-mt-20">
                {caseQ.data && caseQ.data.flag_id === selected ? (
                  <CaseView
                    data={caseQ.data}
                    busy={review.isPending}
                    onDecide={(uphold) => review.mutate({ id: caseQ.data!.flag_id, uphold })}
                  />
                ) : caseQ.isError ? (
                  <div className="rounded-[22px] border border-ad-caution-border bg-ad-caution-bg p-6 text-sm text-ad-caution">
                    {apiErrorMessage(caseQ.error, "Couldn't load this flag.")}
                  </div>
                ) : (
                  <CaseSkeleton />
                )}
              </div>
            </div>
          ))}

        {tab === "proposals" && <ProposalsTab />}
        {tab === "prices" && <PricesTab />}
        {tab === "aliases" && <AliasesTab />}
      </main>

      {/* ------------------------------------------------------------ toasts */}
      <div className="pointer-events-none fixed right-4 bottom-4 z-50 flex w-[min(360px,calc(100vw-2rem))] flex-col gap-2" aria-live="polite">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`ad-toast pointer-events-auto rounded-2xl border p-3.5 shadow-[0_14px_26px_rgba(23,32,31,0.18)] ${
              t.tone === "new"
                ? "border-ad-money/40 bg-ad-deep text-white"
                : t.tone === "error"
                  ? "border-ad-caution-border bg-ad-caution-bg text-ad-caution"
                  : "border-ad-line bg-white text-ad-ink"
            }`}
          >
            <div className="flex items-start gap-2.5">
              <Icon name={t.tone === "new" ? "bolt" : t.tone === "error" ? "x" : "check"} className="mt-0.5 h-5 w-5 shrink-0" />
              <div className="min-w-0 flex-1">
                <div className="text-sm font-extrabold">{t.title}</div>
                {t.body && <div className={`text-xs ${t.tone === "new" ? "text-white/75" : "opacity-80"}`}>{t.body}</div>}
                {t.flagId && (
                  <button onClick={() => open(t.flagId!)} className="mt-1.5 text-xs font-extrabold text-ad-money-light hover:underline">
                    Open it
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Tile({ label, value, sub, money = false }: { label: string; value: string; sub?: string; money?: boolean }) {
  return (
    <div className="bg-white px-5 py-4">
      <div className="text-[11px] font-bold uppercase tracking-wider text-ad-muted">{label}</div>
      <div className={`mt-1 text-3xl font-extrabold tracking-tight ${money ? "text-ad-money-text" : "text-ad-ink"}`}>{value}</div>
      {sub && <div className="mt-0.5 truncate text-xs text-ad-muted">{sub}</div>}
    </div>
  );
}

function SweepButtons({
  ring,
  rating,
  compact = false,
}: {
  ring: { mutate: () => void; isPending: boolean };
  rating: { mutate: () => void; isPending: boolean };
  compact?: boolean;
}) {
  const cls =
    "inline-flex items-center justify-center gap-1.5 rounded-xl border border-ad-outline bg-white px-3 py-2 text-xs font-bold text-ad-ink-soft transition hover:border-ad-brand hover:text-ad-brand disabled:opacity-50";
  return (
    <div className={compact ? "grid grid-cols-2 gap-2" : "mt-5 flex flex-wrap justify-center gap-2"}>
      <button onClick={() => ring.mutate()} disabled={ring.isPending} className={cls}>
        <Icon name="ring" className="h-4 w-4" />
        {ring.isPending ? "Checking…" : "Check for rings now"}
      </button>
      <button onClick={() => rating.mutate()} disabled={rating.isPending} className={cls}>
        <Icon name="ratings" className="h-4 w-4" />
        {rating.isPending ? "Checking…" : "Check ratings now"}
      </button>
    </div>
  );
}

function CaseSkeleton() {
  return (
    <div className="space-y-4" aria-busy="true">
      {[120, 180, 260].map((h) => (
        <div key={h} className="animate-pulse rounded-[22px] border border-ad-line bg-white" style={{ height: h }} />
      ))}
    </div>
  );
}
