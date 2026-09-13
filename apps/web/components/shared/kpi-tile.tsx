import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";

export function KpiTile({
  label,
  value,
  hint,
  icon: Icon,
  loading,
  tone,
  className,
}: {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  icon?: LucideIcon;
  loading?: boolean;
  tone?: "good" | "warning" | "critical";
  className?: string;
}) {
  const toneVar =
    tone === "good"
      ? "var(--status-good-text)"
      : tone === "warning"
        ? "var(--status-warning)"
        : tone === "critical"
          ? "var(--status-critical)"
          : undefined;
  return (
    <div
      className={cn(
        "group rounded-xl border border-border/80 bg-card px-4 py-3.5 shadow-xs transition-shadow hover:shadow-card",
        className,
      )}
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
        {Icon && (
          <span className="flex h-6 w-6 items-center justify-center rounded-md bg-muted/70 text-muted-foreground transition-colors group-hover:bg-accent-tint group-hover:text-primary">
            <Icon className="h-3.5 w-3.5" />
          </span>
        )}
      </div>
      {loading ? (
        <Skeleton className="mt-2.5 h-7 w-24" />
      ) : (
        <div
          className="tabular mt-1.5 text-2xl font-semibold tracking-tight"
          style={toneVar ? { color: toneVar } : undefined}
        >
          {value}
        </div>
      )}
      {hint && <div className="mt-1 text-[11px] text-muted-foreground">{hint}</div>}
    </div>
  );
}
