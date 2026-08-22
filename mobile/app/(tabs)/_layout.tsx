import { Tabs } from "expo-router";
import { Platform, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { colors, font, radius } from "../../src/theme";

function TabIcon({ glyph, focused }: { glyph: string; focused: boolean }) {
  return (
    <View style={[s.icon, focused && s.iconOn]}>
      <Text style={{ fontSize: 18, opacity: focused ? 1 : 0.5 }}>{glyph}</Text>
    </View>
  );
}

export default function TabsLayout() {
  // Size the bar from the real bottom inset rather than a hardcoded guess —
  // a fixed 26pt gap clipped the labels on anything without a home indicator.
  const insets = useSafeAreaInsets();
  const bottomInset = Platform.OS === "web" ? 8 : Math.max(insets.bottom, 8);

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: [s.bar, { height: 58 + bottomInset, paddingBottom: bottomInset }],
        tabBarActiveTintColor: colors.brand,
        tabBarInactiveTintColor: colors.muted,
        tabBarLabelStyle: s.label,
        tabBarItemStyle: { paddingTop: 5 },
        sceneStyle: { backgroundColor: colors.bg },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "Order",
          tabBarIcon: ({ focused }) => <TabIcon glyph="🧑" focused={focused} />,
        }}
      />
      <Tabs.Screen
        name="shops"
        options={{
          title: "Shops",
          tabBarIcon: ({ focused }) => <TabIcon glyph="🏪" focused={focused} />,
        }}
      />
      <Tabs.Screen
        name="runner"
        options={{
          title: "Run",
          tabBarIcon: ({ focused }) => <TabIcon glyph="🛵" focused={focused} />,
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: "Profile",
          tabBarIcon: ({ focused }) => <TabIcon glyph="👤" focused={focused} />,
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
    paddingTop: 4,
  },
  label: { fontSize: 10, fontFamily: font.bold, marginTop: 1 },
  icon: {
    width: 38,
    height: 26,
    borderRadius: radius.pill,
    alignItems: "center",
    justifyContent: "center",
  },
  iconOn: { backgroundColor: colors.brandSoft },
});
