import { Tabs } from "expo-router";
import { Platform, StyleSheet, Text } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { colors, font } from "../../src/theme";

/**
 * Three tabs, matching the two roles the product actually has plus your
 * account. Shops isn't here — you reach it from Order → Food, the way the web
 * app does it.
 */
export default function TabsLayout() {
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
});
