import { useQuery } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useMemo, useState } from "react";
import { Pressable, RefreshControl, StyleSheet, Text, TextInput, View } from "react-native";

import { fetchVendors, type Vendor } from "../src/api/vendors";
import { Icon } from "../src/components/icons";
import { EmptyState, Hero, IconTile, Screen, SkeletonRow } from "../src/components/ui";
import { categoryIcon, colors, font, radius, space } from "../src/theme";
import { goBack } from "../src/lib/nav";

export default function Shops() {
  const router = useRouter();
  const params = useLocalSearchParams<{ category?: string }>();
  const foodMode = params.category === "FOOD";
  const [search, setSearch] = useState("");

  const { data: vendors, isLoading, refetch, isRefetching } = useQuery({
    queryKey: ["vendors"],
    queryFn: fetchVendors,
  });

  const filtered = useMemo(() => {
    let list = vendors ?? [];
    if (foodMode) list = list.filter((v) => v.category === "FOOD");
    const q = search.trim().toLowerCase();
    if (q) {
      list = list.filter(
        (v) =>
          v.name.toLowerCase().includes(q) ||
          (v.description ?? "").toLowerCase().includes(q),
      );
    }
    return list;
  }, [vendors, foodMode, search]);

  return (
    <Screen
      scroll
      padded={false}
      edges={[]}
      bg={colors.bgSoft}
      tabBarClearance={false}
      refreshControl={
        <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={colors.brand} />
      }
    >
      <Hero
        compact
        onBack={() => goBack(router)}
        eyebrow={foodMode ? "Order in" : "Shop"}
        title={foodMode ? "Food on campus" : "Campus stores"}
        subtitle={
          foodMode
            ? "Every canteen, food court and night mess. Order off the menu and a runner brings it to you."
            : "Order straight off the menu and a runner brings it to you."
        }
      >
        <View style={s.search}>
          <Icon name="search" size={20} color={colors.brand} />
          <TextInput
            value={search}
            onChangeText={setSearch}
            placeholder={foodMode ? "Search canteens and food spots" : "Search stores"}
            placeholderTextColor={colors.mutedCool}
            style={s.searchInput}
          />
        </View>
      </Hero>

      <View style={{ paddingHorizontal: 22, paddingTop: 18 }}>
        {isLoading ? (
          <View style={{ gap: space.sm }}>
            <SkeletonRow />
            <SkeletonRow />
          </View>
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={foodMode ? "bowl" : "bag"}
            title={
              (vendors ?? []).length === 0
                ? "No stores onboarded yet"
                : `No matches for "${search}"`
            }
            body={
              (vendors ?? []).length === 0
                ? "Campus stores appear here once an admin adds them."
                : undefined
            }
          />
        ) : (
          <View style={s.grid}>
            {filtered.map((v: Vendor) => (
              <Pressable
                key={v.id}
                onPress={() => router.push(`/vendor/${v.id}`)}
                style={({ pressed }) => [
                  s.card,
                  !v.is_open && { opacity: 0.6 },
                  pressed && { borderColor: colors.brand },
                ]}
              >
                <IconTile
                  icon={categoryIcon[v.category as keyof typeof categoryIcon] ?? "bag"}
                  size={40}
                />
                <Text numberOfLines={1} style={s.name}>
                  {v.name}
                </Text>
                {v.description ? (
                  <Text numberOfLines={2} style={s.desc}>
                    {v.description}
                  </Text>
                ) : null}
                <View
                  style={[s.status, { backgroundColor: v.is_open ? colors.creditBg : colors.chip }]}
                >
                  <View
                    style={[s.dot, { backgroundColor: v.is_open ? colors.credit : colors.mutedCool }]}
                  />
                  <Text style={[s.statusText, { color: v.is_open ? colors.credit : colors.muted }]}>
                    {v.is_open ? "Open" : "Closed"}
                  </Text>
                </View>
              </Pressable>
            ))}
          </View>
        )}
      </View>
    </Screen>
  );
}

const s = StyleSheet.create({
  search: {
    flexDirection: "row",
    alignItems: "center",
    gap: 11,
    marginTop: space.lg,
    backgroundColor: colors.white,
    borderRadius: radius.xxl,
    paddingHorizontal: 15,
  },
  searchInput: {
    flex: 1,
    paddingVertical: 12,
    color: colors.ink,
    fontSize: 14.5,
    fontFamily: font.regular,
  },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 9 },
  card: {
    width: "48.4%",
    borderRadius: radius.xxl,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.white,
    padding: 13,
    minHeight: 150,
  },
  name: { color: colors.ink, fontSize: 14.5, fontFamily: font.bold, marginTop: 8 },
  desc: { color: colors.muted, fontSize: 12, fontFamily: font.regular, lineHeight: 17, marginTop: 2 },
  status: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    alignSelf: "flex-start",
    marginTop: 8,
    paddingHorizontal: 9,
    paddingVertical: 4,
    borderRadius: radius.pill,
  },
  dot: { width: 6, height: 6, borderRadius: 3 },
  statusText: { fontSize: 11, fontFamily: font.bold },
});
