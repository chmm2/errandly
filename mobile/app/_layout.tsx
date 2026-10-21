import { IBMPlexMono_400Regular, IBMPlexMono_500Medium } from "@expo-google-fonts/ibm-plex-mono";
import {
  PlusJakartaSans_400Regular,
  PlusJakartaSans_500Medium,
  PlusJakartaSans_600SemiBold,
  PlusJakartaSans_700Bold,
  PlusJakartaSans_800ExtraBold,
  useFonts,
} from "@expo-google-fonts/plus-jakarta-sans";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Stack, useRouter, useSegments } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useCallback, useEffect, useState } from "react";
import { Platform, StyleSheet, View } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { DialogHost } from "../src/components/DialogHost";
import { Loading } from "../src/components/ui";
import { usePushNotifications } from "../src/lib/push";
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
  const router = useRouter();
  const signedIn = !!useAuth((s) => s.accessToken);

  // Register this device for OS-level push once signed in, and open the right
  // errand when a banner is tapped.
  usePushNotifications(
    signedIn,
    useCallback((errandId: string) => router.push(`/errand/${errandId}`), [router]),
  );

  // Plus Jakarta Sans for text, IBM Plex Mono for codes. Rendering before they
  // load would show a frame of system font and then reflow.
  const [fontsLoaded] = useFonts({
    PlusJakartaSans_400Regular,
    PlusJakartaSans_500Medium,
    PlusJakartaSans_600SemiBold,
    PlusJakartaSans_700Bold,
    PlusJakartaSans_800ExtraBold,
    IBMPlexMono_400Regular,
    IBMPlexMono_500Medium,
  });

  // Give zustand's async rehydrate one tick before rendering routes.
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (hydrated && fontsLoaded) setReady(true);
  }, [hydrated, fontsLoaded]);

  return (
    <PhoneFrame>
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
          {/* Last child so it paints above every screen. */}
          <DialogHost />
        </QueryClientProvider>
      </SafeAreaProvider>
    </PhoneFrame>
  );
}

/**
 * On web only, pin the app to a phone-sized column on a neutral backdrop.
 *
 * React Native's layout fills whatever container it's given, so in a desktop
 * browser the UI stretches to monitor width and looks nothing like the product.
 * Constraining it here means the browser preview is always representative
 * without reaching for device emulation every time.
 *
 * On a real device this is a passthrough — the phone IS the frame.
 */
function PhoneFrame({ children }: { children: React.ReactNode }) {
  if (Platform.OS !== "web") return <>{children}</>;

  return (
    <View style={frame.backdrop}>
      <View style={frame.device}>{children}</View>
    </View>
  );
}

const PHONE_WIDTH = 402; // iPhone 16 Pro logical width

const frame = StyleSheet.create({
  backdrop: {
    flex: 1,
    minHeight: "100%",
    backgroundColor: "#EFF1F0",
    alignItems: "center",
    justifyContent: "center",
  },
  device: {
    width: PHONE_WIDTH,
    maxWidth: "100%",
    flex: 1,
    // Cap the height so a tall desktop window still reads as a phone rather
    // than an unnaturally long strip.
    maxHeight: 874,
    backgroundColor: colors.bg,
    overflow: "hidden",
    borderRadius: 38,
    borderWidth: 1,
    borderColor: colors.line,
    shadowColor: "#16302F",
    shadowOpacity: 0.3,
    shadowRadius: 70,
    shadowOffset: { width: 0, height: 30 },
  },
});
