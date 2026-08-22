import { useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { RefreshControl, StyleSheet, Text, View } from "react-native";

import { fetchVendors, type Vendor } from "../../src/api/vendors";
import {
  Body,
  Caption,
  Card,
  Chip,
  EmptyState,
  Heading,
  Loading,
  Row,
  Screen,
} from "../../src/components/ui";
import { categoryStyle, colors, font, radius, space } from "../../src/theme";

export default function Shops() {
  const router = useRouter();
  const { data, isLoading, refetch, isRefetching } = useQuery({
    queryKey: ["vendors"],
    queryFn: fetchVendors,
  });

  return (
    <Screen
      scroll
      refreshControl={
        <RefreshControl
          refreshing={isRefetching}
          onRefresh={refetch}
          tintColor={colors.brandBright}
        />
      }
    >
      <Heading style={{ paddingTop: space.md }}>Campus shops</Heading>
      <Caption style={{ marginTop: 2, marginBottom: space.lg }}>
        Order from a store and a runner brings it over.
      </Caption>

      {isLoading ? (
        <View style={{ height: 240 }}>
          <Loading />
        </View>
      ) : (data?.length ?? 0) === 0 ? (
        <Card style={{ height: 240, padding: 0, justifyContent: "center" }}>
          <EmptyState
            emoji="🏪"
            title="No shops yet"
            body="Campus stores appear here once an admin onboards them."
          />
        </Card>
      ) : (
        <View style={{ gap: space.md }}>
          {data!.map((v: Vendor) => {
            const cat = categoryStyle[v.category];
            return (
              <Card key={v.id} onPress={() => router.push(`/vendor/${v.id}`)}>
                <Row gap={space.md} align="flex-start">
                  <View style={[s.avatar, { backgroundColor: cat.tint }]}>
                    <Text style={{ fontSize: 24 }}>{cat.emoji}</Text>
                  </View>

                  <View style={{ flex: 1 }}>
                    <Row justify="space-between" gap={space.sm}>
                      <Body style={{ fontWeight: font.bold, flex: 1 }} numberOfLines={1}>
                        {v.name}
                      </Body>
                      <Chip
                        label={v.is_open ? "Open" : "Closed"}
                        color={v.is_open ? colors.success : colors.textFaint}
                        tint={v.is_open ? "rgba(47,217,143,0.14)" : colors.surfaceHigh}
                      />
                    </Row>

                    {v.description ? (
                      <Caption numberOfLines={2} style={{ marginTop: 3 }}>
                        {v.description}
                      </Caption>
                    ) : null}

                    <Row gap={space.sm} style={{ marginTop: space.sm }}>
                      <Chip label={cat.label} icon={cat.emoji} color={cat.color} tint={cat.tint} />
                    </Row>
                  </View>
                </Row>
              </Card>
            );
          })}
        </View>
      )}
    </Screen>
  );
}

const s = StyleSheet.create({
  avatar: {
    width: 54,
    height: 54,
    borderRadius: radius.lg,
    alignItems: "center",
    justifyContent: "center",
  },
});
