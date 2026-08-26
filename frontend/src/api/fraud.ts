import { api } from "../lib/api";

export type Verdict = "OK" | "FLAGGED" | "NO_REFERENCE";

export interface Claim {
  id: string;
  errand_id: string;
  raw_name: string;
  item_key: string;
  claimed_unit_price: number;
  quantity: number;
  reference_snapshot: number | null;
  delta_pct: number | null;
  verdict: Verdict;
  eligible_amount: number;
  created_at: string;
}

export interface ClaimResult {
  claims: Claim[];
  total_claimed: number;
  total_eligible: number;
  /** Money the fraud check refused to release pending admin review. */
  withheld: number;
  message: string | null;
}

export interface ClaimLine {
  name: string;
  unit_price: number;
  quantity: number;
}

export interface Strike {
  id: string;
  level: number;
  action: "WARNING" | "REPUTATION_PENALTY" | "RUNNER_SUSPENDED" | "ACCOUNT_SUSPENDED";
  reason: string;
  expires_at: string | null;
  lifted_at: string | null;
  created_at: string;
}

export interface Standing {
  flags_in_window: number;
  strikes: Strike[];
  blocked_until: string | null;
  /** Flag count at which the next consequence lands, or null if maxed out. */
  next_action_at: number | null;
}

export interface ReferencePrice {
  id: string;
  item_key: string;
  display_name: string;
  reference_price: number;
  band_min: number;
  band_max: number;
  tolerance_pct: number;
  source: "ADMIN" | "AUTO";
  sample_count: number;
  last_estimated_at: string | null;
  updated_at: string;
}

export interface Proposal {
  id: string;
  reference_price_id: string;
  proposed_price: number;
  proposed_band_min: number;
  proposed_band_max: number;
  observed_median: number;
  sample_count: number;
  reason: string;
  status: "PENDING" | "APPROVED" | "REJECTED";
  created_at: string;
}

export interface Flag {
  id: string;
  user_id: string;
  errand_id: string | null;
  claim_id: string | null;
  rule: string;
  severity: number;
  details: {
    item?: string | null;
    claimed?: number | null;
    reference?: number | null;
    delta_pct?: number | null;
  } | null;
  status: "OPEN" | "UPHELD" | "DISMISSED";
  created_at: string;
  reviewed_at: string | null;
}

// ---------------------------------------------------------------- runner

export async function submitClaims(
  errandId: string,
  lines: ClaimLine[],
): Promise<ClaimResult> {
  return (await api.post<ClaimResult>(`/fraud/errands/${errandId}/claims`, { lines })).data;
}

export async function fetchStanding(): Promise<Standing> {
  return (await api.get<Standing>("/fraud/me/standing")).data;
}

// ----------------------------------------------------------------- admin

export async function fetchReferences(): Promise<ReferencePrice[]> {
  return (await api.get<ReferencePrice[]>("/fraud/references")).data;
}

export async function createReference(body: {
  display_name: string;
  reference_price: number;
  band_min: number;
  band_max: number;
  tolerance_pct: number;
}): Promise<ReferencePrice> {
  return (await api.post<ReferencePrice>("/fraud/references", body)).data;
}

export async function updateReference(
  id: string,
  body: Partial<{
    display_name: string;
    reference_price: number;
    band_min: number;
    band_max: number;
    tolerance_pct: number;
  }>,
): Promise<ReferencePrice> {
  return (await api.patch<ReferencePrice>(`/fraud/references/${id}`, body)).data;
}

export async function refreshReferences(): Promise<ReferencePrice[]> {
  return (await api.post<ReferencePrice[]>("/fraud/references/refresh")).data;
}

export async function fetchProposals(status = "PENDING"): Promise<Proposal[]> {
  return (await api.get<Proposal[]>("/fraud/proposals", { params: { status } })).data;
}

export async function approveProposal(id: string): Promise<ReferencePrice> {
  return (await api.post<ReferencePrice>(`/fraud/proposals/${id}/approve`)).data;
}

export async function rejectProposal(id: string): Promise<Proposal> {
  return (await api.post<Proposal>(`/fraud/proposals/${id}/reject`)).data;
}

export async function fetchFlags(status = "OPEN"): Promise<Flag[]> {
  return (await api.get<Flag[]>("/fraud/flags", { params: { status } })).data;
}

export async function reviewFlag(
  id: string,
  uphold: boolean,
  note?: string,
): Promise<Flag> {
  return (await api.post<Flag>(`/fraud/flags/${id}/review`, { uphold, note })).data;
}

export const STRIKE_LABELS: Record<Strike["action"], string> = {
  WARNING: "Warning",
  REPUTATION_PENALTY: "Rating reduced",
  RUNNER_SUSPENDED: "Running paused",
  ACCOUNT_SUSPENDED: "Account suspended",
};
