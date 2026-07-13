import { api } from "../lib/api";

export interface Vendor {
  id: string;
  name: string;
  category: "FOOD" | "GROCERY" | "STATIONERY" | "PHARMACY";
  description: string | null;
  is_open: boolean;
}

export interface MenuItem {
  id: string;
  section: string;
  name: string;
  price: number;
  is_available: boolean;
  position: number;
}

export interface Menu {
  vendor: Vendor;
  items: MenuItem[];
  stale?: boolean;
}

export async function fetchVendors(): Promise<Vendor[]> {
  return (await api.get<Vendor[]>("/vendors")).data;
}

export async function fetchMenu(vendorId: string): Promise<Menu> {
  return (await api.get<Menu>(`/vendors/${vendorId}/menu`)).data;
}

// ---- vendor portal (role = VENDOR) ----

export async function fetchMyStore(): Promise<Vendor> {
  return (await api.get<Vendor>("/vendors/me")).data;
}

export async function updateMyStore(patch: {
  is_open?: boolean;
  description?: string;
}): Promise<Vendor> {
  return (await api.patch<Vendor>("/vendors/me", patch)).data;
}

export async function addMenuItem(item: {
  section: string;
  name: string;
  price: number;
}): Promise<MenuItem> {
  return (await api.post<MenuItem>("/vendors/me/menu-items", item)).data;
}

export async function updateMenuItem(
  id: string,
  patch: Partial<Pick<MenuItem, "section" | "name" | "price" | "is_available" | "position">>,
): Promise<MenuItem> {
  return (await api.patch<MenuItem>(`/vendors/me/menu-items/${id}`, patch)).data;
}

export async function deleteMenuItem(id: string): Promise<void> {
  await api.delete(`/vendors/me/menu-items/${id}`);
}
