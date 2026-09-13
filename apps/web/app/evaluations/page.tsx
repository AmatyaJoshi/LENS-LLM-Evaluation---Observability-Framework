"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { FlaskConical } from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "@/lib/api";
import { fmtAgo, fmtUsd, shortId } from "@/lib/format";
import { useAppFilter } from "@/components/shell/topbar";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { ScoreBar } from "@/components/shared/score-bar";
import { AXIS, ChartCard, ChartTooltip, GRID } from "@/components/charts/chart-kit";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

export default function EvaluationsPage() {
  const [app] = useAppFilter();
  const runs = useQuery({ queryKey: ["evalRuns", app], queryFn: () => api.evalRuns({ app }) });
  const metrics = useQuery({ queryKey: ["metrics"], queryFn: api.metrics });
  const [trendMetric, setTrendMetric] = useState("faithfulness");
  const trend = useQuery({
    queryKey: ["evalTrends", trendMetric, app],
    queryFn: () => api.evalTrends({ metric: trendMetric, app }),
  });

  const allMetrics = Array.from(
    new Set((runs.data ?? []).flatMap((r) => Object.keys(r.metrics))),
  ).sort();
  const trendData = (trend.data ?? []).map((p) => ({
    t: p.git_sha ?? shortId(p.run_id, 6),
    value: p.mean,
  }));

  return (
    <>
      <PageHeader
        title="Evaluations"
        description="Offline and online scoring runs with versioned, calibrated judges"
      />
      {runs.isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : runs.data && runs.data.length === 0 ? (
        <EmptyState
          icon={FlaskConical}
          title="No evaluation runs yet"
          description="Run `lens eval --dataset golden --app rag_demo` or enable online sampling (LENS_EVAL_DISPATCH) to score live traces."
        />
      ) : (
        <div className="space-y-4">
          <ChartCard
            title="Metric trend"
            subtitle="Mean score across runs, oldest to newest"
            right={
              <Select value={trendMetric} onValueChange={setTrendMetric}>
                <SelectTrigger className="h-7 w-[180px] text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(metrics.data ?? []).map((m) => (
                    <SelectItem key={m.name} value={m.name}>
                      {m.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            }
          >
            {trendData.length === 0 ? (
              <div className="flex h-[200px] items-center justify-center text-xs text-muted-foreground">
                No finished runs with {trendMetric}
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={trendData} margin={{ top: 8, right: 12, left: -4, bottom: 0 }}>
                  <CartesianGrid {...GRID} />
                  <XAxis dataKey="t" {...AXIS} minTickGap={20} />
                  <YAxis {...AXIS} domain={[0, 1]} width={40} />
                  <Tooltip content={<ChartTooltip format={(v) => v.toFixed(3)} />} />
                  <Line
                    type="monotone"
                    dataKey="value"
                    name={trendMetric}
                    stroke="var(--series-1)"
                    strokeWidth={2}
                    dot={{ r: 3, fill: "var(--series-1)", strokeWidth: 0 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            )}
          </ChartCard>

          <div className="overflow-hidden rounded-lg border bg-card">
            <div className="border-b px-4 py-2 text-sm font-medium">Runs</div>
            <div className="scrollbar-thin overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-xs text-muted-foreground">
                  <tr className="[&>th]:px-3 [&>th]:py-2 [&>th]:text-left [&>th]:font-normal">
                    <th>Run</th>
                    <th>App</th>
                    <th>Mode</th>
                    <th>Judge</th>
                    {allMetrics.map((m) => (
                      <th key={m} className="!text-right">
                        {m.replace(/_/g, " ")}
                      </th>
                    ))}
                    <th className="!text-right">Items</th>
                    <th className="!text-right">Cost</th>
                    <th className="!text-right">When</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.data?.map((r) => (
                    <tr key={r.id} className="border-t hover:bg-accent/40">
                      <td className="px-3 py-2">
                        <Link
                          href={`/evaluations/${r.id}`}
                          className="font-mono text-xs hover:underline"
                        >
                          {r.git_sha ?? shortId(r.id, 8)}
                        </Link>
                      </td>
                      <td className="px-3 py-2 text-xs">{r.app}</td>
                      <td className="px-3 py-2 text-xs text-muted-foreground">{r.mode}</td>
                      <td className="px-3 py-2 font-mono text-[11px] text-muted-foreground">
                        {r.judge_model ?? r.judge_tier ?? "–"}
                      </td>
                      {allMetrics.map((m) => (
                        <td key={m} className="px-3 py-2">
                          {m in r.metrics ? (
                            <ScoreBar value={r.metrics[m]} higherIsBetter={m !== "hallucination"} />
                          ) : (
                            <span className="text-xs text-muted-foreground">–</span>
                          )}
                        </td>
                      ))}
                      <td className="tabular px-3 py-2 text-right text-xs">{r.n_items}</td>
                      <td className="tabular px-3 py-2 text-right text-xs">{fmtUsd(r.cost_usd)}</td>
                      <td className="px-3 py-2 text-right text-xs text-muted-foreground">
                        {fmtAgo(Date.parse(r.started_at) * 1e6)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
