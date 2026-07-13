import { apiClient } from "./api-client";
import type { BookingConfirmation, BookingRequest } from "@/models/booking";

export async function createDirectBooking(payload: BookingRequest) {
  const { data } = await apiClient.post<BookingConfirmation>("/bookings", payload);
  return data;
}

export async function getBooking(tripId: string) {
  const { data } = await apiClient.get<BookingConfirmation>(`/bookings/${tripId}`);
  return data;
}
