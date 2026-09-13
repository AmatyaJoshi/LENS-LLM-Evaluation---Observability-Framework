"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { AlertTriangle, ArrowRight, Coins, Cpu, Gauge, Hash, Wrench } from "lucide-react";
import { api, type Window } from "@/lib/api";
import { fmtAgo, fmtCompact, fmtInt, fmtMs, fmtPct, fmtUsd } from "@/lib/format";
import { useAppFilter } from "@/components/shell/topbar";
import { PageHeader } from "@/components/shared/page-header";
import { KpiTile } from "@/components/shared/kpi-tile";
import { WindowSelect } from "@/components/shared/window-select";
import { EmptyState } from "@/components/shared/empty-state";
import { StatusBadge } from "@/components/shared/badges";
import {
  KindBreakdown,
  LatencyChart,
  ModelTable,
  TokensChart,
  TrafficChart,
} from "@/components/charts/overview-charts";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { IngestSnippet } from "@/components/settings/ingest-snippet";

export default function OverviewPage() {
  const [app] = useAppFilter();
  const [window, setWindow] = useState<Window>("24h");
  const stats = useQuery({
    queryKey: ["overview", app, window],
    queryFn: () => api.overview({ app, window }),
    refetchInterval: 30_000,
  });
  const recent = useQuery({
    queryKey: ["traces", "recent", app],
    queryFn: () => api.traces({ app, limit: 8 }),
  });
  const s = stats.data;
  const loading = stats.isLoading;
  const empty = !loading && s && s.traces === 0 && (recent.data?.total ?? 0) === 0;

  return (
    <>
      <PageHeader
        title="Overview"
        description={
          app ? `Traffic and health for ${app}` : "Traffic and health across all instrumented apps"
        }
        actions={<WindowSelect value={window} onChange={setWindow} />}
      />

      {stats.isError && (
        <Card className="border-[color:var(--status-critical)]/40 mb-4 px-4 py-3 text-[15px]">
          <span className="font-medium text-[color:var(--status-critical)]">API unreachable.</span>{" "}
          <span className="text-muted-foreground">
            Start it with <code className="font-mono">uv run lens serve</code> or check the endpoint
            in Settings.
          </span>
        </Card>
      )}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <KpiTile
          label="Traces"
          value={fmtInt(s?.traces ?? 0)}
          icon={Hash}
          loading={loading}
          hint={`${fmtInt(s?.spans ?? 0)} spans`}
        />
        <KpiTile
          label="Error rate"
          value={fmtPct(s?.error_rate ?? 0)}
          icon={AlertTriangle}
          loading={loading}
          tone={
            (s?.error_rate ?? 0) > 0.05
              ? "critical"
              : (s?.error_rate ?? 0) > 0
                ? "warning"
                : undefined
          }
          hint={`${fmtInt(s?.errors ?? 0)} failed`}
        />
        <KpiTile
          label="Latency p95"
          value={fmtMs(s?.p95_ms ?? 0)}
          icon={Gauge}
          loading={loading}
          hint={`p50 ${fmtMs(s?.p50_ms ?? 0)}`}
        />
        <KpiTile
          label="LLM calls"
          value={fmtInt(s?.llm_calls ?? 0)}
          icon={Cpu}
          loading={loading}
          hint={`${s?.by_model.length ?? 0} models`}
        />
        <KpiTile
          label="Tool calls"
          value={fmtInt(s?.tool_calls ?? 0)}
          icon={Wrench}
          loading={loading}
          hint={`${fmtInt(s?.retrievals ?? 0)} retrievals`}
        />
        <KpiTile
          label="Tokens"
          value={fmtCompact((s?.tokens_in ?? 0) + (s?.tokens_out ?? 0))}
          icon={Coins}
          loading={loading}
          hint={`${fmtCompact(s?.tokens_in ?? 0)} in · ${fmtCompact(s?.tokens_out ?? 0)} out · ${fmtUsd(s?.cost_usd ?? 0)}`}
        />
      </div>

      {empty ? (
        <div className="mt-6 grid gap-4 lg:grid-cols-[1fr_420px]">
          <EmptyState
            title="No traces yet"
            description="Lens is running and waiting for OpenTelemetry data. Point an instrumented app at the collector, or replay a recorded fixture to see the dashboard fill in."
            className="min-h-[360px]"
          >
            <Button asChild variant="outline" size="sm">
              <Link href="/settings">Connection guide</Link>
            </Button>
          </EmptyState>
          <IngestSnippet compact />
        </div>
      ) : (
        <>
          <div className="mt-4 grid gap-4 xl:grid-cols-3">
            <TrafficChart stats={s} window={window} />
            <LatencyChart stats={s} window={window} />
            <TokensChart stats={s} window={window} />
          </div>
          <div className="mt-4 grid gap-4 xl:grid-cols-[1fr_1fr_1.3fr]">
            <KindBreakdown stats={s} />
            <ModelTable stats={s} />
            <div className="rounded-lg border bg-card">
              <div className="flex items-center justify-between px-4 pt-3">
                <div>
                  <div className="text-[15px] font-medium">Recent traces</div>
                  <div className="text-[13px] text-muted-foreground">Newest first, live</div>
                </div>
                <Button asChild variant="ghost" size="sm" className="h-7 text-sm">
                  <Link href={app ? `/traces?app=${app}` : "/traces"}>
                    All traces <ArrowRight className="ml-1 h-3 w-3" />
                  </Link>
                </Button>
              </div>
              <ul className="mt-2 divide-y">
                {(recent.data?.items ?? []).map((t) => (
                  <li key={t.trace_id}>
                    <Link
                      href={`/traces/${t.trace_id}`}
                      className="flex items-center gap-3 px-4 py-2 text-sm hover:bg-accent/50"
                    >
                      <StatusBadge status={t.status} />
                      <span className="min-w-0 flex-1 truncate">
                        <span className="font-medium">{t.root_name}</span>
                        {t.input_preview && (
                          <span className="ml-2 text-muted-foreground">{t.input_preview}</span>
                        )}
                      </span>
                      <span className="tabular hidden text-muted-foreground sm:inline">
                        {fmtMs(t.duration_ms)}
                      </span>
                      <span className="tabular w-16 text-right text-muted-foreground">
                        {fmtAgo(t.start_ns)}
                      </span>
                    </Link>
                  </li>
                ))}
                {recent.data && recent.data.items.length === 0 && (
                  <li className="px-4 py-6 text-center text-sm text-muted-foreground">
                    No traces for this app.
                  </li>
                )}
              </ul>
            </div>
          </div>
        </>
      )}
    </>
  );
}
