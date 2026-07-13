import { apiClient } from "./api-client";
import type { TopUpRequest, WalletState, WalletTransaction } from "@/models/wallet";

export async function getWalletBalance(userId: string) {
  const { data } = await apiClient.get<WalletState>(`/wallet/${userId}/balance`);
  return data;
}

export async function getWalletLedger(userId: string, tripId?: string) {
  const { data } = await apiClient.get<WalletTransaction[]>(`/wallet/${userId}/ledger`, {
    params: tripId ? { trip_id: tripId } : undefined,
  });
  return data;
}

export async function topUpWallet(userId: string, payload: TopUpRequest) {
  const { data } = await apiClient.post<WalletState>(`/wallet/${userId}/topup`, payload);
  return data;
}
