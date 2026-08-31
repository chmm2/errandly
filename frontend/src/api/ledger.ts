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
  recent: LedgerEntry[];
}

export interface Escrow {
  errand_id: string;
  items_total: number;
  reward: number;
  collect_amount: number;
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
