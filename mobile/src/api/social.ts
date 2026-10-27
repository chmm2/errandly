import { api } from "../lib/api";

export interface Friend {
  id: string;
  display_name: string;
  photo_url: string | null;
  reputation_score: number;
}

export interface PendingRequest {
  id: string; // the friendship row — this is what you accept or decline
  from_user: Friend;
  created_at: string;
}

/** How you're connected to someone: 1st = friend, 2nd = friend of a friend. */
export interface Connection {
  degree: number | null;
  label: string; // "1st" | "2nd" | "3rd" | "R" | "You"
  via: string | null;
  trust: number;
}

export type Relationship =
  | "NONE"
  | "PENDING_OUT"
  | "PENDING_IN"
  | "FRIENDS"
  | "BLOCKED";

export interface SearchResult extends Friend {
  student_id: string | null;
  relationship: Relationship;
  mutual_friends: number;
}

export async function fetchFriends(): Promise<Friend[]> {
  const { data } = await api.get<Friend[]>("/social/friends");
  return data;
}

export async function fetchRequests(): Promise<PendingRequest[]> {
  const { data } = await api.get<PendingRequest[]>("/social/requests");
  return data;
}

export async function searchStudents(q: string): Promise<SearchResult[]> {
  const { data } = await api.get<SearchResult[]>("/social/search", { params: { q } });
  return data;
}

export async function sendRequest(user_id: string): Promise<void> {
  await api.post("/social/requests", { user_id });
}

export async function respondToRequest(id: string, accept: boolean): Promise<void> {
  await api.post(`/social/requests/${id}/respond`, { accept });
}

export async function unfriend(user_id: string): Promise<void> {
  await api.delete(`/social/friends/${user_id}`);
}

export async function blockUser(user_id: string): Promise<void> {
  await api.post(`/social/block/${user_id}`);
}
