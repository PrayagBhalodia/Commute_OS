import { apiClient } from "./api-client";
import type { PlaceInfo } from "@/models/journey";

export async function getPlaces(query?: string) {
  const { data } = await apiClient.get<PlaceInfo[]>("/places", {
    params: query ? { q: query } : undefined,
  });
  return data;
}

export async function geocodePlace(query: string) {
  const { data } = await apiClient.get<PlaceInfo>("/places/geocode", {
    params: { q: query },
  });
  return data;
}
