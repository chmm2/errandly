import { api } from "../lib/api";

export type Category =
  | "FOOD"
  | "GROCERY"
  | "PARCEL"
  | "STATIONERY"
  | "PHARMACY"
  | "CUSTOM";

export type ErrandStatus =
  | "OPEN"
  | "ACCEPTED"
  | "IN_PROGRESS"
  | "DELIVERED"
  | "COMPLETED"
  | "CANCELLED"
  | "EXPIRED";

export type FulfillmentType = "CATALOG" | "GATE_PICKUP" | "PARCEL_POINT";

export interface RunnerSummary {
  id: string;
  display_name: string;
  reputation_score: number;
  rating_count: number;
  trips_completed: number;
  photo_url: string | null;
  phone: string | null;
}

export interface Errand {
  id: string;
  campus_id: string;
  requester_id: string;
  runner_id: string | null;
  category: Category;
  title: string;
  notes: string | null;
  pickup_label: string;
  drop_lat: number;
  drop_lng: number;
  drop_label: string | null;
  reward: number;
  fulfillment_type: FulfillmentType;
  collect_amount: number;
  has_handoff_secret: boolean;
  distance_m: number | null;
  runner_lat: number | null;
  runner_lng: number | null;
  runner: RunnerSummary | null;
  vendor_id: string | null;
  items: OrderLine[];
  items_total: number;
  rated: boolean;
  status: ErrandStatus;
  version: number;
  accepted_at: string | null;
  delivered_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  created_at: string;
}

export interface OrderLine {
  id: string;
  menu_item_id: string | null;
  name_snapshot: string;
  unit_price_snapshot: number;
  quantity: number;
}

export interface ErrandCreate {
  category: Category;
  vendor_id?: string;
  items?: { menu_item_id: string; quantity: number }[];
  title: string;
  notes?: string;
  pickup_label: string;
  drop_lat: number;
  drop_lng: number;
  drop_label?: string;
  reward: number;
  external_ref?: string;
  otp?: string;
  collect_amount?: number;
}

export interface HandoffSecret {
  otp: string | null;
  external_ref: string | null;
  collect_amount: number;
}

export interface ErrandEvent {
  id: string;
  actor_id: string | null;
  event_type: string;
  payload: Record<string, unknown> | null;
  created_at: string;
}

export interface ErrandFeed {
  items: Errand[];
  limit: number;
  offset: number;
  total: number;
}

export interface MyErrands {
  requested: Errand[];
  running: Errand[];
}

export async function createErrand(data: ErrandCreate): Promise<Errand> {
  return (await api.post<Errand>("/errands", data)).data;
}

export async function fetchFeed(
  limit = 20,
  offset = 0,
  near?: { lat: number; lng: number },
): Promise<ErrandFeed> {
  return (
    await api.get<ErrandFeed>("/errands", { params: { limit, offset, ...near } })
  ).data;
}

export async function fetchMyErrands(): Promise<MyErrands> {
  return (await api.get<MyErrands>("/errands/mine")).data;
}

export async function cancelErrand(id: string, reason?: string): Promise<Errand> {
  return (await api.post<Errand>(`/errands/${id}/cancel`, reason ? { reason } : {})).data;
}

export async function acceptErrand(id: string): Promise<Errand> {
  return (await api.post<Errand>(`/errands/${id}/accept`)).data;
}

export async function pickupErrand(id: string): Promise<Errand> {
  return (await api.post<Errand>(`/errands/${id}/pickup`)).data;
}

export async function deliverErrand(id: string): Promise<Errand> {
  return (await api.post<Errand>(`/errands/${id}/deliver`)).data;
}

export async function completeErrand(id: string): Promise<Errand> {
  return (await api.post<Errand>(`/errands/${id}/complete`)).data;
}

export async function fetchHandoffSecret(id: string): Promise<HandoffSecret> {
  return (await api.get<HandoffSecret>(`/errands/${id}/handoff-secret`)).data;
}

export async function rateErrand(id: string, stars: number, comment?: string): Promise<void> {
  await api.post(`/errands/${id}/rate`, { stars, comment });
}
