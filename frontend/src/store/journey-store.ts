"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { ConfirmPlanResponse } from "@/models/booking";
import type { DisruptionResponse } from "@/models/disruption";
import type { ItineraryOption, PlanResponse, ThoughtStep } from "@/models/journey";

interface JourneyState {
  userId: string;
  activePlan?: PlanResponse;
  selectedItineraryId?: string;
  booking?: ConfirmPlanResponse;
  disruption?: DisruptionResponse;
  trace: ThoughtStep[];
  setUserId: (userId: string) => void;
  setPlan: (plan: PlanResponse) => void;
  selectItinerary: (itineraryId: string) => void;
  setBooking: (booking: ConfirmPlanResponse) => void;
  setDisruption: (disruption: DisruptionResponse) => void;
  resetJourney: () => void;
}

export const useJourneyStore = create<JourneyState>()(
  persist(
    (set) => ({
      userId: "user-demo",
      trace: [],
      setUserId: (userId) => set({ userId }),
      setPlan: (plan) =>
        set({
          activePlan: plan,
          selectedItineraryId: plan.selected_itinerary_id ?? plan.itineraries[0]?.itinerary_id,
          booking: undefined,
          disruption: undefined,
          trace: plan.chain_of_thought,
        }),
      selectItinerary: (itineraryId) => set({ selectedItineraryId: itineraryId }),
      setBooking: (booking) =>
        set((state) => ({
          booking,
          trace: [...state.trace, ...booking.chain_of_thought],
        })),
      setDisruption: (disruption) =>
        set((state) => ({
          disruption,
          trace: [...state.trace, ...disruption.chain_of_thought],
        })),
      resetJourney: () =>
        set({ activePlan: undefined, selectedItineraryId: undefined, booking: undefined, disruption: undefined, trace: [] }),
    }),
    { name: "commute-os-journey" },
  ),
);

export function getSelectedItinerary(plan?: PlanResponse, itineraryId?: string): ItineraryOption | undefined {
  return plan?.itineraries.find((itinerary) => itinerary.itinerary_id === itineraryId) ?? plan?.itineraries[0];
}
