import type { ItineraryOption } from "@/models/journey";

/** A single hop of a journey, from one waypoint to the next. */
export interface JourneySegment {
  leg_id: string;
  from: string;
  to: string;
}

/** Progress state used to label segments on the Active journey view. */
export type SegmentProgress = "finished" | "ongoing" | "upcoming";

export const SEGMENT_PROGRESS_LABEL: Record<SegmentProgress, string> = {
  finished: "Finished",
  ongoing: "Ongoing",
  upcoming: "Upcoming",
};

/**
 * The first origin and final destination of an itinerary, e.g. the
 * "Initial → Final" summary shown on the History and Active pages.
 */
export function journeyEndpoints(itinerary?: ItineraryOption | null): { initial: string; final: string } {
  const legs = itinerary?.legs ?? [];
  return {
    initial: legs[0]?.origin ?? "Origin",
    final: legs[legs.length - 1]?.destination ?? "Destination",
  };
}

/** One segment per leg (Initial → Intermediate 1 → … → Final). */
export function journeySegments(itinerary?: ItineraryOption | null): JourneySegment[] {
  return (itinerary?.legs ?? []).map((leg) => ({
    leg_id: leg.leg_id,
    from: leg.origin,
    to: leg.destination,
  }));
}

/**
 * Demo progress heuristic: the middle-ish leg is "ongoing", earlier legs are
 * "finished", later legs are "upcoming". With the classic 3-leg journey this
 * yields Finished → Ongoing → Upcoming. There is no live tracking backend, so
 * this gives a believable in-progress snapshot.
 */
export function segmentProgress(index: number, total: number): SegmentProgress {
  if (total <= 1) return "ongoing";
  const ongoingIndex = Math.min(1, total - 1);
  if (index < ongoingIndex) return "finished";
  if (index === ongoingIndex) return "ongoing";
  return "upcoming";
}
