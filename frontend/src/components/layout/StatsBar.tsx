"use client";

import { TrendingUp, Target, Zap, BarChart3 } from "lucide-react";
import { useStats } from "@/hooks/useDeals";
import { formatPercent, formatNumber } from "@/lib/utils";

export function StatsBar() {
  const { data: stats, isLoading } = useStats();

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="bg-white rounded-xl border border-gray-200 p-4 animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-3/4 mb-2" />
            <div className="h-8 bg-gray-200 rounded w-1/2" />
          </div>
        ))}
      </div>
    );
  }

  const cards = [
    {
      icon: <BarChart3 className="w-5 h-5 text-blue-500" />,
      label: "Deals Today",
      value: formatNumber(stats?.deals_today),
      sub: `${formatNumber(stats?.total_deals)} total`,
    },
    {
      icon: <Target className="w-5 h-5 text-green-500" />,
      label: "Analysed",
      value: formatNumber(stats?.scored_deals),
      sub: "fully scored",
    },
    {
      icon: <Zap className="w-5 h-5 text-orange-500" />,
      label: "High Confidence",
      value: formatNumber(stats?.high_confidence_opportunities),
      sub: "score ≥ 75",
    },
    {
      icon: <TrendingUp className="w-5 h-5 text-purple-500" />,
      label: "Avg ROI",
      value: formatPercent(stats?.avg_roi_percent, 1),
      sub: "across scored deals",
    },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {cards.map((card) => (
        <div
          key={card.label}
          className="bg-white rounded-xl border border-gray-200 p-4 flex items-start gap-3"
        >
          <div className="p-2 bg-gray-50 rounded-lg">{card.icon}</div>
          <div>
            <div className="text-xs text-gray-500 mb-0.5">{card.label}</div>
            <div className="text-xl font-bold text-gray-900">{card.value}</div>
            <div className="text-xs text-gray-400">{card.sub}</div>
          </div>
        </div>
      ))}
    </div>
  );
}
