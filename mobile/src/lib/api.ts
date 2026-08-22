import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";

import { useAuth } from "../stores/auth";
import { apiBase } from "./config";

/**
 * On web this pointed at "/api" and Vite proxied it. There's no proxy on a
 * phone, so we talk to the backend's real address directly.
 *
 * baseURL is set per-request rather than at creation: the user can retype the
 * backend host at runtime, and a baseURL fixed here would keep pointing at the
 * old one until the app restarted.
 */
export const api = axios.create({ timeout: 15000 });

api.interceptors.request.use((config) => {
  config.baseURL = apiBase();
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
    const { data } = await axios.post(`${apiBase()}/auth/refresh`, {
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
      return `Can't reach the server at ${apiBase()}. Check it's running, and that the backend address in Profile is correct.`;
    }
    const detail = (err.response.data as { detail?: unknown })?.detail;
    if (typeof detail === "string") return detail;
  }
  return fallback;
}
