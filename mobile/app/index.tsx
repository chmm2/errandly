import { Redirect } from "expo-router";

import { useAuth } from "../src/stores/auth";

/** Entry point: bounce straight to the right half of the app. */
export default function Index() {
  const token = useAuth((s) => s.accessToken);
  return <Redirect href={token ? "/(tabs)" : "/(auth)/login"} />;
}
