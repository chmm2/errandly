import AsyncStorage from "@react-native-async-storage/async-storage";
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

export interface User {
  id: string;
  student_id: string | null;
  email: string;
  display_name: string;
  role: "STUDENT" | "VENDOR" | "ADMIN";
  account_status: "PENDING" | "ACTIVE" | "SUSPENDED" | "BANNED";
  reputation_score: number;
  photo_url: string | null;
}

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: User | null;
  /** False until the persisted session has been read back off disk. */
  hydrated: boolean;
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
      hydrated: false,
      setTokens: (accessToken, refreshToken) => set({ accessToken, refreshToken }),
      setUser: (user) => set({ user }),
      logout: () => set({ accessToken: null, refreshToken: null, user: null }),
    }),
    {
      name: "errandly-auth",
      // Web used localStorage synchronously; AsyncStorage is a promise, so the
      // app must wait for `hydrated` before deciding logged-in vs logged-out —
      // otherwise every cold start flashes the login screen.
      storage: createJSONStorage(() => AsyncStorage),
      partialize: (s) => ({
        accessToken: s.accessToken,
        refreshToken: s.refreshToken,
        user: s.user,
      }),
      // Zustand has already merged the persisted values by the time this runs,
      // so only flip the flag. Spreading `state` here would be actively wrong:
      // it's the full store state, whose own `hydrated` is still false, and
      // spreading it after the flag would overwrite it back — leaving the app
      // stuck on the splash spinner forever.
      onRehydrateStorage: () => () => {
        useAuth.setState({ hydrated: true });
      },
    },
  ),
);
