import { useEffect, useRef, useState } from "react";
import { Animated, Easing, Modal, Platform, Pressable, StyleSheet, Text, View } from "react-native";

import {
  resolveDialog,
  subscribeToDialogs,
  type DialogRequest,
} from "../lib/dialog";
import { colors, font, radius, shadow, space } from "../theme";
import { Icon } from "./icons";

/**
 * Draws every dialog the app asks for. Mounted once, at the root.
 *
 * A `Modal` rather than an absolutely-positioned overlay so Android's back
 * button dismisses it and the rest of the screen stops taking touches for
 * free. Tapping the scrim cancels, which is what a dismissal means: for a
 * confirm that is "no", never a silent yes.
 */
export function DialogHost() {
  const [dialog, setDialog] = useState<DialogRequest | null>(null);
  const anim = useRef(new Animated.Value(0)).current;

  useEffect(() => subscribeToDialogs(setDialog), []);

  // Visibility is driven straight off `dialog`, never off an animation
  // callback. An earlier version unmounted in Animated.start()'s completion
  // handler, and when that callback didn't fire the dialog stayed on screen
  // with its buttons dead. The animation is decoration, so it must not be
  // load-bearing for state.
  useEffect(() => {
    if (!dialog) return;
    anim.setValue(0);
    Animated.timing(anim, {
      toValue: 1,
      duration: 170,
      easing: Easing.out(Easing.cubic),
      // react-native-web ignores the native driver; opacity/transform are
      // driven from JS there either way.
      useNativeDriver: Platform.OS !== "web",
    }).start();
  }, [dialog]);

  if (!dialog) return null;
  const active = dialog;
  const hasCancel = active.cancelLabel != null;

  return (
    <Modal
      transparent
      visible
      animationType="fade" // scrim fade is the Modal's job; the card scales below
      onRequestClose={() => resolveDialog(false)}
      statusBarTranslucent
    >
      <View style={s.scrim}>
        <Pressable style={StyleSheet.absoluteFill} onPress={() => resolveDialog(false)} />

        <Animated.View
          style={[
            s.card,
            shadow.raised,
            {
              opacity: anim,
              transform: [
                { scale: anim.interpolate({ inputRange: [0, 1], outputRange: [0.92, 1] }) },
              ],
            },
          ]}
        >
          {/* A destructive confirm leads with the caution disc, so the colour
              warns before the words are read. Everything else gets the quiet
              teal one. */}
          <View
            style={[
              s.disc,
              { backgroundColor: active.destructive ? colors.cautionBg : colors.brandTint },
            ]}
          >
            <Icon
              name="alert"
              size={26}
              color={active.destructive ? colors.caution : colors.brand}
            />
          </View>
          <Text style={s.title}>{active.title}</Text>
          {active.message ? <Text style={s.message}>{active.message}</Text> : null}

          <View style={[s.actions, !hasCancel && s.actionsSingle]}>
            {hasCancel ? (
              <Pressable
                style={({ pressed }) => [s.btn, s.btnGhost, pressed && s.pressed]}
                onPress={() => resolveDialog(false)}
              >
                <Text style={s.btnGhostText}>{active.cancelLabel}</Text>
              </Pressable>
            ) : null}

            <Pressable
              style={({ pressed }) => [
                s.btn,
                active.destructive ? s.btnDanger : s.btnPrimary,
                pressed && s.pressed,
              ]}
              onPress={() => resolveDialog(true)}
            >
              <Text style={s.btnPrimaryText}>{active.confirmLabel}</Text>
            </Pressable>
          </View>
        </Animated.View>
      </View>
    </Modal>
  );
}

const s = StyleSheet.create({
  scrim: {
    flex: 1,
    backgroundColor: "rgba(14,26,25,0.55)",
    alignItems: "center",
    justifyContent: "center",
    padding: space.xl,
  },
  card: {
    width: "100%",
    maxWidth: 360,
    backgroundColor: colors.white,
    borderRadius: radius.big,
    padding: 18,
    alignItems: "center",
  },
  disc: {
    width: 52,
    height: 52,
    borderRadius: 26,
    alignItems: "center",
    justifyContent: "center",
  },
  title: {
    color: colors.ink,
    fontSize: 17,
    fontFamily: font.black,
    textAlign: "center",
    marginTop: 14,
  },
  message: {
    color: colors.muted,
    fontSize: 13.5,
    fontFamily: font.regular,
    lineHeight: 20,
    textAlign: "center",
    marginTop: 6,
  },

  actions: { flexDirection: "row", gap: 10, marginTop: space.xl, alignSelf: "stretch" },
  actionsSingle: { justifyContent: "center" },
  btn: {
    flex: 1,
    height: 46,
    borderRadius: radius.pill,
    alignItems: "center",
    justifyContent: "center",
  },
  pressed: { opacity: 0.85 },
  btnPrimary: { backgroundColor: colors.brand },
  btnDanger: { backgroundColor: colors.caution },
  btnPrimaryText: { color: colors.white, fontSize: 14, fontFamily: font.bold },
  btnGhost: { backgroundColor: colors.chip, borderWidth: 1, borderColor: colors.line },
  btnGhostText: { color: colors.muted, fontSize: 14, fontFamily: font.bold },
});
