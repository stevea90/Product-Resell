/**
 * Circular score indicator with colour gradient.
 * 80+ = green, 65-79 = lime, 50-64 = yellow, <50 = red
 */
interface ScoreRingProps {
  score: number | null;
  size?: number;
}

export function ScoreRing({ score, size = 60 }: ScoreRingProps) {
  if (score == null) {
    return (
      <div
        className="flex items-center justify-center rounded-full bg-gray-100 text-gray-400 text-sm font-bold"
        style={{ width: size, height: size }}
      >
        —
      </div>
    );
  }

  const radius = (size - 8) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = circumference * (1 - score / 100);

  const color =
    score >= 80 ? "#22c55e" : score >= 65 ? "#84cc16" : score >= 50 ? "#eab308" : "#ef4444";

  return (
    <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#e5e7eb"
          strokeWidth={4}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={4}
          strokeDasharray={circumference}
          strokeDashoffset={progress}
          strokeLinecap="round"
          style={{ transition: "stroke-dashoffset 0.5s ease" }}
        />
      </svg>
      <span
        className="absolute text-sm font-bold"
        style={{ color, fontSize: size < 50 ? "10px" : "14px" }}
      >
        {score}
      </span>
    </div>
  );
}
