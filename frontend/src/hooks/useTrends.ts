"use client";

import { useQuery } from "@tanstack/react-query";
import { trendsApi } from "@/lib/api";

export function useTrending(limit = 10) {
  return useQuery({
    queryKey: ["trends", "trending", limit],
    queryFn: () => trendsApi.trending(limit),
    staleTime: 5 * 60_000,
    refetchInterval: 10 * 60_000,
    retry: 1,
  });
}

export function useAnomalies(severity?: string, limit = 10) {
  return useQuery({
    queryKey: ["trends", "anomalies", severity, limit],
    queryFn: () => trendsApi.anomalies(severity, limit),
    staleTime: 5 * 60_000,
    refetchInterval: 10 * 60_000,
    retry: 1,
  });
}
