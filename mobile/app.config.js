/**
 * Expo config as JS rather than JSON so values can come from the environment
 * at build time. Nothing secret belongs in here — this file is committed.
 */

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
      // POST_NOTIFICATIONS is required from Android 13 (API 33). Without it in
      // the manifest the runtime prompt never appears, requestPermissionsAsync
      // resolves as denied, and push registration fails silently — which is
      // exactly why no device had ever registered a token.
      permissions: [
        "ACCESS_COARSE_LOCATION",
        "ACCESS_FINE_LOCATION",
        "POST_NOTIFICATIONS",
      ],
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
    ],

    experiments: { typedRoutes: true },

    extra: {
      eas: { projectId: "5d3cf351-8d76-438e-a29f-5c66d768a254" },
    },
  },
};
