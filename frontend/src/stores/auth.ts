import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface User {
  id: string;
  student_id: string | null;
  email: string;
  display_name: string;
  role: "STUDENT" | "VENDOR" | "ADMIN";
  account_status: "PENDING" | "ACTIVE" | "SUSPENDED" | "BANNED";
  reputation_score: number;
}

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: User | null;
  setTokens: (access: string, refresh: string) => void;
  setUser: (user: User | null) => void;
  logout: () => void;
}

export const useAuth = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      setTokens: (accessToken, refreshToken) => set({ accessToken, refreshToken }),
      setUser: (user) => set({ user }),
      logout: () => set({ accessToken: null, refreshToken: null, user: null }),
    }),
    { name: "errandly-auth" },
  ),
);
