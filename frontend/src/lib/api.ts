import axios from "axios";
import type { AnomalyFeedResponse, DealListResponse, StatsResponse, SortBy, TrendingProductsResponse } from "@/types";

const api = axios.create({
  baseURL: "/api/v1",
  headers: { "Content-Type": "application/json" },
});

export interface DealsParams {
  page?: number;
  page_size?: number;
  category?: string;
  min_score?: number;
  min_roi?: number;
  source?: string;
  search?: string;
  sort_by?: SortBy;
}

export const dealsApi = {
  list: async (params: DealsParams = {}): Promise<DealListResponse> => {
    const { data } = await api.get<DealListResponse>("/deals", { params });
    return data;
  },

  stats: async (): Promise<StatsResponse> => {
    const { data } = await api.get<StatsResponse>("/deals/stats");
    return data;
  },

  triggerScrape: async (source = "hotukdeals"): Promise<{ task_id: string }> => {
    const { data } = await api.post("/deals/scrape", null, { params: { source } });
    return data;
  },
};

export const trendsApi = {
  trending: async (limit = 10): Promise<TrendingProductsResponse> => {
    const { data } = await api.get<TrendingProductsResponse>("/trends/trending", { params: { limit } });
    return data;
  },

  anomalies: async (severity?: string, limit = 10): Promise<AnomalyFeedResponse> => {
    const { data } = await api.get<AnomalyFeedResponse>("/trends/anomalies", {
      params: { ...(severity && { severity }), limit },
    });
    return data;
  },
};
