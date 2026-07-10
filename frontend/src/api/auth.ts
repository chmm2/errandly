import { api } from "../lib/api";
import type { User } from "../stores/auth";

export interface TokenPair {
  access_token: string;
  refresh_token: string;
}

export interface RegisterPayload {
  student_id: string;
  email: string;
  display_name: string;
  password: string;
  phone?: string;
}

export async function register(payload: RegisterPayload): Promise<User> {
  const { data } = await api.post<User>("/auth/register", payload);
  return data;
}

export async function login(email: string, password: string): Promise<TokenPair> {
  const { data } = await api.post<TokenPair>("/auth/login", { email, password });
  return data;
}

export async function fetchMe(): Promise<User> {
  const { data } = await api.get<User>("/auth/me");
  return data;
}
