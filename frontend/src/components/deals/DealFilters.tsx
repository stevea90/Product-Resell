"use client";

import { Search, SlidersHorizontal, RefreshCw } from "lucide-react";
import type { SortBy } from "@/types";
import { cn } from "@/lib/utils";
import { dealsApi } from "@/lib/api";
import { useState } from "react";

interface FiltersState {
  search: string;
  category: string;
  min_score: string;
  min_roi: string;
  sort_by: SortBy;
}

interface DealFiltersProps {
  filters: FiltersState;
  onChange: (filters: FiltersState) => void;
}

const CATEGORIES = [
  { value: "", label: "All Categories" },
  { value: "lego", label: "🧱 LEGO" },
  { value: "gaming", label: "🎮 Gaming" },
  { value: "toys", label: "🧸 Toys" },
  { value: "electronics", label: "💻 Electronics" },
];

const SORT_OPTIONS: { value: SortBy; label: string }[] = [
  { value: "score", label: "Score (Best)" },
  { value: "roi", label: "ROI %" },
  { value: "profit", label: "Net Profit" },
  { value: "date", label: "Newest" },
  { value: "hot_score", label: "Hot Score" },
];

export function DealFilters({ filters, onChange }: DealFiltersProps) {
  const [scraping, setScraping] = useState(false);

  const handleScrape = async () => {
    setScraping(true);
    try {
      await dealsApi.triggerScrape("hotukdeals");
    } finally {
      setTimeout(() => setScraping(false), 3000);
    }
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 flex flex-col gap-3">
      <div className="flex items-center gap-2 flex-wrap">
        {/* Search */}
        <div className="relative flex-1 min-w-48">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search deals..."
            value={filters.search}
            onChange={(e) => onChange({ ...filters, search: e.target.value })}
            className="w-full pl-9 pr-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
          />
        </div>

        {/* Category */}
        <select
          value={filters.category}
          onChange={(e) => onChange({ ...filters, category: e.target.value })}
          className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
        >
          {CATEGORIES.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>

        {/* Sort */}
        <select
          value={filters.sort_by}
          onChange={(e) => onChange({ ...filters, sort_by: e.target.value as SortBy })}
          className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
        >
          {SORT_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>

        {/* Min score */}
        <div className="flex items-center gap-1">
          <SlidersHorizontal className="w-4 h-4 text-gray-400" />
          <label className="text-sm text-gray-600">Min score</label>
          <input
            type="number"
            min={0}
            max={100}
            value={filters.min_score}
            onChange={(e) => onChange({ ...filters, min_score: e.target.value })}
            className="w-16 px-2 py-2 border border-gray-300 rounded-lg text-sm text-center focus:outline-none focus:ring-2 focus:ring-green-500"
            placeholder="0"
          />
        </div>

        {/* Min ROI */}
        <div className="flex items-center gap-1">
          <label className="text-sm text-gray-600">Min ROI%</label>
          <input
            type="number"
            min={0}
            value={filters.min_roi}
            onChange={(e) => onChange({ ...filters, min_roi: e.target.value })}
            className="w-16 px-2 py-2 border border-gray-300 rounded-lg text-sm text-center focus:outline-none focus:ring-2 focus:ring-green-500"
            placeholder="0"
          />
        </div>

        {/* Scrape trigger */}
        <button
          onClick={handleScrape}
          disabled={scraping}
          className={cn(
            "flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
            scraping
              ? "bg-gray-100 text-gray-400 cursor-not-allowed"
              : "bg-green-500 hover:bg-green-600 text-white"
          )}
        >
          <RefreshCw className={cn("w-4 h-4", scraping && "animate-spin")} />
          {scraping ? "Queued..." : "Scrape Now"}
        </button>
      </div>
    </div>
  );
}
