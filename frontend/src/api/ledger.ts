import { api } from "../lib/api";

export interface EarningsSummary {
  balance: number;
  week_total: number;
  week_runs: number;
}

export async function fetchEarnings(): Promise<EarningsSummary> {
  return (await api.get<EarningsSummary>("/ledger/me")).data;
}

export interface LedgerEntry {
  seq: number;
  entry_type: string;
  amount: number;
  errand_id: string | null;
  created_at: string;
}

export interface Wallet {
  balance: number;
  entries: LedgerEntry[];
}

export async function fetchWallet(): Promise<Wallet> {
  return (await api.get<Wallet>("/ledger/wallet")).data;
}

export async function topupWallet(amount: number): Promise<Wallet> {
  return (await api.post<Wallet>("/ledger/wallet/topup", { amount })).data;
}

export interface Quote {
  item_total: number;
  runner_fee: number;
  convenience_fee: number;
  total: number;
}

export async function fetchQuote(params: {
  drop_lat: number;
  drop_lng: number;
  item_total?: number;
  tip?: number;
}): Promise<Quote> {
  return (await api.post<Quote>("/ledger/quote", params)).data;
}

export interface LedgerVerify {
  campus_id: string;
  intact: boolean;
  entries: number;
  broken_seq: number | null;
  reason: string | null;
}

export async function verifyLedger(): Promise<LedgerVerify> {
  return (await api.get<LedgerVerify>("/ledger/verify")).data;
}
