import type { ItineraryOption, ThoughtStep, TransportMode } from "./journey";

export interface BookingRequest {
  trip_id: string;
  user_id: string;
  itinerary: ItineraryOption;
  user_confirmed: boolean;
  idempotency_key?: string | null;
  metadata: Record<string, unknown>;
}

export interface LegBookingConfirmation {
  leg_id: string;
  mode: TransportMode;
  operator: string;
  booking_ref?: string | null;
  status: "confirmed" | "failed" | "cancelled" | "pending" | string;
  price_charged: number;
  message: string;
  created_at: string;
}

export interface BookingConfirmation {
  trip_id: string;
  user_id: string;
  itinerary_id: string;
  status: "confirmed" | "failed" | "partially_cancelled" | "cancelled" | string;
  leg_confirmations: LegBookingConfirmation[];
  all_confirmed: boolean;
  total_charged: number;
  failed_legs: string[];
  error?: string | null;
  created_at: string;
}

export interface CancelTripRequest {
  reason_category: string;
  reason_note?: string | null;
}

export interface CancelLegResult {
  trip_id: string;
  leg_id: string;
  status: string;
  refund_amount: number;
  wallet_balance_after: number;
  message: string;
}

export interface ConfirmPlanResponse {
  trip_id: string;
  booking?: BookingConfirmation | null;
  wallet_balance?: number | null;
  chain_of_thought: ThoughtStep[];
  status: string;
  message: string;
}
