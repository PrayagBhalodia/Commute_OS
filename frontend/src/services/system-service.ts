import { apiClient } from "./api-client";

export interface HealthResponse {
  status: string;
  service: string;
  agents: string[];
  google_maps: boolean;
  maps_provider: "google" | "openstreetmap" | "offline";
  nominatim: boolean;
}

export async function getHealth() {
  const { data } = await apiClient.get<HealthResponse>("/health");
  return data;
}

export async function getOperatorCatalog() {
  const { data } = await apiClient.get<Record<string, string[]>>("/operators/catalog");
  return data;
}
