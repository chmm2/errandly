import { useEffect, useRef } from "react";
import { StyleSheet, Text, View } from "react-native";
import MapView, { Marker, PROVIDER_GOOGLE, type MapViewProps } from "react-native-maps";

import { MAP_STYLE } from "../mapStyle";
import { colors, font, radius, space } from "../theme";
import { Caption } from "./ui";

/**
 * Native Google Maps tracking view.
 *
 * Used only when a Maps API key was present at build time; without one the
 * caller falls back to the keyless Leaflet map. Markers are emoji in plain
 * Views, matching the web client and avoiding image assets entirely.
 */
export function NativeTrackingMap({
  drop,
  runner,
  height = 240,
}: {
  drop: { lat: number; lng: number };
  runner?: { lat: number; lng: number } | null;
  height?: number;
}) {
  const mapRef = useRef<MapView>(null);

  // Keep both pins in frame as the runner closes in. Animating beats
  // re-rendering with a new region, which fights the user's own panning.
  useEffect(() => {
    if (!runner || !mapRef.current) return;
    mapRef.current.fitToCoordinates(
      [
        { latitude: drop.lat, longitude: drop.lng },
        { latitude: runner.lat, longitude: runner.lng },
      ],
      { edgePadding: { top: 60, right: 60, bottom: 60, left: 60 }, animated: true },
    );
  }, [runner?.lat, runner?.lng, drop.lat, drop.lng]);

  // PROVIDER_GOOGLE on iOS too, so the custom style renders identically —
  // Apple Maps ignores Google style JSON.
  const provider: MapViewProps["provider"] = PROVIDER_GOOGLE;

  return (
    <View style={[s.wrap, { height }]}>
      <MapView
        ref={mapRef}
        provider={provider}
        style={StyleSheet.absoluteFill}
        customMapStyle={MAP_STYLE}
        initialRegion={{
          latitude: drop.lat,
          longitude: drop.lng,
          latitudeDelta: 0.008,
          longitudeDelta: 0.008,
        }}
        showsUserLocation={false}
        toolbarEnabled={false}
        // The card is inside a scroll view; let the page win vertical drags
        // unless the user is clearly interacting with the map.
        moveOnMarkerPress={false}
      >
        <Marker
          coordinate={{ latitude: drop.lat, longitude: drop.lng }}
          anchor={{ x: 0.5, y: 0.9 }}
          tracksViewChanges={false}
        >
          <Text style={s.pin}>📍</Text>
        </Marker>

        {runner ? (
          <Marker
            coordinate={{ latitude: runner.lat, longitude: runner.lng }}
            anchor={{ x: 0.5, y: 0.5 }}
            tracksViewChanges={false}
          >
            <Text style={s.scooter}>🛵</Text>
          </Marker>
        ) : null}
      </MapView>

      <View style={s.badge}>
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
  pin: { fontSize: 30 },
  scooter: { fontSize: 30 },
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
