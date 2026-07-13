"use client";

import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import type { ConfirmPlanRequest } from "@/models/journey";
import { confirmPlan } from "@/services/journey-service";
import { useJourneyStore } from "@/store/journey-store";

export function useBookingController() {
  const setBooking = useJourneyStore((state) => state.setBooking);

  return useMutation({
    mutationFn: (payload: ConfirmPlanRequest) => confirmPlan(payload),
    onSuccess: (response) => {
      setBooking(response);
      if (response.status === "confirmed") toast.success(response.message || "Booking confirmed");
      else toast.warning(response.message || "Booking did not complete");
    },
    onError: (error: Error) => toast.error(error.message),
  });
}
