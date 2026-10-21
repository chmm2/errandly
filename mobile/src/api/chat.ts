import { api } from "../lib/api";

export interface ChatMessage {
  id: string;
  errand_id: string;
  sender_id: string;
  sender_name: string;
  body: string;
  created_at: string;
}

export async function fetchChat(errandId: string): Promise<ChatMessage[]> {
  return (await api.get<ChatMessage[]>(`/errands/${errandId}/chat`)).data;
}

export async function sendChat(errandId: string, body: string): Promise<ChatMessage> {
  return (await api.post<ChatMessage>(`/errands/${errandId}/chat`, { body })).data;
}
