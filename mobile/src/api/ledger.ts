import { api } from "../lib/api";

export interface EarningsSummary {
  balance: number;
  week_total: number;
  week_runs: number;
}

export async function fetchEarnings(): Promise<EarningsSummary> {
  return (await api.get<EarningsSummary>("/ledger/me")).data;
}
