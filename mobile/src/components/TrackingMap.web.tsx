import { useEffect, useRef } from "react";
import { StyleSheet, View } from "react-native";

import { buildMapHtml } from "../lib/mapHtml";
import { colors, font, radius, space } from "../theme";
import { Caption } from "./ui";

/**
 * Web build of the tracking map.
 *
 * Metro picks this file over TrackingMap.tsx on web, which matters for more
 * than looks: neither react-native-maps nor react-native-webview has a web
 * implementation — MapView.web.ts is literally an UnimplementedView — so the
 * map was a blank rectangle in the browser preview. Resolving to this file
 * keeps both packages out of the web bundle entirely.
 *
 * On web we're already in a browser, so Leaflet goes straight into an iframe.
 * Same HTML the native WebView renders, so the two stay in sync by
 * construction.
 */
export function TrackingMap({
  drop,
  runner,
  height = 240,
}: {
  drop: { lat: number; lng: number };
  runner?: { lat: number; lng: number } | null;
  height?: number;
}) {
  const frameRef = useRef<HTMLIFrameElement | null>(null);

  // Push new positions into the existing document instead of re-rendering it;
  // reassigning srcDoc would rebuild the map on every GPS ping.
  useEffect(() => {
    if (!runner) return;
    const win = frameRef.current?.contentWindow as
      | (Window & { setRunner?: (lat: number, lng: number) => void })
      | null
      | undefined;
    win?.setRunner?.(runner.lat, runner.lng);
  }, [runner?.lat, runner?.lng]);

  return (
    <View style={[s.wrap, { height }]}>
      <iframe
        ref={frameRef}
        srcDoc={buildMapHtml(drop, runner ?? null)}
        style={{ border: "none", width: "100%", height: "100%", display: "block" }}
        title="Live tracking map"
      />
      <View style={[s.badge, { pointerEvents: "none" }]}>
        <Caption style={s.badgeText}>
          {runner ? "🛵 Runner is on the move" : "📍 Drop-off point"}
        </Caption>
      </View>
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
