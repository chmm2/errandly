import { useMemo, useRef } from "react";
import { StyleSheet, Text, View } from "react-native";
import { WebView } from "react-native-webview";

import { buildMapHtml } from "../lib/mapHtml";
import { colors, font, radius, shadow } from "../theme";

/**
 * Live tracking map (native builds).
 *
 * Leaflet in a WebView rather than a native map component, for one practical
 * reason: react-native-maps and expo-maps both require a Google Cloud project
 * and a billable API key on Android, and OpenStreetMap tiles need neither. It
 * also matches the web client exactly, same library, same tiles, same drawn
 * markers, so tracking looks like one product on both.
 *
 * The trade is performance: a WebView map is heavier than a native one. At
 * campus scale, with two markers, that isn't the constraint.
 *
 * See TrackingMap.web.tsx for the browser build. react-native-webview has no
 * web implementation, so the web bundle renders the same Leaflet page in an
 * iframe instead.
 */
export function TrackingMap({
  drop,
  runner,
  height = 150,
}: {
  drop: { lat: number; lng: number };
  runner?: { lat: number; lng: number } | null;
  height?: number;
}) {
  const webRef = useRef<WebView>(null);

  // Built once. Runner movement is pushed in via JS below rather than by
  // re-rendering the HTML, which would tear the map down on every GPS ping.
  const html = useMemo(() => buildMapHtml(drop, runner ?? null), [drop.lat, drop.lng]);

  // Nudge the marker on each new position.
  if (runner) {
    webRef.current?.injectJavaScript(
      `window.setRunner && window.setRunner(${runner.lat}, ${runner.lng}); true;`,
    );
  }

  return (
    <View style={[s.wrap, { height }]}>
      <WebView
        ref={webRef}
        source={{ html }}
        style={s.web}
        scrollEnabled={false}
        originWhitelist={["*"]}
        javaScriptEnabled
        // Tiles come from OSM's CDN; without this Android blocks them.
        mixedContentMode="always"
      />
      <View style={[s.badge, shadow.card, { pointerEvents: "none" }]}>
        <View style={[s.dot, { backgroundColor: runner ? colors.credit : colors.mutedCool }]} />
        <Text style={s.badgeText}>{runner ? "Live" : "Drop-off"}</Text>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  wrap: {
    marginTop: 12,
    borderRadius: radius.card,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.mapBg,
  },
  web: { flex: 1, backgroundColor: "transparent" },
  badge: {
    position: "absolute",
    right: 14,
    top: 14,
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: colors.white,
    borderRadius: radius.pill,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  dot: { width: 7, height: 7, borderRadius: 3.5 },
  badgeText: { color: colors.brand, fontFamily: font.bold, fontSize: 11 },
});
