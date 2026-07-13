"use client";

import { useQuery } from "@tanstack/react-query";
import { getHealth } from "@/services/system-service";

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    refetchInterval: 30000,
    retry: 1,
  });
}
