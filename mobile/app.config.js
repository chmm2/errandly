/**
 * Expo config as JS rather than JSON so the Google Maps key can come from the
 * environment.
 *
 * The key must never be committed: app.json is in version control, and a Maps
 * key in a public repo gets scraped and billed to you. It's read from
 * GOOGLE_MAPS_API_KEY instead — supplied locally via mobile/.env.local and to
 * EAS via `eas secret:create`.
 *
 * Builds still succeed without it; the map just falls back to the keyless
 * Leaflet view, so a missing key degrades one screen rather than the app.
 */

const GOOGLE_MAPS_API_KEY = process.env.GOOGLE_MAPS_API_KEY ?? "";

module.exports = {
  expo: {
    name: "Errandly",
    slug: "errandly",
    owner: "chm2s-team",
    scheme: "errandly",
    version: "1.0.0",
    orientation: "portrait",
    icon: "./assets/icon.png",
    userInterfaceStyle: "light",
    newArchEnabled: true,

    ios: {
      supportsTablet: false,
      bundleIdentifier: "in.errandly.app",
      config: GOOGLE_MAPS_API_KEY ? { googleMapsApiKey: GOOGLE_MAPS_API_KEY } : undefined,
      infoPlist: {
        NSLocationWhenInUseUsageDescription:
          "Errandly uses your location to match you with nearby errands and to show your live position while you run one.",
        NSAppTransportSecurity: {
          NSAllowsArbitraryLoads: true,
          NSAllowsLocalNetworking: true,
        },
      },
    },

    android: {
      package: "in.errandly.app",
      usesCleartextTraffic: true,
      adaptiveIcon: {
        backgroundColor: "#0B0F1A",
        foregroundImage: "./assets/android-icon-foreground.png",
        backgroundImage: "./assets/android-icon-background.png",
        monochromeImage: "./assets/android-icon-monochrome.png",
      },
      permissions: ["ACCESS_COARSE_LOCATION", "ACCESS_FINE_LOCATION"],
      predictiveBackGestureEnabled: false,
    },

    web: { favicon: "./assets/favicon.png" },

    plugins: [
      "expo-router",
      "expo-status-bar",
      [
        "expo-location",
        {
          locationWhenInUsePermission:
            "Errandly uses your location to match you with nearby errands and to show your live position while you run one.",
        },
      ],
      "expo-font",
      ["expo-notifications", { color: "#FC8019", defaultChannel: "default" }],
      // Only registered when a key exists — the plugin fails the build without one.
      ...(GOOGLE_MAPS_API_KEY
        ? [["react-native-maps", { androidGoogleMapsApiKey: GOOGLE_MAPS_API_KEY }]]
        : []),
    ],

    experiments: { typedRoutes: true },

    extra: {
      eas: { projectId: "5d3cf351-8d76-438e-a29f-5c66d768a254" },
      // Read at runtime to decide native map vs Leaflet fallback.
      googleMapsConfigured: !!GOOGLE_MAPS_API_KEY,
    },
  },
};
