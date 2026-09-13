"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { api } from "@/lib/api";
import { fmtUsd, shortId } from "@/lib/format";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { ScoreBar } from "@/components/shared/score-bar";
import { KpiTile } from "@/components/shared/kpi-tile";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

export default function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const run = useQuery({ queryKey: ["evalRun", runId], queryFn: () => api.evalRun(runId) });

  if (run.isLoading) return <Skeleton className="h-96 w-full" />;
  if (run.isError || !run.data)
    return (
      <EmptyState title="Run not found" description="This evaluation run does not exist.">
        <Button asChild variant="outline" size="sm">
          <Link href="/evaluations">Back</Link>
        </Button>
      </EmptyState>
    );

  const r = run.data;
  const metricNames = Object.keys(r.metrics).sort();

  return (
    <>
      <Button
        asChild
        variant="ghost"
        size="sm"
        className="-ml-2 mb-3 h-7 text-xs text-muted-foreground"
      >
        <Link href="/evaluations">
          <ArrowLeft className="mr-1 h-3.5 w-3.5" /> Evaluations
        </Link>
      </Button>
      <PageHeader
        title={r.git_sha ?? shortId(r.id, 8)}
        description={`${r.app} · ${r.mode} · judge ${r.judge_model ?? r.judge_tier ?? "–"}`}
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
        {metricNames.map((m) => {
          const v = r.metrics[m] ?? 0;
          const good = m === "hallucination" ? 1 - v : v;
          return (
            <KpiTile
              key={m}
              label={m.replace(/_/g, " ")}
              value={v.toFixed(3)}
              tone={good >= 0.8 ? "good" : good >= 0.5 ? "warning" : "critical"}
            />
          );
        })}
        <KpiTile label="Items" value={r.n_items} hint={`${r.n_scores} scores`} />
        <KpiTile label="Cost" value={fmtUsd(r.cost_usd)} hint={`${r.errors} errors`} />
      </div>

      <div className="mt-4 overflow-hidden rounded-xl border border-border/80 bg-card shadow-xs">
        <div className="border-b px-4 py-2 text-sm font-medium">Per-example scores</div>
        <div className="scrollbar-thin overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs text-muted-foreground">
              <tr className="[&>th]:px-3 [&>th]:py-2 [&>th]:text-left [&>th]:font-normal">
                <th>Input</th>
                {metricNames.map((m) => (
                  <th key={m} className="!text-right">
                    {m.replace(/_/g, " ")}
                  </th>
                ))}
                <th />
              </tr>
            </thead>
            <tbody>
              {r.items.map((item, i) => (
                <tr key={i} className="border-t align-top hover:bg-accent/40">
                  <td className="max-w-[420px] px-3 py-2">
                    <div className="truncate text-xs">{item.input ?? item.output ?? "—"}</div>
                    {item.trace_id && (
                      <Link
                        href={`/traces/${item.trace_id}`}
                        className="font-mono text-[10px] text-muted-foreground hover:underline"
                      >
                        {shortId(item.trace_id, 12)}
                      </Link>
                    )}
                  </td>
                  {metricNames.map((m) => {
                    const sc = item.scores[m];
                    return (
                      <td key={m} className="px-3 py-2" title={sc?.rationale ?? ""}>
                        {sc && !sc.skipped && !sc.error ? (
                          <ScoreBar value={sc.value} higherIsBetter={m !== "hallucination"} />
                        ) : (
                          <span className="text-xs text-muted-foreground">
                            {sc?.error ? "err" : sc?.skipped ? "skip" : "–"}
                          </span>
                        )}
                      </td>
                    );
                  })}
                  <td className="px-3 py-2 text-right">
                    {item.trace_id && (
                      <Button asChild variant="ghost" size="sm" className="h-6 text-xs">
                        <Link href={`/traces/${item.trace_id}`}>open</Link>
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
