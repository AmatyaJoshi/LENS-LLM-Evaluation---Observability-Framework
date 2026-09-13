"use client";

import { useQuery } from "@tanstack/react-query";
import { Scale } from "lucide-react";
import { api, type AgreementReport } from "@/lib/api";
import { fmtUsd } from "@/lib/format";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

function kappaColor(k: number): string {
  // Landis & Koch bands
  if (k >= 0.8) return "var(--status-good)";
  if (k >= 0.6) return "var(--seq-400)";
  if (k >= 0.4) return "var(--status-warning)";
  return "var(--status-critical)";
}

function AgreementTable({ title, rows }: { title: string; rows: AgreementReport[] }) {
  if (rows.length === 0)
    return (
      <div className="rounded-xl border border-border/80 bg-card p-4 shadow-xs">
        <div className="text-sm font-medium">{title}</div>
        <p className="mt-1 text-xs text-muted-foreground">
          Needs human labels and judge scores on the same items. Label from the Labelling page.
        </p>
      </div>
    );
  return (
    <div className="overflow-hidden rounded-xl border border-border/80 bg-card shadow-xs">
      <div className="border-b px-4 py-2 text-sm font-medium">{title}</div>
      <table className="w-full text-sm">
        <thead className="text-xs text-muted-foreground">
          <tr className="[&>th]:px-3 [&>th]:py-2 [&>th]:text-left [&>th]:font-normal">
            <th>Metric</th>
            <th>Judge</th>
            <th>vs</th>
            <th className="!text-right">n</th>
            <th className="!text-right">Cohen κ</th>
            <th className="!text-right">Kripp. α</th>
            <th className="!text-right">Spearman ρ</th>
            <th className="!text-right">MAE</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t">
              <td className="px-3 py-2 text-xs">{r.metric.replace(/_/g, " ")}</td>
              <td className="px-3 py-2 font-mono text-[11px]">{r.judge}</td>
              <td className="px-3 py-2 text-xs text-muted-foreground">{r.reference}</td>
              <td className="tabular px-3 py-2 text-right text-xs">{r.n}</td>
              <td
                className="tabular px-3 py-2 text-right text-xs font-medium"
                style={{ color: kappaColor(r.cohen_kappa) }}
              >
                {r.cohen_kappa.toFixed(3)}
              </td>
              <td className="tabular px-3 py-2 text-right text-xs">
                {r.krippendorff_alpha.toFixed(3)}
              </td>
              <td className="tabular px-3 py-2 text-right text-xs">{r.spearman_rho.toFixed(3)}</td>
              <td className="tabular px-3 py-2 text-right text-xs">
                {r.mean_abs_error.toFixed(3)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function JudgesPage() {
  const quality = useQuery({ queryKey: ["judgeQuality"], queryFn: () => api.judgeQuality() });
  const prompts = useQuery({ queryKey: ["judgePrompts"], queryFn: api.judgePrompts });

  if (quality.isLoading) return <Skeleton className="h-96 w-full" />;
  const q = quality.data;

  return (
    <>
      <PageHeader
        title="Judge quality"
        description="How good the judges are, measured against a human gold set and each other"
      />
      {q && q.judges.length === 0 ? (
        <EmptyState
          icon={Scale}
          title="No judge scores yet"
          description="Run evaluations to produce judge scores, then add human labels so κ, α and ρ can be computed."
        />
      ) : (
        <div className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-2">
            <AgreementTable title="Judges vs human gold set" rows={q?.vs_human ?? []} />
            <AgreementTable title="Judge vs judge" rows={q?.between_judges ?? []} />
          </div>

          {q && q.costs.length > 0 && (
            <div className="overflow-hidden rounded-xl border border-border/80 bg-card shadow-xs">
              <div className="border-b px-4 py-2 text-sm font-medium">
                Cost &amp; latency per judge
              </div>
              <table className="w-full text-sm">
                <thead className="text-xs text-muted-foreground">
                  <tr className="[&>th]:px-3 [&>th]:py-2 [&>th]:text-left [&>th]:font-normal">
                    <th>Judge</th>
                    <th>Metric</th>
                    <th className="!text-right">n</th>
                    <th className="!text-right">$/1k evals</th>
                    <th className="!text-right">p50 ms</th>
                    <th className="!text-right">p95 ms</th>
                  </tr>
                </thead>
                <tbody>
                  {q.costs.map((c, i) => (
                    <tr key={i} className="border-t">
                      <td className="px-3 py-2 font-mono text-[11px]">{c.judge_model}</td>
                      <td className="px-3 py-2 text-xs">{c.metric.replace(/_/g, " ")}</td>
                      <td className="tabular px-3 py-2 text-right text-xs">{c.n}</td>
                      <td className="tabular px-3 py-2 text-right text-xs">
                        {fmtUsd(c.cost_per_1k_usd)}
                      </td>
                      <td className="tabular px-3 py-2 text-right text-xs">
                        {c.p50_latency_ms.toFixed(0)}
                      </td>
                      <td className="tabular px-3 py-2 text-right text-xs">
                        {c.p95_latency_ms.toFixed(0)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="rounded-xl border border-border/80 bg-card p-4 shadow-xs">
            <div className="text-sm font-medium">Versioned judge prompts</div>
            <p className="mt-1 text-xs text-muted-foreground">
              Every score records the prompt name and version it was produced with (provenance).
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {(prompts.data ?? []).map((p) => (
                <span
                  key={p.name}
                  className={cn("rounded-md border px-2 py-1 font-mono text-[11px]")}
                  title={`variables: ${p.variables.join(", ")}`}
                >
                  {p.name}
                  <span className="ml-1 text-muted-foreground">v{p.version}</span>
                </span>
              ))}
            </div>
            {q && (
              <div className="mt-3 text-xs text-muted-foreground">
                {q.human_labels} human label{q.human_labels === 1 ? "" : "s"} across{" "}
                {q.metrics.length} metric
                {q.metrics.length === 1 ? "" : "s"}.
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
