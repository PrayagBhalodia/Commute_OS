import type { UserPreferences } from "./journey";

export interface FeedbackRequest {
  user_id: string;
  trip_id?: string | null;
  rating?: number | null;
  liked?: boolean | null;
  preferred_mode?: string | null;
  avoid_mode?: string | null;
  comment?: string | null;
  selected_itinerary_id?: string | null;
  metadata?: Record<string, unknown>;
}

export type { UserPreferences };
