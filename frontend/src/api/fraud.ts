import { api } from "../lib/api";

// ELEVATED: above the reference but under the rupee line — paid in full,
// but counted toward the "walking the line" pattern check.
export type Verdict = "OK" | "ELEVATED" | "FLAGGED" | "NO_REFERENCE";

export interface Claim {
  id: string;
  errand_id: string;
  raw_name: string;
  item_key: string;
  claimed_unit_price: number;
  quantity: number;
  reference_snapshot: number | null;
  threshold_snapshot: number | null;
  delta_pct: number | null;
  delta_abs: number | null;
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
  tolerance_abs: number;
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
    // CLAIM_ABOVE_REFERENCE
    item?: string | null;
    claimed?: number | null;
    reference?: number | null;
    // Which shop it was bought at. The reference above is store-adjusted, so
    // this is what makes the comparison interpretable to a reviewer.
    store?: string | null;
    // How many distinct runners have priced this item at that shop. Low means
    // the reference is still forming, which is usually why an honest claim
    // looks high.
    store_reports?: number | null;
    delta_pct?: number | null;
    // PERSISTENT_NEAR_THRESHOLD — the evidence is a distribution, not a price
    near_line_claims?: number;
    judged_claims?: number;
    share?: number;
    avg_rupees_over?: number;
    window_days?: number;
    // COLLUSION_RING — the evidence is a closed money cycle between friends
    signature?: string;
    members?: string[];
    names?: string[];
    size?: number;
    laps?: number;
    total_value?: number;
    min_leg_value?: number;
    closure?: number;
    // RATING_FARMING — the evidence is where the praise came from
    concentration?: number;
    in_cluster?: number;
    out_cluster?: number;
    mean_in?: number | null;
    mean_out?: number | null;
    differential?: number | null;
    post_penalty_burst?: number;
    reasons?: string[];
    // Advisory reading of whether those reviews describe real errands. null on
    // the same terms as `semantic` below.
    reviews?: {
      authenticity: number;
      describes_real_errands: boolean;
      template_like: boolean;
      observations: string[];
      reviews_considered: number;
      exculpatory: boolean;
      model: string;
    } | null;
    // Advisory reading of what the group's errands actually say. null when no
    // model was configured, the history was too thin, or the call failed.
    semantic?: {
      coherence: number;
      diversity: number;
      specificity: number;
      reads_as_genuine: boolean;
      observations: string[];
      errands_considered: number;
      exculpatory: boolean;
      model: string;
    } | null;
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
  tolerance_abs: number;
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
    tolerance_abs: number;
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

export async function sweepCollusion(): Promise<Flag[]> {
  return (await api.post<Flag[]>("/fraud/collusion/sweep")).data;
}

export async function sweepRatingFarming(): Promise<Flag[]> {
  return (await api.post<Flag[]>("/fraud/rating-farming/sweep")).data;
}

export async function reviewFlag(
  id: string,
  uphold: boolean,
  note?: string,
): Promise<Flag> {
  return (await api.post<Flag>(`/fraud/flags/${id}/review`, { uphold, note })).data;
}

export interface ItemAlias {
  id: string;
  alias_key: string;
  item_key: string;
  sample_raw_name: string;
  reason: string | null;
  source: "MODEL" | "ADMIN";
  status: "PENDING" | "APPROVED" | "REJECTED";
  created_at: string;
  decided_at: string | null;
}

export async function fetchAliases(status = "PENDING"): Promise<ItemAlias[]> {
  return (await api.get<ItemAlias[]>("/fraud/aliases", { params: { status } })).data;
}

export async function sweepAliases(): Promise<ItemAlias[]> {
  return (await api.post<ItemAlias[]>("/fraud/aliases/sweep")).data;
}

export async function decideAlias(id: string, approve: boolean): Promise<ItemAlias> {
  return (await api.post<ItemAlias>(`/fraud/aliases/${id}/decide`, null, {
    params: { approve },
  })).data;
}

export const STRIKE_LABELS: Record<Strike["action"], string> = {
  WARNING: "Warning",
  REPUTATION_PENALTY: "Rating reduced",
  RUNNER_SUSPENDED: "Running paused",
  ACCOUNT_SUSPENDED: "Account suspended",
};

export interface ReferenceSuggestion {
  reference_id: string;
  item_key: string;
  display_name: string;
  reference_price: number;
  band_min: number;
  band_max: number;
  score: number;
  /** Set when the hit came through an approved alias rather than the name. */
  matched_via: string | null;
}

/**
 * Type-ahead over the admin's non-MRP price list.
 *
 * Fuzzy server-side, so a misspelling still finds the priced item. That
 * matters more than it looks: a typo that misses drops the line back to
 * unpriced free text, and an unpriced line escapes the reference-price
 * mechanism entirely.
 */
export async function searchReferences(q: string): Promise<ReferenceSuggestion[]> {
  const { data } = await api.get<ReferenceSuggestion[]>("/fraud/references/search", {
    params: { q, limit: 8 },
  });
  return data;
}
