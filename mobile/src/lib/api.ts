import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";

import { useAuth } from "../stores/auth";
import { API_BASE } from "./config";

/**
 * On web this pointed at "/api" and Vite proxied it. There's no proxy on a
 * phone, so we talk to the backend's LAN address directly.
 */
export const api = axios.create({ baseURL: API_BASE, timeout: 15000 });

api.interceptors.request.use((config) => {
  const token = useAuth.getState().accessToken;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Endpoints where a 401 means "bad credentials", not "expired session".
const NO_REFRESH = ["/auth/login", "/auth/register", "/auth/refresh"];

let refreshInFlight: Promise<string | null> | null = null;

async function rotateTokens(): Promise<string | null> {
  const { refreshToken, setTokens, logout } = useAuth.getState();
  if (!refreshToken) return null;
  try {
    // Bare axios: must not recurse through this interceptor.
    const { data } = await axios.post(`${API_BASE}/auth/refresh`, {
      refresh_token: refreshToken,
    });
    setTokens(data.access_token, data.refresh_token);
    return data.access_token as string;
  } catch {
    logout();
    return null;
  }
}

api.interceptors.response.use(
  (res) => res,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & { _retried?: boolean };
    const skip = NO_REFRESH.some((path) => original?.url?.includes(path));

    if (error.response?.status === 401 && original && !original._retried && !skip) {
      original._retried = true;
      // Single-flight refresh: the backend rotates refresh tokens (single-use),
      // so N concurrent 401s must share ONE rotation — racing would revoke
      // ourselves and log the user out.
      refreshInFlight ??= rotateTokens().finally(() => {
        refreshInFlight = null;
      });
      const token = await refreshInFlight;
      if (token) {
        original.headers.Authorization = `Bearer ${token}`;
        return api(original);
      }
    }
    return Promise.reject(error);
  },
);

export function apiErrorMessage(err: unknown, fallback = "Something went wrong."): string {
  if (axios.isAxiosError(err)) {
    if (err.code === "ECONNABORTED") return "The server took too long to respond.";
    if (!err.response) {
      return `Can't reach the server at ${API_BASE}. Is the backend running, and is your phone on the same Wi-Fi?`;
    }
    const detail = (err.response.data as { detail?: unknown })?.detail;
    if (typeof detail === "string") return detail;
  }
  return fallback;
}
