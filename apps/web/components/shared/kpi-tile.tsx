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
        "group flex min-h-[108px] flex-col justify-between rounded-2xl border border-border/70 bg-card p-4 shadow-xs transition-shadow hover:shadow-card",
        className,
      )}
    >
      <div className="flex items-center justify-between">
        <span className="truncate text-[13px] font-medium text-muted-foreground">{label}</span>
        {Icon && (
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-muted/70 text-muted-foreground transition-colors group-hover:bg-accent-tint group-hover:text-primary">
            <Icon className="h-[15px] w-[15px]" />
          </span>
        )}
      </div>
      <div className="mt-2">
        {loading ? (
          <Skeleton className="h-8 w-24" />
        ) : (
          <div
            className="tabular text-[28px] font-semibold leading-none tracking-tight"
            style={toneVar ? { color: toneVar } : undefined}
          >
            {value}
          </div>
        )}
        {hint && <div className="mt-1.5 truncate text-[11px] text-muted-foreground">{hint}</div>}
      </div>
    </div>
  );
}
