"use client";

import { AlertTriangle } from "lucide-react";
import { useAnomalies } from "@/hooks/useTrends";
import type { AnomalyItem } from "@/types";

const SEVERITY_CONFIG: Record<string, { classes: string; dot: string }> = {
  critical: { classes: "bg-red-100 text-red-700", dot: "bg-red-500" },
  high:     { classes: "bg-orange-100 text-orange-700", dot: "bg-orange-500" },
  medium:   { classes: "bg-yellow-100 text-yellow-700", dot: "bg-yellow-400" },
  low:      { classes: "bg-blue-100 text-blue-700", dot: "bg-blue-400" },
};

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const h = Math.floor(diff / 3_600_000);
  if (h < 1) return "< 1h ago";
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function humanSignal(signal: string): string {
  return signal.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function AnomalyRow({ anomaly }: { anomaly: AnomalyItem }) {
  const cfg = SEVERITY_CONFIG[anomaly.severity] ?? SEVERITY_CONFIG.low;
  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-gray-100 last:border-0">
      <span className={`mt-0.5 w-2 h-2 rounded-full flex-shrink-0 ${cfg.dot}`} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${cfg.classes}`}>
            {anomaly.severity}
          </span>
          <span className="text-xs font-medium text-gray-700">
            {humanSignal(anomaly.signal_type)}
          </span>
          <span className="text-[10px] text-gray-400 ml-auto">{timeAgo(anomaly.detected_at)}</span>
        </div>
        {anomaly.description && (
          <p className="text-[11px] text-gray-500 mt-0.5 line-clamp-1">{anomaly.description}</p>
        )}
        <p className="text-[10px] text-gray-400 mt-0.5 font-mono">{anomaly.asin}</p>
      </div>
    </div>
  );
}

export function AnomalyFeed() {
  const { data, isLoading } = useAnomalies(undefined, 8);

  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <AlertTriangle className="w-4 h-4 text-orange-500" />
        <h2 className="text-sm font-semibold text-gray-800">Anomaly Alerts</h2>
        {data && data.total > 0 && (
          <span className="text-xs bg-orange-100 text-orange-700 px-2 py-0.5 rounded-full">
            {data.total}
          </span>
        )}
      </div>

      <div className="bg-white border border-gray-200 rounded-xl px-4 py-1 min-h-[80px]">
        {isLoading && (
          <div className="space-y-3 py-3">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="h-8 bg-gray-100 rounded animate-pulse" />
            ))}
          </div>
        )}

        {!isLoading && (!data || data.total === 0) && (
          <div className="py-6 text-center">
            <p className="text-xs text-gray-400">No anomalies detected yet.</p>
            <p className="text-[10px] text-gray-300 mt-1">
              Checked hourly once trend data accumulates.
            </p>
          </div>
        )}

        {!isLoading && data && data.anomalies.length > 0 &&
          data.anomalies.map((a) => <AnomalyRow key={a.id} anomaly={a} />)
        }
      </div>
    </div>
  );
}
