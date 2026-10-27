import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { type ReferenceSuggestion, searchReferences } from "../api/fraud";
import { colors, font, radius, rupees, shadow } from "../theme";
import { Icon } from "./icons";

/**
 * The search box that leads a shopping list, with type-ahead over the admin's
 * non-MRP price list.
 *
 * Picking a suggestion adds a priced line, and a priced line is the only kind
 * that earns escrow headroom. Typing freely still works, since not everything
 * on a shelf has been priced yet, so the box always offers to add exactly what
 * was typed as well, labelled as unpriced rather than quietly accepted.
 *
 * The suggestions render inline rather than in an overlay: this sits inside a
 * ScrollView, and an absolutely positioned dropdown there is clipped on Android
 * and swallows scroll gestures on both platforms.
 */
export function ItemSearchField({
  onAdd,
  placeholder = "Search the campus price list",
}: {
  onAdd: (name: string, ref: ReferenceSuggestion | null) => void;
  placeholder?: string;
}) {
  const [query, setQuery] = useState("");
  const [focused, setFocused] = useState(false);
  const [debounced, setDebounced] = useState(query);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(query), 200);
    return () => clearTimeout(t);
  }, [query]);

  const term = debounced.trim();
  const { data: hits = [] } = useQuery({
    queryKey: ["ref-search", term],
    queryFn: () => searchReferences(term),
    enabled: term.length > 0,
    staleTime: 60_000,
  });

  const typed = query.trim();
  const open = typed.length > 0;

  function add(name: string, ref: ReferenceSuggestion | null) {
    onAdd(name, ref);
    setQuery("");
  }

  return (
    <View style={{ gap: 10 }}>
      <View style={[s.box, focused && s.boxFocused]}>
        <Icon name="search" size={18} color={colors.brand} />
        <TextInput
          value={query}
          onChangeText={setQuery}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          placeholder={placeholder}
          placeholderTextColor={colors.mutedCool}
          style={s.input}
          maxLength={120}
          returnKeyType="done"
          onSubmitEditing={() => {
            // Return adds the top suggestion when there is one, otherwise the
            // line exactly as typed.
            if (hits[0]) add(hits[0].display_name, hits[0]);
            else if (typed) add(typed, null);
          }}
        />
        <Text style={s.tag}>Campus prices</Text>
      </View>

      {open ? (
        <View style={[s.list, shadow.card]}>
          {hits.map((h, i) => (
            <Pressable
              key={h.reference_id}
              onPress={() => add(h.display_name, h)}
              style={({ pressed }) => [
                s.hit,
                i === 0 && { backgroundColor: colors.bgSoft },
                i > 0 && s.divider,
                pressed && { backgroundColor: colors.brandTint },
              ]}
              accessibilityRole="button"
              accessibilityLabel={`Add ${h.display_name}`}
            >
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text numberOfLines={1} style={s.hitName}>
                  {h.display_name}
                </Text>
                <Text numberOfLines={1} style={s.hitSub}>
                  {h.matched_via
                    ? `also known as “${h.matched_via}”`
                    : `runner may pay ${rupees(h.band_min)} to ${rupees(h.band_max)}`}
                </Text>
              </View>
              <Text style={s.price}>{Math.round(h.reference_price)}</Text>
              <View style={[s.plus, i === 0 && s.plusPrimary]}>
                <Icon name="plus" size={15} color={i === 0 ? colors.white : colors.brand} />
              </View>
            </Pressable>
          ))}

          <Pressable
            onPress={() => add(typed, null)}
            style={({ pressed }) => [
              s.hit,
              hits.length > 0 && s.divider,
              pressed && { backgroundColor: colors.brandTint },
            ]}
            accessibilityRole="button"
            accessibilityLabel={`Add ${typed} as typed`}
          >
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text numberOfLines={1} style={s.hitName}>
                Add “{typed}”
              </Text>
              <Text style={s.hitSub}>Not on the price list, the runner reports it</Text>
            </View>
            <View style={s.plus}>
              <Icon name="plus" size={15} color={colors.brand} />
            </View>
          </Pressable>
        </View>
      ) : null}
    </View>
  );
}

const s = StyleSheet.create({
  box: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: radius.lg,
    paddingHorizontal: 14,
    backgroundColor: colors.white,
  },
  boxFocused: { borderWidth: 1.5, borderColor: colors.brand },
  input: {
    flex: 1,
    paddingVertical: 13,
    color: colors.ink,
    fontSize: 14,
    fontFamily: font.regular,
  },
  tag: {
    color: colors.mutedCool,
    fontSize: 10.5,
    fontFamily: font.bold,
    letterSpacing: 0.6,
    textTransform: "uppercase",
  },

  list: {
    borderWidth: 1,
    borderColor: colors.hairline,
    borderRadius: radius.lg,
    overflow: "hidden",
    backgroundColor: colors.white,
  },
  hit: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  divider: { borderTopWidth: 1, borderTopColor: colors.hairlineSoft },
  hitName: { color: colors.ink, fontSize: 13.5, fontFamily: font.semi },
  hitSub: { color: colors.mutedCool, fontSize: 10.5, fontFamily: font.regular, marginTop: 1 },
  price: { color: colors.inkSoft, fontSize: 12, fontFamily: font.mono },
  plus: {
    width: 26,
    height: 26,
    borderRadius: 13,
    backgroundColor: colors.brandTint,
    alignItems: "center",
    justifyContent: "center",
  },
  plusPrimary: { backgroundColor: colors.brand },
});
