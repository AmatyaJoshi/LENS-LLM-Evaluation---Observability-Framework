"use client";

import type { TooltipProps } from "recharts";
import { cn } from "@/lib/utils";

/** Shared Recharts styling: recessive grid/axes, ink-coloured text, card-styled tooltip. */
export const AXIS = {
  tick: { fill: "var(--viz-muted)", fontSize: 12.5 },
  axisLine: { stroke: "var(--viz-axis)" },
  tickLine: false as const,
};

export const GRID = { stroke: "var(--viz-grid)", strokeDasharray: "0", vertical: false };

export function ChartTooltip({
  active,
  payload,
  label,
  format,
}: TooltipProps<number, string> & { format?: (v: number, key: string) => string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-popover rounded-md border px-2.5 py-2 text-sm shadow-md">
      <div className="mb-1 text-muted-foreground">{label}</div>
      {payload.map((p) => (
        <div key={String(p.dataKey)} className="flex items-center gap-2">
          <span className="inline-block h-2 w-2 rounded-sm" style={{ background: p.color }} />
          <span className="text-muted-foreground">{p.name}</span>
          <span className="tabular ml-auto pl-4 font-medium">
            {format ? format(Number(p.value), String(p.dataKey)) : p.value}
          </span>
        </div>
      ))}
    </div>
  );
}

export function Legend({
  items,
  className,
}: {
  items: { label: string; color: string }[];
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-3 text-[13px] text-muted-foreground",
        className,
      )}
    >
      {items.map((i) => (
        <span key={i.label} className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2 w-2 rounded-sm" style={{ background: i.color }} />
          {i.label}
        </span>
      ))}
    </div>
  );
}

export function ChartCard({
  title,
  subtitle,
  legend,
  children,
  className,
  right,
}: {
  title: string;
  subtitle?: string;
  legend?: { label: string; color: string }[];
  children: React.ReactNode;
  className?: string;
  right?: React.ReactNode;
}) {
  return (
    <div className={cn("rounded-lg border bg-card", className)}>
      <div className="flex items-start justify-between gap-3 px-4 pt-3">
        <div>
          <div className="text-[15px] font-medium">{title}</div>
          {subtitle && <div className="text-[13px] text-muted-foreground">{subtitle}</div>}
        </div>
        <div className="flex items-center gap-3">
          {legend && legend.length > 1 && <Legend items={legend} />}
          {right}
        </div>
      </div>
      <div className="px-2 pb-2 pt-2">{children}</div>
    </div>
  );
}
