import { cn } from "@/lib/utils";

/** A 0-1 score rendered as a labelled meter. Higher-is-better metrics go green→red;
 * lower-is-better (hallucination) invert the color. */
export function ScoreBar({
  value,
  higherIsBetter = true,
  className,
}: {
  value: number | null | undefined;
  higherIsBetter?: boolean;
  className?: string;
}) {
  if (value == null) return <span className="text-xs text-muted-foreground">–</span>;
  const good = higherIsBetter ? value : 1 - value;
  const color =
    good >= 0.8
      ? "var(--status-good)"
      : good >= 0.6
        ? "var(--seq-400)"
        : good >= 0.4
          ? "var(--status-warning)"
          : "var(--status-critical)";
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="h-1.5 w-16 overflow-hidden rounded-sm bg-muted">
        <div
          className="h-full rounded-sm"
          style={{ width: `${value * 100}%`, background: color }}
        />
      </div>
      <span className="tabular w-9 text-right text-xs font-medium">{value.toFixed(2)}</span>
    </div>
  );
}
