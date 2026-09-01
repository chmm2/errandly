import { api } from "../lib/api";

/**
 * One movement of money. `direction` is from the wallet's point of view:
 * CREDIT is money arriving, DEBIT is money leaving.
 */
export interface LedgerEntry {
  id: string;
  errand_id: string | null;
  /** TOPUP | HOLD | REFUND | REWARD | REIMBURSEMENT | REVIEW_REFUND | CLAWBACK */
  entry_type: string;
  direction: "CREDIT" | "DEBIT";
  amount: number;
  memo: string | null;
  created_at: string;
}

export interface Wallet {
  balance: number;
  /** Ring-fenced against errands in flight. Already out of `balance`. */
  held: number;
  recent: LedgerEntry[];
}

export async function fetchWallet(): Promise<Wallet> {
  const { data } = await api.get<Wallet>("/ledger/me/wallet");
  return data;
}

/** Development-only on the backend; the production door is a gateway callback. */
export async function topUp(amount: number): Promise<Wallet> {
  const { data } = await api.post<Wallet>("/ledger/me/topup", { amount });
  return data;
}

export interface Escrow {
  errand_id: string;
  items_total: number;
  reward: number;
  collect_amount: number;
  /** Headroom included in `amount`, over and above the estimate. */
  buffer: number;
  /** The hard ceiling: what the requester locked, and all that can be paid. */
  amount: number;
  released_amount: number;
  status: "HELD" | "RELEASED" | "REFUNDED" | "PENDING_REVIEW";
  created_at: string;
  settled_at: string | null;
}

/** The receipt for one order. Visible to the two parties and admins only. */
export async function fetchEscrow(errandId: string): Promise<Escrow> {
  const { data } = await api.get<Escrow>(`/ledger/errands/${errandId}/escrow`);
  return data;
}
