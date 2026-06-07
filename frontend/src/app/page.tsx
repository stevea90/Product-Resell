"use client";

import { useState } from "react";
import { Zap } from "lucide-react";
import { useDeals } from "@/hooks/useDeals";
import { DealCard } from "@/components/deals/DealCard";
import { DealFilters } from "@/components/deals/DealFilters";
import { StatsBar } from "@/components/layout/StatsBar";
import { TrendingSection } from "@/components/trends/TrendingSection";
import { AnomalyFeed } from "@/components/trends/AnomalyFeed";
import type { SortBy } from "@/types";

const DEFAULT_FILTERS = {
  search: "",
  category: "",
  min_score: "",
  min_roi: "",
  sort_by: "score" as SortBy,
};

export default function Dashboard() {
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [page, setPage] = useState(1);

  const queryParams = {
    page,
    page_size: 20,
    sort_by: filters.sort_by,
    ...(filters.search && { search: filters.search }),
    ...(filters.category && { category: filters.category }),
    ...(filters.min_score && { min_score: parseInt(filters.min_score) }),
    ...(filters.min_roi && { min_roi: parseFloat(filters.min_roi) }),
  };

  const { data, isLoading, isError, refetch } = useDeals(queryParams);

  const handleFiltersChange = (newFilters: typeof filters) => {
    setFilters(newFilters);
    setPage(1);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Top nav */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-green-500 rounded-lg flex items-center justify-center">
              <Zap className="w-5 h-5 text-white" />
            </div>
            <span className="text-lg font-bold text-gray-900">ArbitrageAI</span>
            <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-medium ml-1">
              BETA
            </span>
          </div>
          <div className="text-xs text-gray-500">
            Auto-refreshes every 60s
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-6 space-y-6">
        {/* Stats */}
        <StatsBar />

        {/* Market Intelligence */}
        <section className="bg-gray-50 rounded-2xl border border-gray-200 p-4 space-y-5">
          <div className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
            Market Intelligence
          </div>
          <TrendingSection />
          <AnomalyFeed />
        </section>

        {/* Filters */}
        <DealFilters filters={filters} onChange={handleFiltersChange} />

        {/* Results header */}
        <div className="flex items-center justify-between">
          <div className="text-sm text-gray-600">
            {isLoading ? (
              "Loading..."
            ) : data ? (
              <span>
                Showing <strong>{data.items.length}</strong> of{" "}
                <strong>{data.total}</strong> opportunities
              </span>
            ) : null}
          </div>
        </div>

        {/* Deal grid */}
        {isLoading && (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {[...Array(6)].map((_, i) => (
              <div
                key={i}
                className="bg-white rounded-xl border border-gray-200 h-64 animate-pulse"
              />
            ))}
          </div>
        )}

        {isError && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-center">
            <p className="text-red-600 font-medium">Failed to load deals</p>
            <p className="text-red-400 text-sm mt-1">
              Is the backend running? Check{" "}
              <code className="bg-red-100 px-1 rounded">http://localhost:8000/health</code>
            </p>
            <button
              onClick={() => refetch()}
              className="mt-3 px-4 py-2 bg-red-500 text-white rounded-lg text-sm hover:bg-red-600"
            >
              Retry
            </button>
          </div>
        )}

        {!isLoading && !isError && data?.items.length === 0 && (
          <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
            <div className="text-5xl mb-4">🔍</div>
            <p className="text-gray-600 font-medium">No opportunities found</p>
            <p className="text-gray-400 text-sm mt-1">
              Try adjusting your filters, or trigger a scrape to fetch new deals.
            </p>
          </div>
        )}

        {!isLoading && data && data.items.length > 0 && (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {data.items.map((deal) => (
                <DealCard key={deal.id} deal={deal} />
              ))}
            </div>

            {/* Pagination */}
            {data.pages > 1 && (
              <div className="flex items-center justify-center gap-2 py-4">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="px-4 py-2 rounded-lg border border-gray-300 text-sm disabled:opacity-40 hover:bg-gray-50"
                >
                  Previous
                </button>
                <span className="text-sm text-gray-600">
                  Page {page} of {data.pages}
                </span>
                <button
                  onClick={() => setPage((p) => Math.min(data.pages, p + 1))}
                  disabled={page === data.pages}
                  className="px-4 py-2 rounded-lg border border-gray-300 text-sm disabled:opacity-40 hover:bg-gray-50"
                >
                  Next
                </button>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
