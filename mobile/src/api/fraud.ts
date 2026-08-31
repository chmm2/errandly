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
