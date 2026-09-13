import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { Card } from "@/components/ui/card";
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
    <Card className={cn("px-4 py-3", className)}>
      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>{label}</span>
        {Icon && <Icon className="h-3.5 w-3.5 opacity-70" />}
      </div>
      {loading ? (
        <Skeleton className="mt-2 h-7 w-24" />
      ) : (
        <div
          className="mt-1 text-2xl font-semibold tracking-tight"
          style={toneVar ? { color: toneVar } : undefined}
        >
          {value}
        </div>
      )}
      {hint && <div className="mt-0.5 text-[13px] text-muted-foreground">{hint}</div>}
    </Card>
  );
}
