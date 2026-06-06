import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatGBP(value: number | null | undefined): string {
  if (value == null) return "—";
  return new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: "GBP",
    minimumFractionDigits: 2,
  }).format(value);
}

export function formatPercent(value: number | null | undefined, decimals = 1): string {
  if (value == null) return "—";
  return `${value.toFixed(decimals)}%`;
}

export function formatNumber(value: number | null | undefined): string {
  if (value == null) return "—";
  return new Intl.NumberFormat("en-GB").format(value);
}

export function scoreToColor(score: number | null): string {
  if (score == null) return "bg-gray-200 text-gray-600";
  if (score >= 80) return "bg-green-500 text-white";
  if (score >= 65) return "bg-green-400 text-white";
  if (score >= 50) return "bg-yellow-400 text-gray-900";
  return "bg-red-400 text-white";
}

export function confidenceLabel(level: string | null): string {
  const map: Record<string, string> = {
    very_high: "Very High",
    high: "High",
    medium: "Medium",
    low: "Low",
  };
  return level ? (map[level] ?? level) : "—";
}

export function sourceLabel(source: string): string {
  const map: Record<string, string> = {
    hotukdeals: "HotUKDeals",
    smyths: "Smyths",
    argos: "Argos",
    currys: "Currys",
    manual: "Manual",
  };
  return map[source] ?? source;
}

export function categoryEmoji(category: string | null): string {
  const map: Record<string, string> = {
    lego: "🧱",
    gaming: "🎮",
    toys: "🧸",
    electronics: "💻",
    other: "📦",
  };
  return category ? (map[category] ?? "📦") : "📦";
}
