import type { LegOption, PlanResponse } from "@/models/journey";

export interface ChatAction {
  id: string;
  label: string;
  message: string;
  kind: "message" | "location" | "confirm" | string;
  href?: string | null;
}

export interface LegOptionGroup {
  leg_number: number;
  origin: string;
  destination: string;
  default_leg_id: string;
  options: LegOption[];
}

export interface JourneyReview {
  itinerary_id: string;
  total_price: number;
  total_duration_minutes: number;
  departure?: string | null;
  arrival?: string | null;
  legs: LegOption[];
  booking_requires_confirmation: boolean;
}

export interface ChatResponse {
  session_id: string;
  user_id: string;
  message: string;
  state: { status: string };
  suggested_actions: ChatAction[];
  leg_option_groups: LegOptionGroup[];
  journey_review?: JourneyReview | null;
  tool_results: Array<{
    ok: boolean;
    tool: string;
    data?: PlanResponse & Record<string, unknown>;
  }>;
  mode: string;
}

export interface ChatRequest {
  session_id?: string;
  user_id: string;
  message: string;
  client_time: string;
  timezone: string;
  current_lat?: number;
  current_lng?: number;
  current_location_label?: string;
}
