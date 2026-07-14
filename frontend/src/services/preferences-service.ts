import { apiClient } from "./api-client";
import type { UserPreferences } from "@/models/preferences";

export async function getPreferences(userId: string) {
  const { data } = await apiClient.get<UserPreferences>(`/os/preferences/${userId}`);
  return data;
}

export async function updatePreferences(prefs: UserPreferences) {
  const { data } = await apiClient.put<UserPreferences>(`/os/preferences/${prefs.user_id}`, prefs);
  return data;
}
