export interface Opportunity {
  score: number | null;
  confidence_level: string | null;
  buy_price: number | null;
  sell_price: number | null;
  net_profit: number | null;
  roi_percent: number | null;
  margin_percent: number | null;
  fba_fee: number | null;
  amazon_referral_fee: number | null;
  shipping_cost: number | null;
  estimated_payout: number | null;
  score_reasoning: string | null;
  tags: string[];
}

export interface AmazonProduct {
  asin: string | null;
  amazon_url: string | null;
  current_price: number | null;
  buy_box_price: number | null;
  sales_rank: number | null;
  estimated_monthly_sales: number | null;
  review_count: number | null;
  review_rating: number | null;
  buy_box_seller_count: number | null;
  is_amazon_selling: boolean;
  fba_seller_count: number | null;
}

export interface Deal {
  id: number;
  source: string;
  title: string;
  deal_price: number | null;
  original_price: number | null;
  discount_percent: number | null;
  currency: string;
  category: string | null;
  image_url: string | null;
  source_url: string;
  product_url: string | null;
  retailer: string | null;
  hot_score: number | null;
  comment_count: number | null;
  status: string;
  first_seen_at: string;
  opportunity: Opportunity | null;
  amazon_product: AmazonProduct | null;
}

export interface DealListResponse {
  items: Deal[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface StatsResponse {
  total_deals: number;
  scored_deals: number;
  high_confidence_opportunities: number;
  avg_roi_percent: number | null;
  top_categories: Record<string, number>;
  deals_today: number;
}

export type SortBy = "score" | "roi" | "profit" | "date" | "hot_score";
export type Category = "lego" | "gaming" | "toys" | "electronics" | "home" | "beauty" | "sports" | "fashion" | "garden" | "health" | "pets" | "books" | "other";

// ── Trend types ──────────────────────────────────────────────────────────────

export interface TrendingProduct {
  asin: string;
  product_title: string | null;
  date: string;
  demand_score: number;
  trend_direction: "rising" | "spiking" | "stable" | "falling";
  ma_7d: number | null;
  ma_30d: number | null;
  z_score: number | null;
}

export interface TrendingProductsResponse {
  count: number;
  products: TrendingProduct[];
}

export interface AnomalyItem {
  id: number;
  asin: string;
  product_title: string | null;
  detected_at: string;
  signal_type: string;
  z_score: number;
  severity: "low" | "medium" | "high" | "critical";
  description: string | null;
  current_value: number | null;
  baseline_value: number | null;
  is_acknowledged: boolean;
}

export interface AnomalyFeedResponse {
  total: number;
  anomalies: AnomalyItem[];
}
