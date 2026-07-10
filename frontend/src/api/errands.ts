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
  status: ErrandStatus;
  version: number;
  accepted_at: string | null;
  delivered_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  created_at: string;
}

export interface ErrandCreate {
  category: Category;
  title: string;
  notes?: string;
  pickup_label: string;
  drop_lat: number;
  drop_lng: number;
  drop_label?: string;
  reward: number;
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

export async function fetchFeed(limit = 20, offset = 0): Promise<ErrandFeed> {
  return (await api.get<ErrandFeed>("/errands", { params: { limit, offset } })).data;
}

export async function fetchMyErrands(): Promise<MyErrands> {
  return (await api.get<MyErrands>("/errands/mine")).data;
}

export async function cancelErrand(id: string, reason?: string): Promise<Errand> {
  return (await api.post<Errand>(`/errands/${id}/cancel`, reason ? { reason } : {})).data;
}
