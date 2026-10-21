import { useQuery } from "@tanstack/react-query";
import { Tabs } from "expo-router";
import { Platform, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { fetchRequests } from "../../src/api/social";
import { Icon, type IconName } from "../../src/components/icons";
import { useAuth } from "../../src/stores/auth";
import { colors, font, shadow } from "../../src/theme";

/**
 * Five tabs: the two roles the product has, the wallet, your connections, and
 * your account. Shops isn't here, you reach it from Order then Food, the way
 * the web app does it.
 *
 * Wallet sits in the middle and is raised out of the bar. Money is the thing
 * people check most and trust least, so it gets the position a thumb reaches
 * without looking, and enough visual separation that it reads as its own thing
 * rather than one more destination.
 *
 * Every tab renders its whole stack (icon, label, active underline) inside the
 * icon slot, with the built-in label switched off. React Navigation puts its
 * own label below the icon with no room for a third element, and the design
 * wants the underline under the label rather than between it and the icon.
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
  const bottomInset = Platform.OS === "web" ? 8 : Math.max(insets.bottom, 8);

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: [s.bar, { height: 62 + bottomInset, paddingBottom: bottomInset }],
        tabBarItemStyle: s.item,
        tabBarIconStyle: s.iconSlot,
        tabBarLabel: () => null,
        sceneStyle: { backgroundColor: colors.bgSoft },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "Order",
          tabBarIcon: ({ focused }) => <TabItem icon="order" label="Order" focused={focused} />,
        }}
      />
      <Tabs.Screen
        name="runner"
        options={{
          title: "Run",
          tabBarIcon: ({ focused }) => <TabItem icon="run" label="Run" focused={focused} />,
        }}
      />
      <Tabs.Screen
        name="wallet"
        options={{
          title: "Wallet",
          // The bubble carries the identity; a label under it would crowd the
          // bar and sit at a different height from its neighbours.
          tabBarIcon: () => (
            <View style={s.bubble}>
              <Icon name="wallet" size={27} color={colors.white} />
            </View>
          ),
        }}
      />
      <Tabs.Screen
        name="connects"
        options={{
          title: "Connects",
          tabBarIcon: ({ focused }) => (
            <TabItem icon="connects" label="Connects" focused={focused} badge={pending} />
          ),
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: "Profile",
          tabBarIcon: ({ focused }) => <TabItem icon="profile" label="Profile" focused={focused} />,
        }}
      />
    </Tabs>
  );
}

function TabItem({
  icon,
  label,
  focused,
  badge = 0,
}: {
  icon: IconName;
  label: string;
  focused: boolean;
  badge?: number;
}) {
  const tint = focused ? colors.brand : colors.mutedCool;
  return (
    <View style={s.tab}>
      <Icon name={icon} size={24} color={tint} />
      <Text style={[s.label, { color: tint }]}>{label}</Text>
      {/* Reserve the underline's row on every tab, so switching tabs does not
          shift the icons up and down by two and a half pixels. */}
      <View style={[s.underline, focused && { backgroundColor: colors.brand }]} />
      {badge > 0 ? (
        <View style={s.badge}>
          <Text style={s.badgeText}>{badge > 9 ? "9+" : badge}</Text>
        </View>
      ) : null}
    </View>
  );
}

const s = StyleSheet.create({
  bar: {
    backgroundColor: colors.white,
    borderTopColor: colors.hairline,
    borderTopWidth: 1,
    paddingTop: 10,
  },
  // The stack is drawn entirely in the icon slot, so neither the slot nor the
  // item may impose a height on it.
  item: { height: "100%" },
  iconSlot: { height: "auto", flex: 0 },

  tab: { alignItems: "center", gap: 4 },
  label: { fontSize: 10.5, lineHeight: 13, fontFamily: font.bold },
  underline: { width: 18, height: 2.5, borderRadius: 2, backgroundColor: "transparent" },

  badge: {
    position: "absolute",
    top: -4,
    right: -12,
    minWidth: 17,
    height: 17,
    paddingHorizontal: 4,
    borderRadius: 9,
    backgroundColor: colors.moneyText,
    borderWidth: 2,
    borderColor: colors.white,
    alignItems: "center",
    justifyContent: "center",
  },
  badgeText: { color: colors.white, fontSize: 10, fontFamily: font.black },

  // Lifted clear of the bar, with a thick ring in the page background so the
  // bar appears to part around it rather than the bubble sitting on top of it.
  bubble: {
    width: 60,
    height: 60,
    borderRadius: 30,
    marginTop: -34,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.brand,
    borderWidth: 5,
    borderColor: colors.white,
    ...shadow.bubble,
  },
});
