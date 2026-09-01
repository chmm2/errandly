import { api } from "../lib/api";

/** One line of what the runner actually paid at the counter. */
export interface ClaimLine {
  name: string;
  unit_price: number;
  quantity: number;
}

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
  /** OK | ELEVATED | FLAGGED | NO_REFERENCE */
  verdict: string;
  eligible_amount: number;
}

export interface ClaimResult {
  claims: Claim[];
  total_claimed: number;
  total_eligible: number;
  /** Claimed minus eligible — held back pending review, stated plainly. */
  withheld: number;
  message: string | null;
}

export async function submitClaims(
  errandId: string,
  lines: ClaimLine[],
): Promise<ClaimResult> {
  const { data } = await api.post<ClaimResult>(`/fraud/errands/${errandId}/claims`, {
    lines,
  });
  return data;
}

export interface Strike {
  id: string;
  level: number;
  action: string;
  reason: string;
  expires_at: string | null;
  lifted_at: string | null;
  created_at: string;
}

/** A runner's own record — visible to them, because someone being penalised
 *  by a system is owed a way to see what it thinks they did. */
export interface Standing {
  flags_in_window: number;
  strikes: Strike[];
  blocked_until: string | null;
  next_action_at: number | null;
}

export async function fetchStanding(): Promise<Standing> {
  const { data } = await api.get<Standing>("/fraud/me/standing");
  return data;
}

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
 * mechanism the whole table exists to enforce.
 */
export async function searchReferences(q: string): Promise<ReferenceSuggestion[]> {
  const { data } = await api.get<ReferenceSuggestion[]>("/fraud/references/search", {
    params: { q, limit: 8 },
  });
  return data;
}
