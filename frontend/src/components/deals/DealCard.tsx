"use client";

import Image from "next/image";
import { ExternalLink, TrendingUp, Users, Star, ThumbsUp, MessageCircle } from "lucide-react";
import type { Deal } from "@/types";
import { ScoreRing } from "@/components/ui/score-ring";
import { Badge } from "@/components/ui/badge";
import {
  formatGBP,
  formatPercent,
  formatNumber,
  confidenceLabel,
  sourceLabel,
  categoryEmoji,
  cn,
} from "@/lib/utils";

interface DealCardProps {
  deal: Deal;
}

const SOURCE_COLORS: Record<string, string> = {
  hotukdeals: "bg-orange-500",
  smyths: "bg-purple-600",
  argos: "bg-red-600",
  currys: "bg-blue-600",
};

export function DealCard({ deal }: DealCardProps) {
  const opp = deal.opportunity;
  const amazon = deal.amazon_product;
  const score = opp?.score ?? null;

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm hover:shadow-md transition-shadow overflow-hidden">
      {/* Header */}
      <div className="flex items-start gap-3 p-4">
        {/* Product image */}
        <div className="relative w-16 h-16 flex-shrink-0 rounded-lg overflow-hidden bg-gray-100">
          {deal.image_url ? (
            <Image
              src={deal.image_url}
              alt={deal.title}
              fill
              className="object-contain p-1"
              unoptimized
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-2xl">
              {categoryEmoji(deal.category)}
            </div>
          )}
        </div>

        {/* Title + badges */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span
              className={cn(
                "text-xs font-medium text-white px-2 py-0.5 rounded-full",
                SOURCE_COLORS[deal.source] ?? "bg-gray-500"
              )}
            >
              {sourceLabel(deal.source)}
            </span>
            {deal.category && (
              <Badge variant="blue">
                {categoryEmoji(deal.category)} {deal.category.toUpperCase()}
              </Badge>
            )}
            {opp?.confidence_level && (
              <Badge
                variant={
                  opp.confidence_level === "very_high" || opp.confidence_level === "high"
                    ? "green"
                    : opp.confidence_level === "medium"
                    ? "yellow"
                    : "red"
                }
              >
                {confidenceLabel(opp.confidence_level)} confidence
              </Badge>
            )}
          </div>
          <h3 className="text-sm font-semibold text-gray-900 line-clamp-2 leading-snug">
            {deal.title}
          </h3>
        </div>

        {/* Score ring */}
        <div className="flex-shrink-0">
          <ScoreRing score={score} size={56} />
        </div>
      </div>

      {/* Price bar */}
      <div className="px-4 pb-3 flex items-center gap-3 flex-wrap">
        <div>
          <span className="text-xl font-bold text-gray-900">
            {formatGBP(deal.deal_price)}
          </span>
          {deal.original_price && (
            <span className="ml-2 text-sm text-gray-400 line-through">
              {formatGBP(deal.original_price)}
            </span>
          )}
        </div>
        {deal.discount_percent && (
          <Badge variant="red" className="text-xs font-bold">
            -{Math.round(deal.discount_percent)}% OFF
          </Badge>
        )}
        {deal.hot_score != null && (
          <span className="flex items-center gap-1 text-xs text-orange-600 font-medium">
            <ThumbsUp className="w-3 h-3" />
            {deal.hot_score}°
          </span>
        )}
        {deal.comment_count != null && (
          <span className="flex items-center gap-1 text-xs text-gray-500">
            <MessageCircle className="w-3 h-3" />
            {deal.comment_count}
          </span>
        )}
      </div>

      {/* Profitability metrics */}
      {opp && (
        <div className="mx-4 mb-3 grid grid-cols-3 gap-2 bg-gray-50 rounded-lg p-3">
          <div className="text-center">
            <div className="text-xs text-gray-500 mb-0.5">Net Profit</div>
            <div
              className={cn(
                "text-sm font-bold",
                (opp.net_profit ?? 0) > 0 ? "text-green-600" : "text-red-600"
              )}
            >
              {formatGBP(opp.net_profit)}
            </div>
          </div>
          <div className="text-center">
            <div className="text-xs text-gray-500 mb-0.5">ROI</div>
            <div
              className={cn(
                "text-sm font-bold",
                (opp.roi_percent ?? 0) >= 30
                  ? "text-green-600"
                  : (opp.roi_percent ?? 0) >= 15
                  ? "text-yellow-600"
                  : "text-red-600"
              )}
            >
              {formatPercent(opp.roi_percent)}
            </div>
          </div>
          <div className="text-center">
            <div className="text-xs text-gray-500 mb-0.5">Sell Price</div>
            <div className="text-sm font-bold text-gray-700">
              {formatGBP(opp.sell_price)}
            </div>
          </div>
        </div>
      )}

      {/* Amazon signals */}
      {amazon && (
        <div className="px-4 pb-3 flex items-center gap-4 text-xs text-gray-500 flex-wrap">
          {amazon.estimated_monthly_sales != null && (
            <span className="flex items-center gap-1">
              <TrendingUp className="w-3 h-3 text-green-500" />
              ~{formatNumber(amazon.estimated_monthly_sales)}/mo sales
            </span>
          )}
          {amazon.review_count != null && (
            <span className="flex items-center gap-1">
              <Star className="w-3 h-3 text-yellow-400 fill-yellow-400" />
              {formatNumber(amazon.review_count)} ({amazon.review_rating?.toFixed(1) ?? "?"})
            </span>
          )}
          {amazon.buy_box_seller_count != null && (
            <span className="flex items-center gap-1">
              <Users className="w-3 h-3" />
              {amazon.buy_box_seller_count} sellers
            </span>
          )}
          {amazon.is_amazon_selling && (
            <Badge variant="yellow">Amazon sells</Badge>
          )}
        </div>
      )}

      {/* Tags */}
      {opp?.tags && opp.tags.length > 0 && (
        <div className="px-4 pb-3 flex flex-wrap gap-1">
          {opp.tags.slice(0, 4).map((tag) => (
            <Badge key={tag} variant="default" className="text-xs">
              #{tag}
            </Badge>
          ))}
        </div>
      )}

      {/* Reasoning snippet */}
      {opp?.score_reasoning && (
        <div className="px-4 pb-3">
          <p className="text-xs text-gray-500 italic line-clamp-2">{opp.score_reasoning}</p>
        </div>
      )}

      {/* Footer actions */}
      <div className="border-t border-gray-100 px-4 py-3 flex items-center justify-between">
        <a
          href={deal.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 font-medium"
        >
          View Deal <ExternalLink className="w-3 h-3" />
        </a>
        {amazon?.amazon_url && (
          <a
            href={amazon.amazon_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-xs text-orange-600 hover:text-orange-800 font-medium"
          >
            Amazon <ExternalLink className="w-3 h-3" />
          </a>
        )}
      </div>
    </div>
  );
}
