import { StyleSheet, Text, View } from "react-native";

import type { Connection } from "../api/social";
import { colors, font, radius, space } from "../theme";

/**
 * LinkedIn-style degree badge: 1st, 2nd, 3rd, or R for a stranger.
 *
 * Colour carries the same information as the text, deliberately: on a feed
 * that's scanned rather than read, the difference between "someone I know"
 * and "a stranger" has to survive peripheral vision. Brand orange for a
 * direct friend, a lighter tint for indirect, neutral grey for R — so the
 * strength of the tie reads as intensity, not just a different word.
 */
export function ConnectionBadge({
  connection,
  size = "sm",
}: {
  connection?: Connection | null;
  size?: "sm" | "md";
}) {
  if (!connection) return null;

  const direct = connection.degree === 1;
  const linked = connection.degree != null && connection.degree > 1;
  const md = size === "md";

  return (
    <View
      style={[
        s.badge,
        md && s.badgeMd,
        direct && s.direct,
        linked && s.linked,
        !direct && !linked && s.stranger,
      ]}
    >
      <Text
        style={[
          s.text,
          md && s.textMd,
          direct && s.textDirect,
          linked && s.textLinked,
          !direct && !linked && s.textStranger,
        ]}
      >
        {connection.label}
      </Text>
    </View>
  );
}

/**
 * The badge plus the path in words — for detail screens, where there's room to
 * explain rather than just mark.
 */
export function ConnectionLine({ connection }: { connection?: Connection | null }) {
  if (!connection) return null;

  const detail = (() => {
    if (connection.degree === 1) return "Your friend";
    if (connection.degree === 2)
      return connection.via ? `Friend of ${connection.via}` : "Friend of a friend";
    if (connection.degree != null && connection.degree > 2)
      return connection.via
        ? `Connected through ${connection.via}`
        : `${connection.degree} connections away`;
    return "Not connected to you";
  })();

  return (
    <View style={s.line}>
      <ConnectionBadge connection={connection} size="md" />
      <Text style={s.lineText}>{detail}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  badge: {
    minWidth: 26,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: radius.pill,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
  },
  badgeMd: { minWidth: 32, paddingHorizontal: 9, paddingVertical: 3 },

  direct: { backgroundColor: colors.brand, borderColor: colors.brand },
  linked: { backgroundColor: colors.brandSoft, borderColor: "#FFD9B8" },
  stranger: { backgroundColor: colors.bgSoft, borderColor: colors.line },

  text: { fontSize: 10, fontFamily: font.black, letterSpacing: 0.2 },
  textMd: { fontSize: 12 },
  textDirect: { color: colors.white },
  textLinked: { color: colors.brandDark },
  textStranger: { color: colors.muted },

  line: { flexDirection: "row", alignItems: "center", gap: space.sm },
  lineText: { color: colors.muted, fontSize: font.small, fontFamily: font.semi },
});
