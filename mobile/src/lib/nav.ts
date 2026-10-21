import { useRouter } from "expo-router";

// The object useRouter() returns; expo-router does not export the type itself.
type Router = ReturnType<typeof useRouter>;

/**
 * Go back, or go somewhere sensible when there is nothing to go back to.
 *
 * `router.back()` alone dispatches GO_BACK into an empty history whenever a
 * screen was opened directly rather than navigated into — a deep link, a web
 * reload, or a tapped push notification, which lands straight on
 * /errand/{id}. React Navigation then warns "GO_BACK was not handled by any
 * navigator" and, more to the point, the button does nothing.
 *
 * So: pop the stack if there is one, otherwise replace with a root the user
 * can actually continue from.
 */
export function goBack(router: Router, fallback: "tabs" | "login" = "tabs") {
  if (router.canGoBack()) {
    router.back();
    return;
  }
  router.replace(fallback === "login" ? "/(auth)/login" : "/(tabs)");
}
