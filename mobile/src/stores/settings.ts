import AsyncStorage from "@react-native-async-storage/async-storage";
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

interface SettingsState {
  /**
   * Backend origin typed by the user, overriding the compiled-in default.
   * null means "use the built-in address".
   *
   * This exists because a release build bakes its backend URL in at build time,
   * so a tunnel or host change would otherwise brick an installed app until it
   * was rebuilt and reinstalled. Being able to retype the address turns a
   * 20-minute rebuild into a few seconds.
   */
  apiHostOverride: string | null;
  setApiHostOverride: (host: string | null) => void;
  hydrated: boolean;
}

export const useSettings = create<SettingsState>()(
  persist(
    (set) => ({
      apiHostOverride: null,
      setApiHostOverride: (host) =>
        set({ apiHostOverride: host ? host.trim().replace(/\/+$/, "") : null }),
      hydrated: false,
    }),
    {
      name: "errandly-settings",
      storage: createJSONStorage(() => AsyncStorage),
      partialize: (s) => ({ apiHostOverride: s.apiHostOverride }),
      onRehydrateStorage: () => (state) => {
        useSettings.setState({ hydrated: true, ...(state ?? {}) });
      },
    },
  ),
);
