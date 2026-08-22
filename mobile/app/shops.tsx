import { useQuery } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useMemo, useState } from "react";
import { Pressable, RefreshControl, StyleSheet, Text, TextInput, View } from "react-native";

import { fetchVendors, type Vendor } from "../src/api/vendors";
import {
  Body,
  Caption,
  EmptyState,
  Hero,
  Loading,
  Pill,
  Row,
  Screen,
} from "../src/components/ui";
import { categoryIcon, colors, font, radius, space } from "../src/theme";

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
      tabBarClearance={false}
      refreshControl={
        <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={colors.brand} />
      }
    >
      <Hero
        compact
        onBack={() => router.back()}
        title={foodMode ? "Food on campus 🍔" : "Campus stores 🏪"}
        subtitle={
          foodMode
            ? "Every canteen, food court and night mess on campus. Order off the menu — a runner brings it to you."
            : "Order straight off the menu — a runner picks it up and brings it to you."
        }
      >
        <TextInput
          value={search}
          onChangeText={setSearch}
          placeholder={foodMode ? "🔍 Search canteens & food spots" : "🔍 Search stores"}
          placeholderTextColor={colors.muted}
          style={s.search}
        />
      </Hero>

      <View style={{ paddingHorizontal: space.lg, paddingTop: space.xl }}>
        {isLoading ? (
          <View style={{ height: 220 }}>
            <Loading />
          </View>
        ) : filtered.length === 0 ? (
          <EmptyState
            emoji="🏪"
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
          <Row gap={space.md} wrap align="stretch">
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
                <Text style={{ fontSize: 30 }}>{categoryIcon[v.category] ?? "🏪"}</Text>
                <Body numberOfLines={1} style={{ fontFamily: font.bold, marginTop: space.sm }}>
                  {v.name}
                </Body>
                {v.description ? (
                  <Caption numberOfLines={2} style={{ marginTop: 2 }}>
                    {v.description}
                  </Caption>
                ) : null}
                <View style={{ marginTop: space.sm }}>
                  <Pill
                    label={v.is_open ? "● Open" : "Closed"}
                    bg={v.is_open ? colors.greenBg : colors.grayBg}
                    color={v.is_open ? colors.greenText : colors.muted}
                  />
                </View>
              </Pressable>
            ))}
          </Row>
        )}
      </View>
    </Screen>
  );
}

const s = StyleSheet.create({
  search: {
    marginTop: space.lg,
    backgroundColor: "rgba(255,255,255,0.95)",
    borderRadius: radius.lg,
    paddingHorizontal: space.lg,
    paddingVertical: space.md + 1,
    color: colors.ink,
    fontSize: font.body,
    fontFamily: font.regular,
  },
  card: {
    width: "48%",
    borderRadius: radius.xl,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.white,
    padding: space.lg,
    minHeight: 150,
  },
});
