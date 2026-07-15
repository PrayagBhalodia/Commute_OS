"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { BookingConfirmation, ConfirmPlanResponse } from "@/models/booking";
import type { ChatMessage, ChatResponse } from "@/models/chat";
import type { DisruptionResponse } from "@/models/disruption";
import type { ItineraryOption, PlanResponse, ThoughtStep } from "@/models/journey";
import type { TripPriority } from "@/lib/priority";

interface JourneyState {
  userId: string;
  goalText: string;
  /** Active optimisation lens; drives ranking + replans. */
  priority: TripPriority;
  /** Captured from the date/time modal (local ISO, e.g. "2026-07-20T09:00"). */
  startDateTime?: string;
  returnDateTime?: string;
  activePlan?: PlanResponse;
  selectedItineraryId?: string;
  /** Auto-planned return leg when the user requests a round trip. */
  returnPlan?: PlanResponse;
  selectedReturnItineraryId?: string;
  booking?: ConfirmPlanResponse;
  disruption?: DisruptionResponse;
  trace: ThoughtStep[];
  /** Home-page chat transcript; persists until the user clears the session. */
  chatMessages: ChatMessage[];
  chatSessionId?: string;
  /** Last chat response, kept so action chips survive reloads. */
  chatLatest?: ChatResponse;
  setUserId: (userId: string) => void;
  setGoalText: (goalText: string) => void;
  setPriority: (priority: TripPriority) => void;
  setSchedule: (schedule: { startDateTime?: string; returnDateTime?: string }) => void;
  setPlan: (plan: PlanResponse) => void;
  setReturnPlan: (plan: PlanResponse) => void;
  clearReturnPlan: () => void;
  selectItinerary: (itineraryId: string) => void;
  selectReturnItinerary: (itineraryId: string) => void;
  setBooking: (booking: ConfirmPlanResponse) => void;
  updateBookingConfirmation: (confirmation: BookingConfirmation) => void;
  setDisruption: (disruption: DisruptionResponse) => void;
  appendChatMessage: (message: ChatMessage) => void;
  setChatResponse: (response: ChatResponse) => void;
  clearChat: () => void;
  resetJourney: () => void;
}

export const useJourneyStore = create<JourneyState>()(
  persist(
    (set) => ({
      userId: "user-demo",
      goalText: "",
      priority: "time",
      trace: [],
      chatMessages: [],
      setUserId: (userId) => set({ userId }),
      setGoalText: (goalText) => set({ goalText }),
      setPriority: (priority) => set({ priority }),
      setSchedule: ({ startDateTime, returnDateTime }) => set({ startDateTime, returnDateTime }),
      setPlan: (plan) =>
        set({
          activePlan: plan,
          goalText: plan.intent?.raw_text || "",
          selectedItineraryId: plan.selected_itinerary_id ?? plan.itineraries[0]?.itinerary_id,
          // A fresh onward plan invalidates any previous return leg.
          returnPlan: undefined,
          selectedReturnItineraryId: undefined,
          booking: undefined,
          disruption: undefined,
          trace: plan.chain_of_thought,
        }),
      setReturnPlan: (plan) =>
        set({
          returnPlan: plan,
          selectedReturnItineraryId:
            plan.selected_itinerary_id ?? plan.itineraries[0]?.itinerary_id,
        }),
      clearReturnPlan: () => set({ returnPlan: undefined, selectedReturnItineraryId: undefined }),
      selectItinerary: (itineraryId) => set({ selectedItineraryId: itineraryId }),
      selectReturnItinerary: (itineraryId) => set({ selectedReturnItineraryId: itineraryId }),
      setBooking: (booking) =>
        set((state) => ({
          booking,
          trace: [...state.trace, ...booking.chain_of_thought],
        })),
      updateBookingConfirmation: (confirmation) =>
        set((state) =>
          state.booking
            ? { booking: { ...state.booking, booking: confirmation } }
            : {},
        ),
      setDisruption: (disruption) =>
        set((state) => ({
          disruption,
          trace: [...state.trace, ...disruption.chain_of_thought],
        })),
      appendChatMessage: (message) =>
        set((state) => ({ chatMessages: [...state.chatMessages, message] })),
      setChatResponse: (response) =>
        set((state) => ({
          chatSessionId: response.session_id,
          chatLatest: response,
          chatMessages: [...state.chatMessages, { role: "assistant", text: response.message }],
        })),
      clearChat: () =>
        set({ chatMessages: [], chatSessionId: undefined, chatLatest: undefined }),
      resetJourney: () =>
        set({
          activePlan: undefined,
          selectedItineraryId: undefined,
          returnPlan: undefined,
          selectedReturnItineraryId: undefined,
          booking: undefined,
          disruption: undefined,
          trace: [],
        }),
    }),
    { name: "commute-os-journey" },
  ),
);

export function getSelectedItinerary(plan?: PlanResponse, itineraryId?: string): ItineraryOption | undefined {
  return plan?.itineraries.find((itinerary) => itinerary.itinerary_id === itineraryId) ?? plan?.itineraries[0];
}

/** Whether the current journey has an auto-planned return leg with options. */
export function hasReturnLeg(returnPlan?: PlanResponse): boolean {
  return Boolean(returnPlan?.itineraries?.length);
}
