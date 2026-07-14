import type { ItineraryOption } from "@/models/journey";

/** The optimisation lenses the user can plan/replan by. */
export type TripPriority = "time" | "cost" | "comfort";

export const TRIP_PRIORITIES: readonly TripPriority[] = ["time", "cost", "comfort"];

export const PRIORITY_LABELS: Record<TripPriority, string> = {
  time: "Time",
  cost: "Cost",
  comfort: "Comfort",
};

/** Average comfort across an itinerary's legs (0–1). */
export function avgComfort(itinerary: ItineraryOption): number {
  if (!itinerary.legs.length) return 0;
  return itinerary.legs.reduce((sum, leg) => sum + leg.comfort_score, 0) / itinerary.legs.length;
}

/**
 * Return a NEW array of itineraries ordered so the best option for `priority`
 * comes first. Pure and deterministic — used to re-rank instantly on the
 * client whenever the user switches priority.
 */
export function rankByPriority(items: ItineraryOption[], priority: TripPriority): ItineraryOption[] {
  const ranked = [...items];
  switch (priority) {
    case "time":
      ranked.sort((a, b) => a.total_duration_minutes - b.total_duration_minutes);
      break;
    case "cost":
      ranked.sort((a, b) => a.total_price - b.total_price);
      break;
    case "comfort":
      ranked.sort((a, b) => avgComfort(b) - avgComfort(a));
      break;
  }
  return ranked;
}
