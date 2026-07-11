import { api } from "../lib/api";

export interface RunnerProfile {
  is_available: boolean;
  max_load: number;
  active_load: number;
  last_lat: number | null;
  last_lng: number | null;
  location_updated_at: string | null;
}

export async function fetchRunnerProfile(): Promise<RunnerProfile> {
  return (await api.get<RunnerProfile>("/runners/me")).data;
}

export async function setAvailability(
  is_available: boolean,
  location?: { lat: number; lng: number },
): Promise<RunnerProfile> {
  return (
    await api.post<RunnerProfile>("/runners/me/availability", { is_available, ...location })
  ).data;
}

export async function updateLocation(lat: number, lng: number): Promise<RunnerProfile> {
  return (await api.post<RunnerProfile>("/runners/me/location", { lat, lng })).data;
}
