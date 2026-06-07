"use client";

import { TrendingUp, Zap, Minus, TrendingDown } from "lucide-react";
import { useTrending } from "@/hooks/useTrends";
import type { TrendingProduct } from "@/types";

const DIRECTION_CONFIG = {
  spiking: {
    label: "Spiking",
    icon: Zap,
    classes: "bg-red-100 text-red-700",
    bar: "bg-red-500",
  },
  rising: {
    label: "Rising",
    icon: TrendingUp,
    classes: "bg-green-100 text-green-700",
    bar: "bg-green-500",
  },
  stable: {
    label: "Stable",
    icon: Minus,
    classes: "bg-gray-100 text-gray-600",
    bar: "bg-gray-400",
  },
  falling: {
    label: "Falling",
    icon: TrendingDown,
    classes: "bg-blue-100 text-blue-700",
    bar: "bg-blue-400",
  },
};

function TrendCard({ product }: { product: TrendingProduct }) {
  const cfg = DIRECTION_CONFIG[product.trend_direction] ?? DIRECTION_CONFIG.stable;
  const Icon = cfg.icon;
  const title = product.product_title ?? product.asin;
  const score = Math.round(product.demand_score);
  const scoreColor =
    score >= 75 ? "text-green-600" : score >= 55 ? "text-yellow-600" : "text-red-500";

  return (
    <a
      href={`https://www.amazon.co.uk/s?k=${product.asin}`}
      target="_blank"
      rel="noopener noreferrer"
      className="flex-shrink-0 w-56 bg-white border border-gray-200 rounded-xl p-4 hover:border-green-400 hover:shadow-sm transition-all group"
    >
      <div className="flex items-start justify-between gap-2 mb-3">
        <span
          className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full ${cfg.classes}`}
        >
          <Icon className="w-3 h-3" />
          {cfg.label}
        </span>
        <span className={`text-xl font-bold tabular-nums ${scoreColor}`}>{score}</span>
      </div>

      <p className="text-xs font-medium text-gray-800 leading-tight line-clamp-2 mb-3 min-h-[2.5rem]">
        {title}
      </p>

      {/* demand score bar */}
      <div className="w-full bg-gray-100 rounded-full h-1.5 mb-2">
        <div
          className={`h-1.5 rounded-full ${cfg.bar} transition-all`}
          style={{ width: `${Math.min(100, score)}%` }}
        />
      </div>

      <div className="flex justify-between text-[10px] text-gray-400 mt-1">
        {product.ma_7d != null && <span>7d avg {Math.round(product.ma_7d)}</span>}
        {product.z_score != null && (
          <span className={Math.abs(product.z_score) >= 3 ? "text-red-400 font-semibold" : ""}>
            z {product.z_score > 0 ? "+" : ""}{product.z_score.toFixed(1)}σ
          </span>
        )}
      </div>
    </a>
  );
}

export function TrendingSection() {
  const { data, isLoading } = useTrending(12);

  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <TrendingUp className="w-4 h-4 text-green-600" />
        <h2 className="text-sm font-semibold text-gray-800">Trending Products</h2>
        {data && data.count > 0 && (
          <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">
            {data.count} rising
          </span>
        )}
      </div>

      {isLoading && (
        <div className="flex gap-3 overflow-hidden">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="flex-shrink-0 w-56 h-32 bg-gray-100 rounded-xl animate-pulse" />
          ))}
        </div>
      )}

      {!isLoading && (!data || data.count === 0) && (
        <div className="bg-white border border-dashed border-gray-200 rounded-xl p-5 text-center">
          <p className="text-sm text-gray-500 font-medium">No trending data yet</p>
          <p className="text-xs text-gray-400 mt-1">
            Trend signals are ingested nightly at 2am. Check back tomorrow.
          </p>
        </div>
      )}

      {!isLoading && data && data.count > 0 && (
        <div className="flex gap-3 overflow-x-auto pb-2 scrollbar-thin">
          {data.products.map((p) => (
            <TrendCard key={p.asin} product={p} />
          ))}
        </div>
      )}
    </div>
  );
}
