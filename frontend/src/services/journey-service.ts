import { apiClient } from "./api-client";
import type { ConfirmPlanRequest, PlanRequest, PlanResponse } from "@/models/journey";
import type { ConfirmPlanResponse } from "@/models/booking";
import type { DisruptionRequest, DisruptionResponse } from "@/models/disruption";
import type { FeedbackRequest, UserPreferences } from "@/models/preferences";

export async function planJourney(payload: PlanRequest) {
  const { data } = await apiClient.post<PlanResponse>("/os/plan", payload);
  return data;
}

export async function getPlan(tripId: string) {
  const { data } = await apiClient.get<PlanResponse>(`/os/plan/${tripId}`);
  return data;
}

export async function confirmPlan(payload: ConfirmPlanRequest) {
  const { data } = await apiClient.post<ConfirmPlanResponse>("/os/confirm", payload);
  return data;
}

export async function disruptJourney(payload: DisruptionRequest) {
  const { data } = await apiClient.post<DisruptionResponse>("/os/disrupt", payload);
  return data;
}

export async function submitFeedback(payload: FeedbackRequest) {
  const { data } = await apiClient.post<UserPreferences>("/os/feedback", payload);
  return data;
}
