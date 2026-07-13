"use client";

import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import type { DisruptionRequest } from "@/models/disruption";
import { disruptJourney } from "@/services/journey-service";
import { useJourneyStore } from "@/store/journey-store";

export function useDisruptionController() {
  const setDisruption = useJourneyStore((state) => state.setDisruption);
  return useMutation({
    mutationFn: (payload: DisruptionRequest) => disruptJourney(payload),
    onSuccess: (response) => {
      setDisruption(response);
      toast.warning(response.message || "Disruption handled");
    },
    onError: (error: Error) => toast.error(error.message),
  });
}
