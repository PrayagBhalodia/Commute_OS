import type { ItineraryOption } from "@/models/journey";

/** The four optimisation lenses the user can plan/replan by. */
export type TripPriority = "time" | "cost" | "eco" | "comfort";

export const TRIP_PRIORITIES: readonly TripPriority[] = ["time", "cost", "eco", "comfort"];

export const PRIORITY_LABELS: Record<TripPriority, string> = {
  time: "Time",
  cost: "Cost",
  eco: "Eco",
  comfort: "Comfort",
};

// Relative per-leg environmental impact by mode (lower = greener). The backend
// no longer models emissions, so we derive an eco ranking from the transport
// mix instead. Rail/metro are greenest; flights are the heaviest footprint.
const MODE_ECO_WEIGHT: Record<string, number> = {
  metro: 1,
  train: 1.2,
  bus: 1.6,
  auto: 2.6,
  cab: 4,
  flight: 9,
};

/** Average comfort across an itinerary's legs (0–1). */
export function avgComfort(itinerary: ItineraryOption): number {
  if (!itinerary.legs.length) return 0;
  return itinerary.legs.reduce((sum, leg) => sum + leg.comfort_score, 0) / itinerary.legs.length;
}

/** Summed mode-based environmental impact (lower = greener). */
export function ecoImpact(itinerary: ItineraryOption): number {
  if (!itinerary.legs.length) return Number.POSITIVE_INFINITY;
  return itinerary.legs.reduce((sum, leg) => sum + (MODE_ECO_WEIGHT[leg.mode] ?? 4), 0);
}

/** Qualitative footprint label for display on comparison cards. */
export function ecoLabel(itinerary: ItineraryOption): { text: string; tone: "green" | "amber" | "red" } {
  const modes = new Set(itinerary.legs.map((leg) => leg.mode));
  if (modes.has("flight")) return { text: "Higher footprint", tone: "red" };
  if (modes.has("train") || modes.has("metro") || modes.has("bus")) {
    return { text: "Low footprint", tone: "green" };
  }
  return { text: "Moderate footprint", tone: "amber" };
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
    case "eco":
      ranked.sort((a, b) => ecoImpact(a) - ecoImpact(b));
      break;
  }
  return ranked;
}
