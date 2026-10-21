import { useQuery } from "@tanstack/react-query";
import { Tabs } from "expo-router";
import type { ComponentProps } from "react";
import { Platform, Pressable, StyleSheet, Text, View } from "react-native";
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
 * The bar is drawn here rather than by React Navigation. Its built-in item
 * sizes the icon slot itself, and a stack of icon, label and underline
 * overflowed that slot and rode up over the bar's top edge. Drawing it by hand
 * puts every position on the constants below, so the four tabs and the wallet
 * bubble cannot drift out of line with each other.
 */

/** Per-tab metadata, in bar order. The route name is the file under (tabs). */
const TABS: Record<string, { label: string; icon: IconName }> = {
  index: { label: "Order", icon: "order" },
  runner: { label: "Run", icon: "run" },
  wallet: { label: "Wallet", icon: "wallet" },
  connects: { label: "Connects", icon: "connects" },
  profile: { label: "Profile", icon: "profile" },
};

// Geometry. The stack is icon, gap, label, gap, underline, and it is centred
// in the bar's content height. The bubble is then placed so its centre sits
// on the icon row, which leaves it standing proud of the bar's top edge, the
// way the design draws it.
const BAR_H = 58;
const ICON = 24;
const GAP = 4;
const LABEL_H = 13;
const LINE_H = 2.5;
const STACK_H = ICON + GAP + LABEL_H + GAP + LINE_H;
const STACK_TOP = (BAR_H - STACK_H) / 2;
const ICON_CENTRE = STACK_TOP + ICON / 2;
const BUBBLE = 60;
const BUBBLE_TOP = ICON_CENTRE - BUBBLE / 2;

type TabBarProps = Parameters<NonNullable<ComponentProps<typeof Tabs>["tabBar"]>>[0];

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

  return (
    <Tabs
      screenOptions={{ headerShown: false, sceneStyle: { backgroundColor: colors.bgSoft } }}
      tabBar={(props) => <TabBar {...props} badges={{ connects: pending }} />}
    >
      <Tabs.Screen name="index" options={{ title: "Order" }} />
      <Tabs.Screen name="runner" options={{ title: "Run" }} />
      <Tabs.Screen name="wallet" options={{ title: "Wallet" }} />
      <Tabs.Screen name="connects" options={{ title: "Connects" }} />
      <Tabs.Screen name="profile" options={{ title: "Profile" }} />
    </Tabs>
  );
}

function TabBar({
  state,
  navigation,
  badges,
}: TabBarProps & { badges: Record<string, number> }) {
  // Size from the real inset; a hardcoded gap clipped the labels on anything
  // without a home indicator.
  const insets = useSafeAreaInsets();
  const bottomInset = Platform.OS === "web" ? 8 : Math.max(insets.bottom, 8);

  return (
    <View style={[s.bar, { paddingBottom: bottomInset }]}>
      {state.routes.map((route, index) => {
        const meta = TABS[route.name];
        if (!meta) return null;
        const focused = state.index === index;

        // The same press contract React Navigation's own bar follows, so
        // listeners that watch tabPress (scroll to top, refresh) still fire.
        const onPress = () => {
          const event = navigation.emit({
            type: "tabPress",
            target: route.key,
            canPreventDefault: true,
          });
          if (!focused && !event.defaultPrevented) navigation.navigate(route.name, route.params);
        };
        const onLongPress = () => navigation.emit({ type: "tabLongPress", target: route.key });

        if (route.name === "wallet") {
          return (
            <Pressable
              key={route.key}
              onPress={onPress}
              onLongPress={onLongPress}
              style={s.item}
              accessibilityRole="tab"
              aria-selected={focused}
              accessibilityLabel={meta.label}
            >
              {/* The bubble carries the identity; a label under it would crowd
                  the bar and sit at a different height from its neighbours. */}
              <View style={s.bubble}>
                <Icon name="wallet" size={27} color={colors.white} />
              </View>
            </Pressable>
          );
        }

        const tint = focused ? colors.brand : colors.mutedCool;
        const badge = badges[route.name] ?? 0;
        return (
          <Pressable
            key={route.key}
            onPress={onPress}
            onLongPress={onLongPress}
            style={s.item}
            accessibilityRole="tab"
            aria-selected={focused}
            accessibilityLabel={badge ? `${meta.label}, ${badge} waiting` : meta.label}
          >
            <View style={s.stack}>
              <Icon name={meta.icon} size={ICON} color={tint} />
              <Text style={[s.label, { color: tint }]} numberOfLines={1}>
                {meta.label}
              </Text>
              {/* Reserved on every tab, so switching tabs never moves the
                  icons up or down by the underline's height. */}
              <View style={[s.underline, focused && { backgroundColor: colors.brand }]} />
              {badge > 0 ? (
                <View style={s.badge}>
                  <Text style={s.badgeText}>{badge > 9 ? "9+" : badge}</Text>
                </View>
              ) : null}
            </View>
          </Pressable>
        );
      })}
    </View>
  );
}

const s = StyleSheet.create({
  bar: {
    flexDirection: "row",
    backgroundColor: colors.white,
    borderTopColor: colors.hairline,
    borderTopWidth: 1,
    paddingHorizontal: 14,
  },
  item: { flex: 1, height: BAR_H, alignItems: "center" },

  stack: { position: "absolute", top: STACK_TOP, alignItems: "center", gap: GAP },
  label: { fontSize: 10.5, lineHeight: LABEL_H, height: LABEL_H, fontFamily: font.bold },
  underline: { width: 18, height: LINE_H, borderRadius: 2, backgroundColor: "transparent" },

  badge: {
    position: "absolute",
    top: -4,
    right: -14,
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

  // Centred on the icon row, which lifts it clear of the bar's top edge, with a
  // thick ring in the bar colour so the bar appears to part around it.
  bubble: {
    position: "absolute",
    top: BUBBLE_TOP,
    width: BUBBLE,
    height: BUBBLE,
    borderRadius: BUBBLE / 2,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.brand,
    borderWidth: 5,
    borderColor: colors.white,
    ...shadow.bubble,
  },
});
