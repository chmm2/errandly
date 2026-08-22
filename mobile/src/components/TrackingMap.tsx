import Constants from "expo-constants";
import { useMemo, useRef } from "react";
import { StyleSheet, View } from "react-native";
import { WebView } from "react-native-webview";

import { colors, font, radius, space } from "../theme";
import { buildMapHtml } from "../lib/mapHtml";
import { NativeTrackingMap } from "./NativeTrackingMap";
import { Caption } from "./ui";

/**
 * Live tracking map — native Google Maps when a key is configured, Leaflet
 * otherwise.
 *
 * Both paths exist on purpose. Native is the better map: smoother, styleable,
 * and what a delivery app is expected to feel like. But it needs a Google
 * Cloud key on Android, and a build without one should still ship a working
 * tracking screen rather than a blank rectangle — hence the WebView fallback,
 * which needs no key at all and matches the web client's tiles and markers.
 */
/** True when a Maps API key was present at build time (see app.config.js). */
const GOOGLE_MAPS_READY = !!Constants.expoConfig?.extra?.googleMapsConfigured;

export function TrackingMap(props: {
  drop: { lat: number; lng: number };
  runner?: { lat: number; lng: number } | null;
  height?: number;
}) {
  // Native map when we have a key; the keyless Leaflet view otherwise, so a
  // missing key costs one screen's polish rather than the whole feature.
  return GOOGLE_MAPS_READY ? <NativeTrackingMap {...props} /> : <LeafletTrackingMap {...props} />;
}

function LeafletTrackingMap({
  drop,
  runner,
  height = 240,
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
      {!runner ? (
        <View style={s.badge}>
          <Caption style={s.badgeText}>📍 Drop-off point</Caption>
        </View>
      ) : (
        <View style={s.badge}>
          <Caption style={s.badgeText}>🛵 Runner is on the move</Caption>
        </View>
      )}
    </View>
  );
}


const s = StyleSheet.create({
  wrap: {
    marginTop: space.lg,
    borderRadius: radius.xl,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.bgSoft,
  },
  web: { flex: 1, backgroundColor: "transparent" },
  badge: {
    position: "absolute",
    left: space.md,
    top: space.md,
    backgroundColor: "rgba(255,255,255,0.94)",
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: 5,
  },
  badgeText: { color: colors.ink, fontFamily: font.semi, fontSize: font.tiny },
});
