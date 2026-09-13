"use client";

import { useMemo } from "react";
import type { Span } from "@/lib/api";
import { fmtMs } from "@/lib/format";
import { KIND_VAR, kindOf } from "@/lib/kinds";
import { cn } from "@/lib/utils";
import { KindDot } from "@/components/shared/badges";

export interface WaterfallRow {
  span: Span;
  depth: number;
  left: number; // 0..1
  width: number; // 0..1
}

export function buildRows(spans: Span[]): { rows: WaterfallRow[]; t0: number; total: number } {
  if (spans.length === 0) return { rows: [], t0: 0, total: 1 };
  const byId = new Map(spans.map((s) => [s.span_id, s]));
  const children = new Map<string | null, Span[]>();
  for (const s of spans) {
    const parent = s.parent_span_id && byId.has(s.parent_span_id) ? s.parent_span_id : null;
    children.set(parent, [...(children.get(parent) ?? []), s]);
  }
  for (const list of children.values())
    list.sort((a, b) => a.start_ns - b.start_ns || a.span_id.localeCompare(b.span_id));
  const t0 = Math.min(...spans.map((s) => s.start_ns));
  const t1 = Math.max(...spans.map((s) => s.end_ns));
  const total = Math.max(1, t1 - t0);
  const rows: WaterfallRow[] = [];
  const walk = (parent: string | null, depth: number) => {
    for (const s of children.get(parent) ?? []) {
      rows.push({
        span: s,
        depth,
        left: (s.start_ns - t0) / total,
        width: Math.max(0.002, (s.end_ns - s.start_ns) / total),
      });
      walk(s.span_id, depth + 1);
    }
  };
  walk(null, 0);
  return { rows, t0, total };
}

export function Waterfall({
  spans,
  selected,
  onSelect,
}: {
  spans: Span[];
  selected: string | null;
  onSelect: (spanId: string) => void;
}) {
  const { rows, total } = useMemo(() => buildRows(spans), [spans]);
  const ticks = 5;
  return (
    <div className="scrollbar-thin overflow-x-auto">
      <div className="min-w-[720px]">
        <div className="grid grid-cols-[320px_1fr_90px] items-center border-b px-3 py-1.5 text-[12px] uppercase tracking-wider text-muted-foreground">
          <span>Span</span>
          <div className="relative h-4">
            {Array.from({ length: ticks + 1 }).map((_, i) => (
              <span
                key={i}
                className="tabular absolute -translate-x-1/2 normal-case tracking-normal"
                style={{ left: `${(i / ticks) * 100}%` }}
              >
                {fmtMs((total / 1e6) * (i / ticks))}
              </span>
            ))}
          </div>
          <span className="text-right">Duration</span>
        </div>
        <ul>
          {rows.map(({ span, depth, left, width }) => {
            const active = selected === span.span_id;
            return (
              <li key={span.span_id}>
                <button
                  type="button"
                  onClick={() => onSelect(span.span_id)}
                  className={cn(
                    "grid w-full grid-cols-[320px_1fr_90px] items-center px-3 py-1 text-left text-sm transition-colors hover:bg-accent/50",
                    active && "bg-accent",
                  )}
                >
                  <span
                    className="flex min-w-0 items-center gap-2"
                    style={{ paddingLeft: depth * 14 }}
                  >
                    <KindDot kind={span.kind} />
                    <span className="truncate">{span.name}</span>
                    {span.status === "error" && (
                      <span className="bg-[color:var(--status-critical)]/15 rounded px-1 text-[12px] text-[color:var(--status-critical)]">
                        error
                      </span>
                    )}
                  </span>
                  <span className="relative block h-4">
                    {Array.from({ length: ticks + 1 }).map((_, i) => (
                      <span
                        key={i}
                        className="absolute top-0 h-full border-l border-dashed border-[color:var(--viz-grid)]"
                        style={{ left: `${(i / ticks) * 100}%` }}
                      />
                    ))}
                    <span
                      className="absolute top-0.5 h-3 rounded-[3px]"
                      style={{
                        left: `${left * 100}%`,
                        width: `${width * 100}%`,
                        background: KIND_VAR[kindOf(span.kind)],
                        opacity: span.status === "error" ? 0.55 : 0.9,
                        outline:
                          span.status === "error"
                            ? "1.5px solid var(--status-critical)"
                            : undefined,
                      }}
                    />
                  </span>
                  <span className="tabular text-right text-muted-foreground">
                    {fmtMs((span.end_ns - span.start_ns) / 1e6)}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
