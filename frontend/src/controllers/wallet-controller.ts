"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import type { TopUpRequest } from "@/models/wallet";
import { getWalletBalance, getWalletLedger, topUpWallet } from "@/services/wallet-service";

export function useWalletController(userId: string) {
  const queryClient = useQueryClient();
  const balanceQuery = useQuery({
    queryKey: ["wallet", userId],
    queryFn: () => getWalletBalance(userId),
    retry: 1,
  });
  const ledgerQuery = useQuery({
    queryKey: ["wallet-ledger", userId],
    queryFn: () => getWalletLedger(userId),
    retry: 1,
  });
  const topUpMutation = useMutation({
    mutationFn: (payload: TopUpRequest) => topUpWallet(userId, payload),
    onSuccess: () => {
      toast.success("Wallet topped up");
      void queryClient.invalidateQueries({ queryKey: ["wallet", userId] });
      void queryClient.invalidateQueries({ queryKey: ["wallet-ledger", userId] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { balanceQuery, ledgerQuery, topUpMutation };
}
