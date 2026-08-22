import { Tabs } from "expo-router";
import { StyleSheet, Text, View } from "react-native";

import { colors, font, radius, space } from "../../src/theme";

function TabIcon({ glyph, focused }: { glyph: string; focused: boolean }) {
  return (
    <View style={[s.icon, focused && s.iconOn]}>
      <Text style={{ fontSize: 19, opacity: focused ? 1 : 0.55 }}>{glyph}</Text>
    </View>
  );
}

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: s.bar,
        tabBarActiveTintColor: colors.brandBright,
        tabBarInactiveTintColor: colors.textFaint,
        tabBarLabelStyle: s.label,
        tabBarItemStyle: { paddingTop: 6 },
        sceneStyle: { backgroundColor: colors.bg },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "Home",
          tabBarIcon: ({ focused }) => <TabIcon glyph="🏠" focused={focused} />,
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
    backgroundColor: colors.bgElevated,
    borderTopColor: colors.border,
    borderTopWidth: 1,
    height: 86,
    paddingBottom: 26,
    paddingTop: 6,
  },
  label: { fontSize: font.tiny, fontWeight: font.bold, marginTop: 2 },
  icon: {
    width: 42,
    height: 30,
    borderRadius: radius.pill,
    alignItems: "center",
    justifyContent: "center",
  },
  iconOn: { backgroundColor: "rgba(124,92,255,0.18)" },
});
