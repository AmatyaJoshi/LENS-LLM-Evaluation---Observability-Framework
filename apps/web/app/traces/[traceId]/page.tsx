"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { ArrowLeft, Check, Copy, Download } from "lucide-react";
import { api } from "@/lib/api";
import { fmtDateTime, fmtInt, fmtMs, fmtUsd } from "@/lib/format";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { StatusBadge } from "@/components/shared/badges";
import { Waterfall } from "@/components/trace/waterfall";
import { SpanInspector } from "@/components/trace/span-inspector";
import { Conversation } from "@/components/trace/conversation";
import { Retrievals, Tools } from "@/components/trace/evidence";
import { TrajectoryGraph } from "@/components/trace/trajectory-graph";
import { ScoresPanel, SecurityPanel } from "@/components/trace/side-panels";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-md border bg-card px-3 py-2">
      <div className="text-[12px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="tabular mt-0.5 text-[15px] font-medium">{value}</div>
    </div>
  );
}

export default function TraceDetailPage() {
  const { traceId } = useParams<{ traceId: string }>();
  const spans = useQuery({ queryKey: ["trace", traceId], queryFn: () => api.trace(traceId) });
  const traj = useQuery({
    queryKey: ["trajectory", traceId],
    queryFn: () => api.trajectory(traceId),
  });
  const [selected, setSelected] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const selectedSpan = useMemo(
    () => spans.data?.find((s) => s.span_id === selected) ?? null,
    [spans.data, selected],
  );

  if (spans.isError) {
    return (
      <EmptyState
        title="Trace not found"
        description={`No spans stored for ${traceId}. It may have expired (30-day TTL) or never been ingested.`}
      >
        <Button asChild variant="outline" size="sm">
          <Link href="/traces">Back to traces</Link>
        </Button>
      </EmptyState>
    );
  }

  const t = traj.data;
  const copyId = async () => {
    try {
      await navigator.clipboard.writeText(traceId);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore */
    }
  };
  const exportJson = () => {
    const blob = new Blob([JSON.stringify({ trajectory: t, spans: spans.data }, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `lens-trace-${traceId}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <div className="mb-3">
        <Button
          asChild
          variant="ghost"
          size="sm"
          className="-ml-2 h-7 text-sm text-muted-foreground"
        >
          <Link href="/traces">
            <ArrowLeft className="mr-1 h-3.5 w-3.5" /> Traces
          </Link>
        </Button>
      </div>
      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-2">
            {t ? String(t.metadata.root_span ?? "Trace") : <Skeleton className="h-6 w-40" />}
            {t && <StatusBadge status={t.status} />}
            {t && (
              <span className="rounded-md border px-1.5 py-0.5 text-[13px] font-normal text-muted-foreground">
                {t.app}
              </span>
            )}
          </span>
        }
        description={
          <span className="flex flex-wrap items-center gap-2 font-mono text-[13px]">
            {traceId}
            <button
              type="button"
              onClick={copyId}
              className="text-muted-foreground hover:text-foreground"
              aria-label="Copy trace id"
            >
              {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
            </button>
            {t?.run_id && <span className="text-muted-foreground">run {t.run_id}</span>}
            {t?.metadata["lens.session.id"] != null && (
              <span className="text-muted-foreground">
                session {String(t.metadata["lens.session.id"])}
              </span>
            )}
            {spans.data?.[0] && (
              <span className="text-muted-foreground">{fmtDateTime(spans.data[0].start_ns)}</span>
            )}
          </span>
        }
        actions={
          <Button
            variant="outline"
            size="sm"
            className="h-8 text-sm"
            onClick={exportJson}
            disabled={!t}
          >
            <Download className="mr-1.5 h-3.5 w-3.5" /> Export JSON
          </Button>
        }
      />

      <div className="grid grid-cols-3 gap-2 md:grid-cols-6">
        <Stat label="Duration" value={t ? fmtMs(t.duration_ms) : "…"} />
        <Stat label="Steps" value={t ? t.steps.length : "…"} />
        <Stat label="LLM calls" value={t ? t.steps.filter((s) => s.llm_call).length : "…"} />
        <Stat
          label="Tool calls"
          value={t ? t.steps.reduce((a, s) => a + s.tool_calls.length, 0) : "…"}
        />
        <Stat label="Tokens" value={t ? fmtInt(t.total_tokens) : "…"} />
        <Stat label="Cost" value={t ? fmtUsd(t.total_cost_usd) : "…"} />
      </div>

      {t && (
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          <div className="rounded-lg border bg-card p-3">
            <div className="text-[12px] uppercase tracking-wider text-muted-foreground">Input</div>
            <p className="mt-1 whitespace-pre-wrap text-[15px] leading-relaxed">
              {t.user_input ?? <span className="text-muted-foreground">none</span>}
            </p>
          </div>
          <div className="rounded-lg border bg-card p-3">
            <div className="text-[12px] uppercase tracking-wider text-muted-foreground">
              Final output
            </div>
            <p className="mt-1 whitespace-pre-wrap text-[15px] leading-relaxed">
              {t.final_output ?? <span className="text-muted-foreground">none</span>}
            </p>
          </div>
        </div>
      )}

      <Tabs defaultValue="waterfall" className="mt-4">
        <TabsList className="h-9">
          <TabsTrigger value="waterfall" className="text-sm">
            Waterfall{" "}
            {spans.data && (
              <span className="tabular ml-1 text-muted-foreground">{spans.data.length}</span>
            )}
          </TabsTrigger>
          <TabsTrigger value="graph" className="text-sm">
            Trajectory
          </TabsTrigger>
          <TabsTrigger value="conversation" className="text-sm">
            Conversation
          </TabsTrigger>
          <TabsTrigger value="retrievals" className="text-sm">
            Retrievals{" "}
            {t && (
              <span className="tabular ml-1 text-muted-foreground">
                {t.steps.reduce((a, s) => a + s.retrievals.length, 0)}
              </span>
            )}
          </TabsTrigger>
          <TabsTrigger value="tools" className="text-sm">
            Tools{" "}
            {t && (
              <span className="tabular ml-1 text-muted-foreground">
                {t.steps.reduce((a, s) => a + s.tool_calls.length, 0)}
              </span>
            )}
          </TabsTrigger>
          <TabsTrigger value="raw" className="text-sm">
            Raw
          </TabsTrigger>
        </TabsList>

        <TabsContent value="waterfall" className="mt-3">
          <ResizablePanelGroup
            direction="horizontal"
            className="min-h-[460px] rounded-lg border bg-card"
          >
            <ResizablePanel defaultSize={62} minSize={40}>
              {spans.data ? (
                <Waterfall spans={spans.data} selected={selected} onSelect={setSelected} />
              ) : (
                <div className="space-y-2 p-3">
                  {Array.from({ length: 6 }).map((_, i) => (
                    <Skeleton key={i} className="h-5 w-full" />
                  ))}
                </div>
              )}
            </ResizablePanel>
            <ResizableHandle withHandle />
            <ResizablePanel defaultSize={38} minSize={25}>
              <SpanInspector span={selectedSpan} />
            </ResizablePanel>
          </ResizablePanelGroup>
        </TabsContent>

        <TabsContent value="graph" className="mt-3">
          {t ? (
            <div className="grid gap-3 xl:grid-cols-[1fr_360px]">
              <TrajectoryGraph trajectory={t} onSelectSpan={setSelected} />
              <div className="h-[520px] overflow-hidden rounded-lg border bg-card">
                <SpanInspector span={selectedSpan} />
              </div>
            </div>
          ) : (
            <Skeleton className="h-[520px] w-full" />
          )}
        </TabsContent>

        <TabsContent value="conversation" className="mt-3">
          <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
            <div className="rounded-lg border bg-card p-4">
              {t ? <Conversation trajectory={t} /> : <Skeleton className="h-64 w-full" />}
            </div>
            <div className="space-y-3">
              {t && <ScoresPanel trajectory={t} />}
              {spans.data && <SecurityPanel spans={spans.data} />}
            </div>
          </div>
        </TabsContent>

        <TabsContent value="retrievals" className="mt-3">
          {t ? <Retrievals trajectory={t} /> : <Skeleton className="h-40 w-full" />}
        </TabsContent>
        <TabsContent value="tools" className="mt-3">
          {t ? <Tools trajectory={t} /> : <Skeleton className="h-40 w-full" />}
        </TabsContent>
        <TabsContent value="raw" className="mt-3">
          <pre className="scrollbar-thin max-h-[640px] overflow-auto rounded-lg border bg-card p-4 font-mono text-[13px] leading-relaxed">
            {JSON.stringify({ trajectory: t, spans: spans.data }, null, 2)}
          </pre>
        </TabsContent>
      </Tabs>
    </>
  );
}
