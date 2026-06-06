"use client";

import { useQuery } from "@tanstack/react-query";
import { dealsApi, type DealsParams } from "@/lib/api";

export function useDeals(params: DealsParams) {
  return useQuery({
    queryKey: ["deals", params],
    queryFn: () => dealsApi.list(params),
    staleTime: 30_000,
    refetchInterval: 60_000, // Auto-refresh every minute
  });
}

export function useStats() {
  return useQuery({
    queryKey: ["stats"],
    queryFn: () => dealsApi.stats(),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}
