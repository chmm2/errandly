import { useQuery } from "@tanstack/react-query";
import { Tabs } from "expo-router";
import { Platform, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { fetchRequests } from "../../src/api/social";
import { useAuth } from "../../src/stores/auth";
import { colors, font } from "../../src/theme";

/**
 * Five tabs: the two roles the product has, the wallet, your connections, and
 * your account. Shops isn't here — you reach it from Order → Food, the way the
 * web app does it.
 *
 * Wallet sits in the middle and is raised out of the bar. Money is the thing
 * people check most and trust least, so it gets the position a thumb reaches
 * without looking, and enough visual separation that it reads as its own
 * thing rather than one more destination.
 */
export default function TabsLayout() {
  const signedIn = !!useAuth((s) => s.accessToken);

  // Pending friend requests surface on the tab itself: a request nobody sees
  // is a connection that never forms, and connections are what decide who
  // your errands reach.
  const { data: requests } = useQuery({
    queryKey: ["friend-requests"],
    queryFn: fetchRequests,
    enabled: signedIn,
    refetchInterval: 60_000,
  });
  const pending = requests?.length ?? 0;
  // Size from the real inset; a hardcoded gap clipped the labels on anything
  // without a home indicator.
  const insets = useSafeAreaInsets();
  const bottomInset = Platform.OS === "web" ? 6 : Math.max(insets.bottom, 6);

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: [s.bar, { height: 62 + bottomInset, paddingBottom: bottomInset }],
        tabBarActiveTintColor: colors.brand,
        tabBarInactiveTintColor: colors.muted,
        tabBarLabelStyle: s.label,
        tabBarIconStyle: s.icon,
        sceneStyle: { backgroundColor: colors.bg },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "Order",
          tabBarIcon: ({ focused }) => (
            <Text style={{ fontSize: 20, opacity: focused ? 1 : 0.55 }}>🧑</Text>
          ),
        }}
      />
      <Tabs.Screen
        name="runner"
        options={{
          title: "Run",
          tabBarIcon: ({ focused }) => (
            <Text style={{ fontSize: 20, opacity: focused ? 1 : 0.55 }}>🛵</Text>
          ),
        }}
      />
      <Tabs.Screen
        name="wallet"
        options={{
          title: "Wallet",
          tabBarIcon: ({ focused }) => (
            <View style={[s.walletBubble, focused && s.walletBubbleActive]}>
              <Text style={{ fontSize: 21 }}>👛</Text>
            </View>
          ),
          // The bubble carries the identity; a label under it would crowd the
          // bar and sit at a different height from its neighbours.
          tabBarLabel: () => null,
        }}
      />
      <Tabs.Screen
        name="connects"
        options={{
          title: "Connects",
          tabBarIcon: ({ focused }) => (
            <Text style={{ fontSize: 20, opacity: focused ? 1 : 0.55 }}>🤝</Text>
          ),
          tabBarBadge: pending || undefined,
          tabBarBadgeStyle: s.badge,
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: "Profile",
          tabBarIcon: ({ focused }) => (
            <Text style={{ fontSize: 20, opacity: focused ? 1 : 0.55 }}>👤</Text>
          ),
        }}
      />
    </Tabs>
  );
}

const s = StyleSheet.create({
  bar: {
    backgroundColor: colors.white,
    borderTopColor: colors.line,
    borderTopWidth: 1,
    paddingTop: 8,
  },
  // Generous line height so descenders in "Profile" can't be clipped.
  label: { fontSize: 11, lineHeight: 15, fontFamily: font.bold, marginTop: 3 },
  icon: { height: 24 },
  badge: { backgroundColor: colors.brand, fontSize: 10, fontFamily: font.bold },

  // Lifted clear of the bar, with a ring in the page background so the bar
  // appears to part around it rather than the bubble sitting on top of it.
  walletBubble: {
    width: 54,
    height: 54,
    borderRadius: 27,
    marginTop: -22,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.white,
    borderWidth: 4,
    borderColor: colors.bg,
    shadowColor: "#101223",
    shadowOpacity: 0.18,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 4 },
    elevation: 6,
  },
  walletBubbleActive: { backgroundColor: colors.brandSoft },
});
