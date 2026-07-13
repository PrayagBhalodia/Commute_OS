"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import type { PlanRequest } from "@/models/journey";
import { DEMO_USER_ID } from "@/constants/demo";
import { planJourney, submitFeedback } from "@/services/journey-service";
import { getPreferences } from "@/services/preferences-service";
import { useJourneyStore } from "@/store/journey-store";

export function useJourneyController() {
  const queryClient = useQueryClient();
  const setPlan = useJourneyStore((state) => state.setPlan);

  const planMutation = useMutation({
    mutationFn: (payload: PlanRequest) => planJourney(payload),
    onSuccess: (plan) => {
      setPlan(plan);
      toast.success(plan.message || "Journey options ready");
      void queryClient.invalidateQueries({ queryKey: ["preferences", plan.user_id] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { planMutation };
}

export function usePreferencesController(userId = DEMO_USER_ID) {
  return useQuery({
    queryKey: ["preferences", userId],
    queryFn: () => getPreferences(userId),
    staleTime: 15000,
    retry: 1,
  });
}

export function useFeedbackController() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: submitFeedback,
    onSuccess: (prefs) => {
      toast.success("Travel DNA updated");
      void queryClient.invalidateQueries({ queryKey: ["preferences", prefs.user_id] });
    },
    onError: (error: Error) => toast.error(error.message),
  });
}
