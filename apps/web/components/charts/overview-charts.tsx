"use client";

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { OverviewStats, Window } from "@/lib/api";
import { fmtCompact, fmtInt, fmtMs, fmtTime, nsToDate } from "@/lib/format";
import { KIND_LABEL, KIND_ORDER, KIND_VAR, kindOf } from "@/lib/kinds";
import { AXIS, ChartCard, ChartTooltip, GRID } from "@/components/charts/chart-kit";
import { EmptyState } from "@/components/shared/empty-state";

function labelFor(tNs: number, window: Window): string {
  const d = nsToDate(tNs);
  if (window === "7d" || window === "30d" || window === "all") {
    return d.toLocaleDateString(undefined, { month: "short", day: "2-digit" });
  }
  return fmtTime(tNs).slice(0, 5);
}

function useSeries(stats: OverviewStats | undefined, window: Window) {
  return (stats?.series ?? []).map((p) => ({
    t: labelFor(p.t_ns, window),
    ok: p.traces - p.errors,
    error: p.errors,
    tokens: p.tokens,
    p95: p.p95_ms,
  }));
}

const NoData = () => (
  <div className="flex h-[200px] items-center justify-center text-sm text-muted-foreground">
    No traces in this window
  </div>
);

export function TrafficChart({ stats, window }: { stats?: OverviewStats; window: Window }) {
  const data = useSeries(stats, window);
  return (
    <ChartCard
      title="Traces"
      subtitle="Completed runs per interval"
      legend={[
        { label: "ok", color: "var(--series-1)" },
        { label: "error", color: "var(--status-critical)" },
      ]}
    >
      {data.length === 0 ? (
        <NoData />
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <BarChart
            data={data}
            margin={{ top: 8, right: 8, left: -12, bottom: 0 }}
            barCategoryGap="20%"
          >
            <CartesianGrid {...GRID} />
            <XAxis dataKey="t" {...AXIS} minTickGap={24} />
            <YAxis {...AXIS} allowDecimals={false} width={44} />
            <Tooltip
              content={<ChartTooltip format={(v) => fmtInt(v)} />}
              cursor={{ fill: "var(--viz-grid)" }}
            />
            <Bar
              dataKey="ok"
              name="ok"
              stackId="a"
              fill="var(--series-1)"
              stroke="var(--viz-surface)"
              strokeWidth={1}
            />
            <Bar
              dataKey="error"
              name="error"
              stackId="a"
              fill="var(--status-critical)"
              stroke="var(--viz-surface)"
              strokeWidth={1}
              radius={[3, 3, 0, 0]}
            />
          </BarChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  );
}

export function LatencyChart({ stats, window }: { stats?: OverviewStats; window: Window }) {
  const data = useSeries(stats, window);
  return (
    <ChartCard title="Latency p95" subtitle="End-to-end trace duration">
      {data.length === 0 ? (
        <NoData />
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={data} margin={{ top: 8, right: 8, left: -4, bottom: 0 }}>
            <CartesianGrid {...GRID} />
            <XAxis dataKey="t" {...AXIS} minTickGap={24} />
            <YAxis {...AXIS} width={56} tickFormatter={(v: number) => fmtMs(v)} />
            <Tooltip
              content={<ChartTooltip format={(v) => fmtMs(v)} />}
              cursor={{ stroke: "var(--viz-axis)" }}
            />
            <Line
              type="monotone"
              dataKey="p95"
              name="p95"
              stroke="var(--series-1)"
              strokeWidth={2}
              dot={{ r: 3, strokeWidth: 0, fill: "var(--series-1)" }}
              activeDot={{ r: 5, stroke: "var(--viz-surface)", strokeWidth: 2 }}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  );
}

export function TokensChart({ stats, window }: { stats?: OverviewStats; window: Window }) {
  const data = useSeries(stats, window);
  return (
    <ChartCard title="Tokens" subtitle="Prompt + completion tokens per interval">
      {data.length === 0 ? (
        <NoData />
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={data} margin={{ top: 8, right: 8, left: -4, bottom: 0 }}>
            <defs>
              <linearGradient id="tokensFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--series-2)" stopOpacity={0.35} />
                <stop offset="100%" stopColor="var(--series-2)" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid {...GRID} />
            <XAxis dataKey="t" {...AXIS} minTickGap={24} />
            <YAxis {...AXIS} width={48} tickFormatter={(v: number) => fmtCompact(v)} />
            <Tooltip
              content={<ChartTooltip format={(v) => fmtInt(v)} />}
              cursor={{ stroke: "var(--viz-axis)" }}
            />
            <Area
              type="monotone"
              dataKey="tokens"
              name="tokens"
              stroke="var(--series-2)"
              strokeWidth={2}
              fill="url(#tokensFill)"
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  );
}

export function KindBreakdown({ stats }: { stats?: OverviewStats }) {
  const total = Object.values(stats?.by_kind ?? {}).reduce((a, b) => a + b, 0);
  const rows = KIND_ORDER.map((k) => ({ kind: k, n: stats?.by_kind?.[k] ?? 0 })).filter(
    (r) => r.n > 0,
  );
  return (
    <ChartCard title="Span mix" subtitle={`${fmtInt(total)} spans by kind`}>
      {rows.length === 0 ? (
        <NoData />
      ) : (
        <div className="space-y-2 px-2 pb-2 pt-1">
          {rows.map((r) => (
            <div key={r.kind} className="grid grid-cols-[96px_1fr_56px] items-center gap-2 text-sm">
              <span className="flex items-center gap-1.5 text-muted-foreground">
                <span
                  className="h-2 w-2 rounded-sm"
                  style={{ background: KIND_VAR[kindOf(r.kind)] }}
                />
                {KIND_LABEL[kindOf(r.kind)]}
              </span>
              <div className="h-2 overflow-hidden rounded-sm bg-muted">
                <div
                  className="h-full rounded-sm"
                  style={{ width: `${(r.n / total) * 100}%`, background: KIND_VAR[kindOf(r.kind)] }}
                />
              </div>
              <span className="tabular text-right">{fmtInt(r.n)}</span>
            </div>
          ))}
        </div>
      )}
    </ChartCard>
  );
}

export function ModelTable({ stats }: { stats?: OverviewStats }) {
  const rows = stats?.by_model ?? [];
  const max = Math.max(1, ...rows.map((r) => r.tokens_in + r.tokens_out));
  return (
    <ChartCard title="Models" subtitle="LLM calls and tokens by model">
      {rows.length === 0 ? (
        <EmptyState title="No LLM calls yet" className="border-0 py-10" />
      ) : (
        <table className="w-full text-sm">
          <thead className="text-muted-foreground">
            <tr className="[&>th]:px-2 [&>th]:pb-1.5 [&>th]:text-left [&>th]:font-normal">
              <th>Model</th>
              <th>Provider</th>
              <th className="!text-right">Calls</th>
              <th className="!text-right">Tokens</th>
              <th className="w-[30%]" />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={`${r.provider}/${r.model}`} className="border-t [&>td]:px-2 [&>td]:py-1.5">
                <td className="font-mono">{r.model}</td>
                <td className="text-muted-foreground">{r.provider}</td>
                <td className="tabular text-right">{fmtInt(r.calls)}</td>
                <td className="tabular text-right">{fmtCompact(r.tokens_in + r.tokens_out)}</td>
                <td>
                  <div className="h-1.5 rounded-sm bg-muted">
                    <div
                      className="h-full rounded-sm"
                      style={{
                        width: `${((r.tokens_in + r.tokens_out) / max) * 100}%`,
                        background: "var(--seq-400)",
                      }}
                    />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </ChartCard>
  );
}
