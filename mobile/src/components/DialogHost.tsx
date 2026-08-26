import { useEffect, useRef, useState } from "react";
import { Animated, Easing, Modal, Platform, Pressable, StyleSheet, Text, View } from "react-native";

import {
  resolveDialog,
  subscribeToDialogs,
  type DialogRequest,
} from "../lib/dialog";
import { colors, font, radius, shadow, space } from "../theme";

/**
 * Draws every dialog the app asks for. Mounted once, at the root.
 *
 * A `Modal` rather than an absolutely-positioned overlay so Android's back
 * button dismisses it and the rest of the screen stops taking touches for
 * free. Tapping the scrim cancels, which is what a dismissal means — for a
 * confirm that is "no", never a silent yes.
 */
export function DialogHost() {
  const [dialog, setDialog] = useState<DialogRequest | null>(null);
  const anim = useRef(new Animated.Value(0)).current;

  useEffect(() => subscribeToDialogs(setDialog), []);

  // Visibility is driven straight off `dialog`, never off an animation
  // callback. An earlier version unmounted in Animated.start()'s completion
  // handler, and when that callback didn't fire the dialog stayed on screen
  // with its buttons dead — the animation is decoration, so it must not be
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
    backgroundColor: "rgba(20,22,30,0.55)",
    alignItems: "center",
    justifyContent: "center",
    padding: space.xl,
  },
  card: {
    width: "100%",
    maxWidth: 380,
    backgroundColor: colors.white,
    borderRadius: radius.xxl,
    padding: space.xxl,
  },
  title: {
    color: colors.ink,
    fontSize: font.h3,
    fontFamily: font.black,
    textAlign: "center",
  },
  message: {
    color: colors.muted,
    fontSize: font.body,
    fontFamily: font.regular,
    lineHeight: 21,
    textAlign: "center",
    marginTop: space.sm,
  },

  actions: { flexDirection: "row", gap: space.sm, marginTop: space.xxl },
  actionsSingle: { justifyContent: "center" },
  btn: {
    flex: 1,
    height: 48,
    borderRadius: radius.pill,
    alignItems: "center",
    justifyContent: "center",
  },
  pressed: { opacity: 0.85 },
  btnPrimary: { backgroundColor: colors.brand },
  btnDanger: { backgroundColor: colors.redText },
  btnPrimaryText: { color: colors.white, fontSize: font.body, fontFamily: font.bold },
  btnGhost: { backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.line },
  btnGhostText: { color: colors.muted, fontSize: font.body, fontFamily: font.bold },
});
