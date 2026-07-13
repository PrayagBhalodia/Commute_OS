import { apiClient } from "./api-client";
import type { UserPreferences } from "@/models/preferences";

export async function getPreferences(userId: string) {
  const { data } = await apiClient.get<UserPreferences>(`/os/preferences/${userId}`);
  return data;
}
