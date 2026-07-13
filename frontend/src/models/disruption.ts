import type { BookingConfirmation } from "./booking";
import type { ItineraryOption, ThoughtStep } from "./journey";
import type { ReconciliationResult } from "./wallet";

export interface DisruptionRequest {
  trip_id: string;
  user_id: string;
  leg_id?: string | null;
  reason: string;
  severity: "low" | "medium" | "high" | string;
  auto_rebook: boolean;
  metadata?: Record<string, unknown>;
}

export interface DisruptionResponse {
  trip_id: string;
  user_id: string;
  disrupted_leg_id?: string | null;
  cancelled_legs: string[];
  refund_total: number;
  revised_itinerary?: ItineraryOption | null;
  rebooking?: BookingConfirmation | null;
  reconciliation?: ReconciliationResult | null;
  chain_of_thought: ThoughtStep[];
  status: string;
  message: string;
}
