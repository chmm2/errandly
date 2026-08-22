import { LinearGradient } from "expo-linear-gradient";
import { StyleSheet, Text, View } from "react-native";

import type { Errand } from "../api/errands";
import {
  categoryStyle,
  colors,
  font,
  metres,
  radius,
  rupees,
  space,
  statusStyle,
  timeAgo,
  timeLeft,
} from "../theme";
import { Body, Caption, Card, Chip, Row } from "./ui";

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
  const cat = categoryStyle[errand.category];
  const status = statusStyle[errand.status];
  const distance = metres(errand.distance_m);
  const left = errand.status === "OPEN" ? timeLeft(errand.expires_at) : null;

  return (
    <Card onPress={onPress} style={s.card}>
      {/* Category stripe — colour-codes the card at a glance */}
      <LinearGradient
        colors={[cat.color, "transparent"]}
        start={{ x: 0, y: 0 }}
        end={{ x: 0, y: 1 }}
        style={s.stripe}
      />

      <Row justify="space-between" align="flex-start" gap={space.md}>
        <View style={{ flex: 1 }}>
          <Row gap={space.sm} wrap style={{ marginBottom: space.sm }}>
            <Chip label={cat.label} icon={cat.emoji} color={cat.color} tint={cat.tint} />
            {showStatus ? (
              <Chip label={status.label} color={status.color} tint={status.tint} />
            ) : null}
          </Row>

          <Body numberOfLines={2} style={s.title}>
            {errand.title}
          </Body>

          <Row gap={space.xs} style={{ marginTop: 5 }}>
            <Text style={s.pin}>📍</Text>
            <Caption numberOfLines={1} style={{ flex: 1 }}>
              {errand.pickup_label}
              {errand.drop_label ? ` → ${errand.drop_label}` : ""}
            </Caption>
          </Row>
        </View>

        {/* Reward is the decision-driver for a runner — give it real weight */}
        <View style={s.rewardWrap}>
          <Text style={s.reward}>{rupees(errand.reward)}</Text>
          <Caption style={s.rewardLabel}>reward</Caption>
        </View>
      </Row>

      <Row gap={space.md} wrap style={s.meta}>
        {distance ? <Caption>🧭 {distance} away</Caption> : null}
        {errand.items_total > 0 ? <Caption>🧾 {rupees(errand.items_total)} order</Caption> : null}
        {errand.collect_amount > 0 ? (
          <Caption style={{ color: colors.warning }}>
            💵 {rupees(errand.collect_amount)} to pay
          </Caption>
        ) : null}
        {left ? <Caption style={{ color: colors.warning }}>⏳ {left}</Caption> : null}
        <Caption style={{ marginLeft: "auto" }}>{timeAgo(errand.created_at)}</Caption>
      </Row>

      {footer ? <View style={s.footer}>{footer}</View> : null}
    </Card>
  );
}

const s = StyleSheet.create({
  card: { overflow: "hidden", paddingLeft: space.lg + 3 },
  stripe: { position: "absolute", left: 0, top: 0, bottom: 0, width: 4, opacity: 0.9 },

  title: { fontSize: font.h3, fontWeight: font.bold, lineHeight: 22 },
  pin: { fontSize: 11 },

  rewardWrap: { alignItems: "flex-end", minWidth: 62 },
  reward: { color: colors.gold, fontSize: 23, fontWeight: font.black, letterSpacing: -0.6 },
  rewardLabel: { color: colors.goldDeep, fontSize: 10, letterSpacing: 0.6, marginTop: -2 },

  meta: {
    marginTop: space.md,
    paddingTop: space.md,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    alignItems: "center",
  },
  footer: { marginTop: space.md, gap: space.sm },
});
