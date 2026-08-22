import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Stack, useRouter, useSegments } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useEffect, useState } from "react";
import { View } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { Loading } from "../src/components/ui";
import { useAuth } from "../src/stores/auth";
import { colors } from "../src/theme";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 10_000,
      refetchOnWindowFocus: false,
    },
  },
});

/**
 * Sends the user to the right half of the app whenever auth state changes:
 * signed out -> (auth), signed in -> (tabs). Runs only after the persisted
 * session has been read off disk, so a cold start doesn't flash the login
 * screen at an already-signed-in user.
 */
function useAuthGate() {
  const router = useRouter();
  const segments = useSegments();
  const token = useAuth((s) => s.accessToken);
  const hydrated = useAuth((s) => s.hydrated);

  useEffect(() => {
    if (!hydrated) return;
    const inAuthGroup = segments[0] === "(auth)";

    if (!token && !inAuthGroup) {
      router.replace("/(auth)/login");
    } else if (token && inAuthGroup) {
      router.replace("/(tabs)");
    }
  }, [token, hydrated, segments, router]);

  return hydrated;
}

export default function RootLayout() {
  const hydrated = useAuthGate();
  // Give zustand's async rehydrate one tick before rendering routes.
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (hydrated) setReady(true);
  }, [hydrated]);

  return (
    <SafeAreaProvider>
      <QueryClientProvider client={queryClient}>
        <StatusBar style="light" />
        {ready ? (
          <Stack
            screenOptions={{
              headerShown: false,
              contentStyle: { backgroundColor: colors.bg },
              animation: "slide_from_right",
            }}
          >
            <Stack.Screen name="(auth)" />
            <Stack.Screen name="(tabs)" />
            <Stack.Screen
              name="errand/[id]"
              options={{ animation: "slide_from_bottom", presentation: "card" }}
            />
            <Stack.Screen name="errand/new" options={{ animation: "slide_from_bottom" }} />
          </Stack>
        ) : (
          <View style={{ flex: 1, backgroundColor: colors.bg }}>
            <Loading />
          </View>
        )}
      </QueryClientProvider>
    </SafeAreaProvider>
  );
}
