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

/** Short, de-duplicated autocomplete list for the chat's smart place input. */
export async function searchPlaces(query: string): Promise<PlaceInfo[]> {
  const q = query.trim();
  if (q.length < 2) return [];
  const results = await getPlaces(q);
  return (results ?? []).slice(0, 8);
}

/** Human label for a place, e.g. "Thaltej, Ahmedabad". */
export function placeLabel(place: Pick<PlaceInfo, "name" | "city">): string {
  const name = (place.name ?? "").trim();
  const city = (place.city ?? "").trim();
  if (city && !name.toLowerCase().includes(city.toLowerCase())) {
    return `${name}, ${city}`;
  }
  return name;
}
