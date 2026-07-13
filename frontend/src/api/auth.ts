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

export interface RegisterResult {
  user: User;
  devOtp: string | null; // dev-mode convenience (SMTP off); null in production
}

export async function register(payload: RegisterPayload): Promise<RegisterResult> {
  const res = await api.post<User>("/auth/register", payload);
  return { user: res.data, devOtp: res.headers["x-dev-otp"] ?? null };
}

export async function verifyEmail(email: string, code: string): Promise<TokenPair> {
  const { data } = await api.post<TokenPair>("/auth/verify-email", { email, code });
  return data;
}

export async function resendOtp(email: string): Promise<string | null> {
  const res = await api.post("/auth/resend-otp", { email });
  return res.headers["x-dev-otp"] ?? null;
}

export async function login(email: string, password: string): Promise<TokenPair> {
  const { data } = await api.post<TokenPair>("/auth/login", { email, password });
  return data;
}

export async function fetchMe(): Promise<User> {
  const { data } = await api.get<User>("/auth/me");
  return data;
}
