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

/**
 * Ask for a password-reset code.
 *
 * Resolves even when no account exists for the address — the backend answers
 * 202 either way so the endpoint can't be used to discover who's registered.
 * The UI must therefore never claim the email "was sent", only that it will
 * arrive if the account exists.
 */
export async function forgotPassword(email: string): Promise<string | null> {
  const res = await api.post("/auth/forgot-password", { email });
  return res.headers["x-dev-otp"] ?? null;
}

export async function resetPassword(
  email: string,
  code: string,
  new_password: string,
): Promise<void> {
  await api.post("/auth/reset-password", { email, code, new_password });
}

export async function login(email: string, password: string): Promise<TokenPair> {
  const { data } = await api.post<TokenPair>("/auth/login", { email, password });
  return data;
}

export async function fetchMe(): Promise<User> {
  const { data } = await api.get<User>("/auth/me");
  return data;
}

export async function setPhoto(photo_url: string | null): Promise<User> {
  const { data } = await api.put<User>("/auth/me/photo", { photo_url });
  return data;
}
