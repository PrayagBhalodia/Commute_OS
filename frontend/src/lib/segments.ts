import type { ItineraryOption } from "@/models/journey";

/** A single hop of a journey, from one waypoint to the next. */
export interface JourneySegment {
  leg_id: string;
  from: string;
  to: string;
  /** ISO timestamps from the leg, used to derive live progress. */
  departure: string;
  arrival: string;
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
    departure: leg.departure,
    arrival: leg.arrival,
  }));
}

/**
 * Live progress from the segment's own schedule: finished once the arrival
 * time has passed, ongoing between departure and arrival, upcoming before
 * departure. A trip that hasn't started yet truthfully shows every segment
 * as upcoming.
 */
export function segmentProgress(segment: JourneySegment, now: Date = new Date()): SegmentProgress {
  const time = now.getTime();
  if (new Date(segment.arrival).getTime() <= time) return "finished";
  if (new Date(segment.departure).getTime() <= time) return "ongoing";
  return "upcoming";
}

/**
 * Overall trip state for the Active page header: completed only when every
 * segment has finished, upcoming until the first one starts, else ongoing
 * (which includes waiting between two legs).
 */
export function journeyProgress(segments: JourneySegment[], now: Date = new Date()): SegmentProgress {
  if (!segments.length) return "upcoming";
  const states = segments.map((segment) => segmentProgress(segment, now));
  if (states.every((state) => state === "finished")) return "finished";
  if (states.every((state) => state === "upcoming")) return "upcoming";
  return "ongoing";
}
