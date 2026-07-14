import { apiClient } from "./api-client";
import type {
  BookingConfirmation,
  BookingRequest,
  CancelLegResult,
  CancelTripRequest,
} from "@/models/booking";

export async function createDirectBooking(payload: BookingRequest) {
  const { data } = await apiClient.post<BookingConfirmation>("/bookings", payload);
  return data;
}

export async function getBooking(tripId: string) {
  const { data } = await apiClient.get<BookingConfirmation>(`/bookings/${tripId}`);
  return data;
}

export async function cancelBookingLeg(tripId: string, legId: string) {
  const { data } = await apiClient.post<CancelLegResult>(
    `/bookings/${tripId}/legs/${legId}/cancel`,
  );
  return data;
}

export async function cancelBookingTrip(tripId: string, reason: CancelTripRequest) {
  const { data } = await apiClient.post<BookingConfirmation>(
    `/bookings/${tripId}/cancel`,
    reason,
  );
  return data;
}
