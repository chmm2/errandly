import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Pressable, StyleSheet, View } from "react-native";

import { searchReferences, type ReferenceSuggestion } from "../api/fraud";
import { colors, radius, rupees, space } from "../theme";
import { Body, Caption, Field } from "./ui";

interface Props {
  value: string;
  placeholder?: string;
  /** Set once the line is bound to a priced item; cleared when edited away. */
  picked: ReferenceSuggestion | null;
  onChangeText: (name: string) => void;
  onPick: (s: ReferenceSuggestion | null) => void;
}

/**
 * Shopping-list line with type-ahead over the admin's non-MRP price list.
 *
 * Picking a suggestion is what makes the line priced, and a priced line is the
 * only kind that earns escrow headroom. Typing freely still works - not
 * everything on a shelf has been priced yet - so the control has to show which
 * of the two happened rather than quietly accepting either.
 *
 * The list renders inline rather than in an overlay: this sits inside a
 * ScrollView, and an absolutely-positioned dropdown there is clipped on
 * Android and swallows scroll gestures on both platforms.
 */
export function ItemSearchField({
  value, placeholder, picked, onChangeText, onPick,
}: Props) {
  const [focused, setFocused] = useState(false);
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), 200);
    return () => clearTimeout(t);
  }, [value]);

  const { data: hits = [] } = useQuery({
    queryKey: ["ref-search", debounced],
    queryFn: () => searchReferences(debounced),
    enabled: focused && debounced.trim().length > 0 && !picked,
    staleTime: 60_000,
  });

  return (
    <View>
      <Field
        placeholder={placeholder}
        value={value}
        onChangeText={(v) => {
          onChangeText(v);
          // Editing the text breaks the binding: a price must never outlive
          // the name it was quoted for.
          if (picked) onPick(null);
        }}
        onFocus={() => setFocused(true)}
        onBlur={() => setTimeout(() => setFocused(false), 150)}
        maxLength={120}
      />

      {picked ? (
        <View style={s.picked}>
          <Caption style={{ color: colors.brandDark, fontWeight: "700" }}>
            {rupees(picked.reference_price)} each
          </Caption>
          <Caption style={{ color: colors.muted, flex: 1 }}>
            campus price · runner may pay {rupees(picked.band_min)}–
            {rupees(picked.band_max)}
          </Caption>
        </View>
      ) : null}

      {focused && !picked && hits.length > 0 ? (
        <View style={s.list}>
          {hits.map((h) => (
            <Pressable
              key={h.reference_id}
              onPress={() => {
                onChangeText(h.display_name);
                onPick(h);
                setFocused(false);
              }}
              style={({ pressed }) => [s.hit, pressed && { backgroundColor: colors.brandSoft }]}
            >
              <View style={{ flex: 1 }}>
                <Body numberOfLines={1} style={{ fontWeight: "700" }}>
                  {h.display_name}
                </Body>
                {h.matched_via ? (
                  <Caption style={{ color: colors.muted }}>
                    also known as “{h.matched_via}”
                  </Caption>
                ) : null}
              </View>
              <Body style={{ color: colors.brandDark, fontWeight: "700" }}>
                {rupees(h.reference_price)}
              </Body>
            </Pressable>
          ))}
        </View>
      ) : null}

      {focused && !picked && debounced.trim() !== "" && hits.length === 0 ? (
        <Caption style={s.miss}>
          Not on the campus price list — the runner pays the shelf price and
          reports it.
        </Caption>
      ) : null}
    </View>
  );
}

const s = StyleSheet.create({
  picked: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.sm,
    marginTop: 4,
    paddingHorizontal: 2,
  },
  list: {
    marginTop: 6,
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: radius.lg,
    overflow: "hidden",
    backgroundColor: colors.surface,
  },
  hit: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.sm + 2,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.line,
  },
  miss: { marginTop: 4, paddingHorizontal: 2, color: colors.muted },
});
