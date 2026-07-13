import type { BookingConfirmation } from "@/models/booking";
import type { ItineraryOption } from "@/models/journey";
import { JourneyLegCard } from "./JourneyLegCard";

export function JourneyTimeline({ itinerary, booking }: { itinerary: ItineraryOption; booking?: BookingConfirmation | null }) {
  return (
    <div className="space-y-3">
      {itinerary.legs.map((leg, index) => {
        const conf = booking?.leg_confirmations.find((item) => item.leg_id === leg.leg_id);
        const next = itinerary.legs[index + 1];
        const buffer = next ? Math.round((new Date(next.departure).getTime() - new Date(leg.arrival).getTime()) / 60000) : null;
        return (
          <div key={leg.leg_id}>
            <JourneyLegCard leg={leg} status={conf?.status} />
            {buffer !== null ? <p className="ml-14 mt-2 text-xs text-slate-500">Connection buffer: {Math.max(0, buffer)} min</p> : null}
          </div>
        );
      })}
    </div>
  );
}
