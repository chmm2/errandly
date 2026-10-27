import { Pressable, StyleSheet, Text, View } from "react-native";

import type { Errand } from "../api/errands";
import { categoryIcon, colors, font, metres, radius, rupees, space, statusStyle, timeAgo } from "../theme";
import { ConnectionBadge } from "./ConnectionBadge";
import { Icon } from "./icons";
import { IconTile, Pill } from "./ui";

/**
 * One errand in a list: category tile on the left, title and pickup line,
 * reward called out on the right, and a metadata strip along the bottom.
 *
 * When `onAccept` is given the strip ends in an Accept affordance instead of a
 * timestamp, which is how the runner's nearby feed presents the same card.
 */
export function ErrandCard({
  errand,
  onPress,
  showStatus = true,
  onAccept,
  accepting = false,
}: {
  errand: Errand;
  onPress?: () => void;
  showStatus?: boolean;
  onAccept?: () => void;
  accepting?: boolean;
}) {
  const status = statusStyle[errand.status];
  const distance = metres(errand.distance_m);

  return (
    <View style={s.card}>
      <Pressable onPress={onPress} style={({ pressed }) => pressed && { opacity: 0.85 }}>
        <View style={s.top}>
          <IconTile icon={categoryIcon[errand.category] ?? "gate"} size={44} />

          <View style={{ flex: 1, minWidth: 0 }}>
            <View style={s.titleRow}>
              <Text numberOfLines={2} style={s.title}>
                {errand.title}
              </Text>
              {/* Degree badge sits with the title, not the metadata row:
                  whether this came from someone you know changes how you read
                  the whole card, so it has to land in the same glance. */}
              <ConnectionBadge connection={errand.connection} />
            </View>
            <Text numberOfLines={1} style={s.sub}>
              {errand.pickup_label}
              {errand.drop_label ? ` to ${errand.drop_label}` : ""}
            </Text>

            {showStatus ? (
              <View style={{ marginTop: space.sm, alignSelf: "flex-start" }}>
                <Pill label={status.label} bg={status.bg} color={status.text} />
              </View>
            ) : null}
          </View>

          <View style={{ alignItems: "flex-end" }}>
            <Text style={s.reward}>{rupees(errand.reward)}</Text>
            <Text style={s.rewardLabel}>reward</Text>
          </View>
        </View>
      </Pressable>

      <View style={s.meta}>
        {distance ? <Meta icon="nav">{distance}</Meta> : null}
        {errand.items_total > 0 ? (
          <Meta icon="receipt">{rupees(errand.items_total)} order</Meta>
        ) : null}
        {errand.collect_amount > 0 ? (
          <Meta icon="cash" color={colors.warnText}>
            {rupees(errand.collect_amount)} to pay
          </Meta>
        ) : null}

        {onAccept ? (
          <Pressable
            onPress={onAccept}
            disabled={accepting}
            hitSlop={8}
            style={s.accept}
            accessibilityRole="button"
          >
            <Text style={s.acceptText}>{accepting ? "Accepting…" : "Accept"}</Text>
            <Icon name="chev" size={14} color={colors.brand} />
          </Pressable>
        ) : (
          <Text style={s.time}>{timeAgo(errand.created_at)}</Text>
        )}
      </View>
    </View>
  );
}

function Meta({
  icon,
  color = colors.muted,
  children,
}: {
  icon: "nav" | "receipt" | "cash" | "clock";
  color?: string;
  children: React.ReactNode;
}) {
  return (
    <View style={s.metaItem}>
      <Icon name={icon} size={14} color={color} />
      <Text style={[s.metaText, { color }]}>{children}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  card: {
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.hairline,
    borderRadius: radius.card,
    padding: space.lg,
  },
  top: { flexDirection: "row", gap: 12, alignItems: "flex-start" },
  titleRow: { flexDirection: "row", alignItems: "flex-start", gap: 8 },
  title: { flex: 1, color: colors.ink, fontSize: 14.5, fontFamily: font.bold },
  sub: { color: colors.muted, fontSize: 12, fontFamily: font.regular, marginTop: 2 },
  reward: { color: colors.moneyText, fontSize: 18, fontFamily: font.black },
  rewardLabel: { color: colors.mutedCool, fontSize: 10, fontFamily: font.regular },

  meta: {
    flexDirection: "row",
    alignItems: "center",
    gap: 14,
    marginTop: 13,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: colors.hairlineSoft,
  },
  metaItem: { flexDirection: "row", alignItems: "center", gap: 5 },
  metaText: { fontSize: 11.5, fontFamily: font.semi },
  time: { marginLeft: "auto", color: colors.muted, fontSize: 11.5, fontFamily: font.regular },
  accept: { marginLeft: "auto", flexDirection: "row", alignItems: "center", gap: 5 },
  acceptText: { color: colors.brand, fontSize: 12, fontFamily: font.bold },
});
