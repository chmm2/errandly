import { api } from "../lib/api";

export interface TimetableSlot {
  id: string;
  day_of_week: number; // 0 = Monday
  start_minute: number;
  end_minute: number;
  label: string;
}

export async function fetchSlots(): Promise<TimetableSlot[]> {
  return (await api.get<TimetableSlot[]>("/timetable")).data;
}

export async function createSlot(slot: Omit<TimetableSlot, "id">): Promise<TimetableSlot> {
  return (await api.post<TimetableSlot>("/timetable", slot)).data;
}

export async function deleteSlot(id: string): Promise<void> {
  await api.delete(`/timetable/${id}`);
}

export interface VitSlotsResult {
  slots: TimetableSlot[];
  unknown: string[];
}

/** Replace the whole timetable from a raw VTOP paste — the backend figures out
 * whether it's the timetable grid or the registered-courses list. */
export async function setVitSlots(raw: string): Promise<VitSlotsResult> {
  return (await api.put<VitSlotsResult>("/timetable/vit", { raw })).data;
}
