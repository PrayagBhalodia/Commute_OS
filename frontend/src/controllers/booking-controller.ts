"use client";

import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import type { CancelTripRequest } from "@/models/booking";
import type { ConfirmPlanRequest } from "@/models/journey";
import { confirmPlan } from "@/services/journey-service";
import { cancelBookingLeg, cancelBookingTrip, getBooking } from "@/services/booking-service";
import { formatInr } from "@/lib/utils";
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

export function useCancelBookingController(userId: string) {
  const queryClient = useQueryClient();
  const updateBookingConfirmation = useJourneyStore((state) => state.updateBookingConfirmation);

  const refreshWallet = () =>
    void queryClient.invalidateQueries({ queryKey: ["wallet", userId] });

  // Cancel a single leg, then refetch the booking so the UI reflects the
  // authoritative per-leg status and recomputed trip status.
  const cancelLeg = useMutation({
    mutationFn: async ({ tripId, legId }: { tripId: string; legId: string }) => {
      const result = await cancelBookingLeg(tripId, legId);
      const booking = await getBooking(tripId);
      return { result, booking };
    },
    onSuccess: ({ result, booking }) => {
      updateBookingConfirmation(booking);
      // Keep the status-sync query cache in step so it can't revert the
      // optimistic store update with a pre-cancel snapshot.
      queryClient.setQueryData(["booking", booking.trip_id], booking);
      refreshWallet();
      toast.success(
        result.refund_amount > 0
          ? `Leg cancelled — refunded ${formatInr(result.refund_amount)}`
          : result.message || "Leg cancelled",
      );
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const cancelTrip = useMutation({
    mutationFn: ({ tripId, reason }: { tripId: string; reason: CancelTripRequest }) =>
      cancelBookingTrip(tripId, reason),
    onSuccess: (booking) => {
      updateBookingConfirmation(booking);
      // Keep the status-sync query cache in step so it can't revert the
      // optimistic store update with a pre-cancel snapshot.
      queryClient.setQueryData(["booking", booking.trip_id], booking);
      refreshWallet();
      toast.success("Trip cancelled — confirmed legs refunded to your wallet");
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { cancelLeg, cancelTrip };
}

/** Keep the persisted booking in sync with the server after a reload, so a
 * trip cancelled elsewhere (or in a previous session) leaves the Active tab
 * once the authoritative status arrives. */
export function useBookingStatusSync(tripId?: string) {
  const storedStatus = useJourneyStore((state) => state.booking?.booking?.status);
  const updateBookingConfirmation = useJourneyStore((state) => state.updateBookingConfirmation);

  const bookingQuery = useQuery({
    queryKey: ["booking", tripId],
    queryFn: () => getBooking(tripId as string),
    enabled: Boolean(tripId),
    retry: 1,
  });

  useEffect(() => {
    if (bookingQuery.data && bookingQuery.data.status !== storedStatus) {
      updateBookingConfirmation(bookingQuery.data);
    }
  }, [bookingQuery.data, storedStatus, updateBookingConfirmation]);
}
