import { StyleSheet, Text, View } from "react-native";

import type { Errand } from "../api/errands";
import { categoryIcon, colors, font, metres, rupees, space, statusStyle, timeAgo } from "../theme";
import { ConnectionBadge } from "./ConnectionBadge";
import { Body, Caption, Card, IconTile, Pill, Row } from "./ui";

/**
 * One errand in a list. Mirrors the web app's card: category tile on the left,
 * title and pickup line, status pill, reward called out on the right.
 */
export function ErrandCard({
  errand,
  onPress,
  showStatus = true,
  footer,
}: {
  errand: Errand;
  onPress?: () => void;
  showStatus?: boolean;
  footer?: React.ReactNode;
}) {
  const status = statusStyle[errand.status];
  const distance = metres(errand.distance_m);

  return (
    <Card raised onPress={onPress} style={{ padding: space.lg }}>
      <Row gap={space.md} align="flex-start">
        <IconTile emoji={categoryIcon[errand.category] ?? "✨"} />

        <View style={{ flex: 1, minWidth: 0 }}>
          <Row gap={space.sm} align="flex-start">
            <Body numberOfLines={2} style={{ fontFamily: font.bold, flex: 1 }}>
              {errand.title}
            </Body>
            {/* Degree badge sits with the title, not the metadata row: whether
                this came from someone you know changes how you read the whole
                card, so it has to land in the same glance as the title. */}
            <ConnectionBadge connection={errand.connection} />
          </Row>
          <Caption numberOfLines={1} style={{ marginTop: 2 }}>
            from {errand.pickup_label}
            {errand.drop_label ? ` → ${errand.drop_label}` : ""}
          </Caption>

          {showStatus ? (
            <View style={{ marginTop: space.sm }}>
              <Pill label={status.label} bg={status.bg} color={status.text} />
            </View>
          ) : null}
        </View>

        <View style={{ alignItems: "flex-end" }}>
          <Text style={s.reward}>{rupees(errand.reward)}</Text>
          <Caption style={{ fontSize: 10 }}>reward</Caption>
        </View>
      </Row>

      <Row gap={space.md} wrap style={s.meta}>
        {distance ? <Caption>🧭 {distance} away</Caption> : null}
        {errand.items_total > 0 ? <Caption>🧾 {rupees(errand.items_total)} order</Caption> : null}
        {errand.collect_amount > 0 ? (
          <Caption style={{ color: colors.amberText }}>
            💵 {rupees(errand.collect_amount)} to pay
          </Caption>
        ) : null}
        <Caption style={{ marginLeft: "auto" }}>{timeAgo(errand.created_at)}</Caption>
      </Row>

      {footer ? <View style={{ marginTop: space.md, gap: space.sm }}>{footer}</View> : null}
    </Card>
  );
}

const s = StyleSheet.create({
  reward: { color: colors.brand, fontSize: 20, fontFamily: font.black },
  meta: {
    marginTop: space.md,
    paddingTop: space.md,
    borderTopWidth: 1,
    borderTopColor: colors.line,
    alignItems: "center",
  },
});
