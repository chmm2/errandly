import { api } from "../lib/api";

export interface Notification {
  id: string;
  type: string;
  title: string;
  body: string | null;
  data: Record<string, unknown> | null;
  read_at: string | null;
  created_at: string;
}

export interface NotificationList {
  items: Notification[];
  unread: number;
}

export async function fetchNotifications(): Promise<NotificationList> {
  return (await api.get<NotificationList>("/notifications")).data;
}

export async function markAllRead(): Promise<void> {
  await api.post("/notifications/read");
}

/** Tell the backend this device can receive OS-level pushes. */
export async function registerPushToken(token: string, platform?: string): Promise<void> {
  await api.post("/notifications/push-token", { token, platform });
}

/** Drop this device on logout, so the next user here doesn't get your pushes. */
export async function unregisterPushToken(token: string): Promise<void> {
  await api.delete("/notifications/push-token", { data: { token } });
}
