import { api } from "../lib/api";

export interface EarningsSummary {
  /** Money EARNED running — not the wallet balance. Top-ups are excluded. */
  balance: number;
  week_total: number;
  week_runs: number;
}

export interface LedgerEntry {
  id: string;
  errand_id: string | null;
  entry_type:
    | "TOPUP"
    | "HOLD"
    | "REFUND"
    | "REWARD"
    | "REIMBURSEMENT"
    | "REVIEW_PAYOUT"
    | "REVIEW_REFUND"
    | "CLAWBACK";
  direction: "CREDIT" | "DEBIT";
  amount: number;
  memo: string | null;
  created_at: string;
}

export interface Wallet {
  balance: number;
  /** Money already debited and sitting in escrow on live orders. */
  held: number;
  /** Headroom rate the server applies to the ESTIMATED SPEND when holding. */
  buffer_pct: number;
  recent: LedgerEntry[];
}

export interface Escrow {
  errand_id: string;
  items_total: number;
  reward: number;
  collect_amount: number;
  /** Headroom included in `amount`, over and above the estimate. */
  buffer: number;
  amount: number;
  released_amount: number;
  status: "HELD" | "RELEASED" | "REFUNDED" | "PENDING_REVIEW";
  created_at: string;
  settled_at: string | null;
}

export async function fetchEarnings(): Promise<EarningsSummary> {
  return (await api.get<EarningsSummary>("/ledger/me")).data;
}

export async function fetchWallet(): Promise<Wallet> {
  return (await api.get<Wallet>("/ledger/me/wallet")).data;
}

export async function topUp(amount: number): Promise<Wallet> {
  return (await api.post<Wallet>("/ledger/me/topup", { amount })).data;
}

export async function fetchEscrow(errandId: string): Promise<Escrow> {
  return (await api.get<Escrow>(`/ledger/errands/${errandId}/escrow`)).data;
}

/** How each entry type reads to a human, and which way the money went. */
export const ENTRY_LABELS: Record<LedgerEntry["entry_type"], string> = {
  TOPUP: "Added to wallet",
  HOLD: "Held for order",
  REFUND: "Refunded",
  REWARD: "Delivery reward",
  REIMBURSEMENT: "Reimbursed for shopping",
  REVIEW_PAYOUT: "Released after review",
  REVIEW_REFUND: "Overcharge returned",
  CLAWBACK: "Adjustment",
};


export interface HoldQuote {
  /** What the items are expected to cost. */
  spend: number;
  /** Headroom on the spend, refunded in full if the runner does not need it. */
  buffer: number;
  /** Paid to the runner for the trip. Never carries headroom. */
  fee: number;
  /** What actually leaves the available balance when the order is placed. */
  total: number;
}

/**
 * What an order will lock, computed the way the server computes it.
 *
 * The button on a checkout screen has to name the number the wallet will
 * actually move, or the requester watches more money disappear than they
 * agreed to. Headroom applies to the spend alone - the fee is fixed and known,
 * so padding it would reserve money that no outcome could ever need.
 */
export function quoteHold(spend: number, fee: number, bufferPct: number): HoldQuote {
  const round2 = (n: number) => Math.round(n * 100) / 100;
  const safeSpend = Math.max(0, round2(spend || 0));
  const safeFee = Math.max(0, round2(fee || 0));
  const buffer = round2(safeSpend * (bufferPct || 0));
  return {
    spend: safeSpend,
    buffer,
    fee: safeFee,
    total: round2(safeSpend + buffer + safeFee),
  };
}
