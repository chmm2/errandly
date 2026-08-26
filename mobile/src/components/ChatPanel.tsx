import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { type ChatMessage, fetchChat, sendChat } from "../api/chat";
import { useSocket } from "../lib/ws";
import { useAuth } from "../stores/auth";
import { colors, font, radius, space } from "../theme";
import { Caption, Card, Heading, Row } from "./ui";

export function ChatPanel({ errandId }: { errandId: string }) {
  const myId = useAuth((s) => s.user?.id);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);

  const { data } = useQuery({
    queryKey: ["chat", errandId],
    queryFn: () => fetchChat(errandId),
  });

  useEffect(() => {
    if (data) setMessages(data);
  }, [data]);

  // Chat rides the errand's status channel — same socket the tracker uses.
  useSocket(
    `/ws/errands/${errandId}`,
    useCallback((payload: Record<string, unknown>) => {
      if (payload.type !== "chat") return;
      const msg = payload as unknown as ChatMessage;
      // Our own message echoes back over the socket — dedupe on id.
      setMessages((prev) => (prev.some((m) => m.id === msg.id) ? prev : [...prev, msg]));
    }, []),
  );

  async function send() {
    const body = draft.trim();
    if (!body || sending) return;
    setSending(true);
    setDraft("");
    try {
      const msg = await sendChat(errandId, body);
      setMessages((prev) => (prev.some((m) => m.id === msg.id) ? prev : [...prev, msg]));
    } catch {
      setDraft(body); // put it back so nothing is silently lost
    } finally {
      setSending(false);
    }
  }

  return (
    <>
      <Heading style={{ marginTop: space.xxl, marginBottom: space.md }}>Chat</Heading>
      <Card style={{ padding: space.md, gap: space.sm }}>
        {messages.length === 0 ? (
          <Caption style={{ textAlign: "center", paddingVertical: space.lg }}>
            Say hi — messages are delivered instantly.
          </Caption>
        ) : (
          <View style={{ gap: space.sm }}>
            {messages.slice(-30).map((m) => {
              const mine = m.sender_id === myId;
              return (
                <View key={m.id} style={[s.bubbleRow, mine && { justifyContent: "flex-end" }]}>
                  <View style={[s.bubble, mine ? s.mine : s.theirs]}>
                    {!mine ? <Text style={s.sender}>{m.sender_name}</Text> : null}
                    <Text style={[s.text, mine && { color: colors.white }]}>{m.body}</Text>
                  </View>
                </View>
              );
            })}
          </View>
        )}

        <Row gap={space.sm} style={{ marginTop: space.xs }}>
          <TextInput
            value={draft}
            onChangeText={setDraft}
            placeholder="Message…"
            placeholderTextColor={colors.muted}
            style={s.input}
            maxLength={2000}
            returnKeyType="send"
            onSubmitEditing={send}
          />
          <Pressable
            onPress={send}
            disabled={!draft.trim() || sending}
            style={[s.send, (!draft.trim() || sending) && { opacity: 0.4 }]}
          >
            <Text style={{ fontSize: 15, color: colors.white }}>➤</Text>
          </Pressable>
        </Row>
      </Card>
    </>
  );
}

const s = StyleSheet.create({
  bubbleRow: { flexDirection: "row" },
  bubble: {
    maxWidth: "82%",
    borderRadius: radius.lg,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
  },
  mine: { backgroundColor: colors.brand, borderBottomRightRadius: 4 },
  theirs: { backgroundColor: colors.brandSoft, borderBottomLeftRadius: 4 },
  sender: { color: colors.brandDark, fontFamily: font.bold, fontSize: font.tiny, marginBottom: 2 },
  text: { color: colors.ink, fontSize: font.body, fontFamily: font.regular, lineHeight: 20 },

  input: {
    flex: 1,
    backgroundColor: colors.white,
    borderRadius: radius.pill,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    color: colors.ink,
    fontSize: font.body,
    fontFamily: font.regular,
    borderWidth: 1,
    borderColor: colors.line,
  },
  send: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.brand,
    alignItems: "center",
    justifyContent: "center",
  },
});
