import { z } from "zod";

export const transportModeSchema = z.enum(["cab", "auto", "flight", "train", "bus", "metro"]);
export type TransportMode = z.infer<typeof transportModeSchema>;

export interface GoalContext {
  goal_statement: string;
  purpose?: string | null;
  destination_name?: string | null;
  destination_address?: string | null;
  appointment_time?: string | null;
  return_required: boolean;
  luggage_count: number;
  required_buffer_minutes: number;
  metadata: Record<string, unknown>;
}

export interface UserPreferences {
  user_id: string;
  preferred_modes: string[];
  avoid_modes: string[];
  max_budget_inr?: number | null;
  prefer_cheapest: boolean;
  prefer_fastest: boolean;
  prefer_comfort: boolean;
  default_buffer_minutes: number;
  home_label?: string | null;
  home_lat?: number | null;
  home_lng?: number | null;
  luggage_default: number;
  notes: string[];
  interaction_count: number;
  updated_at?: string | null;
  metadata: Record<string, unknown>;
}

export interface IntentResult {
  user_id: string;
  raw_text: string;
  goal_context: GoalContext;
  origin_hint?: string | null;
  destination_hint?: string | null;
  preferences: UserPreferences;
  reasoning: string[];
  missing_fields: string[];
}

export interface PlaceInfo {
  place_id: string;
  name: string;
  address: string;
  city?: string | null;
  state?: string | null;
  lat: number;
  lng: number;
  place_type: string;
  metadata: Record<string, unknown>;
}

export interface LegOption {
  leg_id: string;
  mode: TransportMode;
  operator: string;
  origin: string;
  destination: string;
  departure: string;
  arrival: string;
  price: number;
  currency: string;
  comfort_score: number;
  service_id?: string | null;
  metadata: Record<string, unknown>;
}

export interface ItineraryOption {
  itinerary_id: string;
  trip_id: string;
  goal_context?: GoalContext | null;
  legs: LegOption[];
  total_price: number;
  total_duration_minutes: number;
  score: number;
  explanation: string;
  metadata: Record<string, unknown>;
}

export interface ThoughtStep {
  step_id: number;
  phase: "thought" | "action" | "observation" | "decision" | "wait_user" | string;
  agent?: string | null;
  title: string;
  detail: string;
  data: Record<string, unknown>;
  timestamp?: string | null;
}

export interface PlanRequest {
  user_id: string;
  goal_text: string;
  origin?: string;
  origin_lat?: number;
  origin_lng?: number;
  destination?: string;
  destination_lat?: number;
  destination_lng?: number;
  appointment_time?: string;
  return_required?: boolean;
  luggage_count?: number;
  required_buffer_minutes?: number;
  max_options: number;
  metadata?: Record<string, unknown>;
}

export interface PlanResponse {
  trip_id: string;
  user_id: string;
  intent: IntentResult;
  origin: PlaceInfo;
  destination: PlaceInfo;
  distance_km: number;
  itineraries: ItineraryOption[];
  selected_itinerary_id?: string | null;
  chain_of_thought: ThoughtStep[];
  status: "planned" | "needs_input" | "failed" | string;
  message: string;
}

export interface ConfirmPlanRequest {
  trip_id: string;
  user_id: string;
  itinerary_id: string;
  user_confirmed: boolean;
  topup_if_needed?: number | null;
  idempotency_key?: string | null;
}

// Empty form inputs arrive as "" (or NaN for number fields). The backend
// treats those as present-but-invalid values (e.g. "" is not a valid
// datetime), which returns a 422. Normalize empties to undefined so optional
// fields are simply omitted from the request body.
const emptyToUndefined = (value: unknown) =>
  value === "" || value === null || (typeof value === "number" && Number.isNaN(value))
    ? undefined
    : value;

export const planRequestSchema = z.object({
  user_id: z.string().min(1),
  goal_text: z.string().min(8),
  origin: z.preprocess(emptyToUndefined, z.string().optional()),
  destination: z.preprocess(emptyToUndefined, z.string().optional()),
  appointment_time: z.preprocess(emptyToUndefined, z.string().optional()),
  return_required: z.boolean().optional(),
  luggage_count: z.preprocess(emptyToUndefined, z.coerce.number().int().min(0).optional()),
  required_buffer_minutes: z.preprocess(emptyToUndefined, z.coerce.number().int().min(0).optional()),
  max_options: z.preprocess(emptyToUndefined, z.coerce.number().int().min(1).max(5).default(3)),
});

export const thoughtStepSchema = z.object({
  step_id: z.number(),
  phase: z.string(),
  agent: z.string().nullable().optional(),
  title: z.string(),
  detail: z.string(),
  data: z.record(z.string(), z.unknown()).default({}),
  timestamp: z.string().nullable().optional(),
});
