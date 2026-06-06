import axios from "axios";
import type { DealListResponse, StatsResponse, SortBy } from "@/types";

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
