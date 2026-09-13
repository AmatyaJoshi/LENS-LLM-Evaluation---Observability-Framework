"use client";

import { Database, Wrench } from "lucide-react";
import type { Trajectory } from "@/lib/api";
import { fmtMs, stringify } from "@/lib/format";
import { EmptyState } from "@/components/shared/empty-state";

export function Retrievals({ trajectory }: { trajectory: Trajectory }) {
  const rets = trajectory.steps.flatMap((s) => s.retrievals.map((r) => ({ step: s, r })));
  if (rets.length === 0) {
    return (
      <EmptyState
        icon={Database}
        title="No retrievals"
        description="Set lens.retrieval.query and lens.retrieval.docs (or db.system=vector) on retrieval spans to see retrieved context here."
      />
    );
  }
  return (
    <div className="space-y-4">
      {rets.map(({ step, r }) => (
        <div key={r.span_id} className="rounded-lg border bg-card">
          <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2 text-sm">
            <Database className="kind-retrieval h-3.5 w-3.5" />
            <span className="font-medium">Step {step.index + 1}</span>
            <span className="text-muted-foreground">·</span>
            <span className="truncate">
              {r.query || <span className="text-muted-foreground">no query</span>}
            </span>
            <span className="tabular ml-auto text-muted-foreground">
              {r.documents.length} docs · {fmtMs(r.duration_ms)}
            </span>
          </div>
          <ol className="divide-y">
            {r.documents.map((d) => (
              <li
                key={`${d.rank}-${d.id ?? ""}`}
                className="grid grid-cols-[36px_1fr_72px] gap-2 px-3 py-2 text-sm"
              >
                <span className="tabular text-muted-foreground">#{d.rank}</span>
                <div className="min-w-0">
                  {d.id && (
                    <div className="font-mono text-[12px] text-muted-foreground">{d.id}</div>
                  )}
                  <div className="whitespace-pre-wrap break-words leading-relaxed">{d.text}</div>
                </div>
                <span className="tabular text-right text-muted-foreground">
                  {d.score != null ? d.score.toFixed(3) : "—"}
                </span>
              </li>
            ))}
          </ol>
        </div>
      ))}
    </div>
  );
}

export function Tools({ trajectory }: { trajectory: Trajectory }) {
  const tools = trajectory.steps.flatMap((s) => s.tool_calls.map((t) => ({ step: s, t })));
  if (tools.length === 0) {
    return (
      <EmptyState
        icon={Wrench}
        title="No tool executions"
        description="Tool spans (gen_ai.tool.name or traceloop.span.kind=tool) appear here with their arguments and results."
      />
    );
  }
  return (
    <div className="space-y-3">
      {tools.map(({ step, t }) => (
        <div key={t.span_id} className="rounded-lg border bg-card">
          <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2 text-sm">
            <Wrench className="kind-tool h-3.5 w-3.5" />
            <span className="font-mono font-medium">{t.name}</span>
            {t.call_id && <span className="font-mono text-muted-foreground">{t.call_id}</span>}
            <span className="text-muted-foreground">· step {step.index + 1}</span>
            <span className="tabular ml-auto text-muted-foreground">{fmtMs(t.duration_ms)}</span>
            {t.error && <span className="text-[color:var(--status-critical)]">{t.error}</span>}
          </div>
          <div className="grid gap-0 md:grid-cols-2 md:divide-x">
            <div className="p-3">
              <div className="mb-1 text-[12px] uppercase tracking-wider text-muted-foreground">
                Arguments
              </div>
              <pre className="scrollbar-thin overflow-x-auto font-mono text-[13px] leading-relaxed">
                {stringify(t.args)}
              </pre>
            </div>
            <div className="p-3">
              <div className="mb-1 text-[12px] uppercase tracking-wider text-muted-foreground">
                Result
              </div>
              <pre className="scrollbar-thin max-h-64 overflow-auto font-mono text-[13px] leading-relaxed">
                {t.result == null ? (
                  <span className="text-muted-foreground">none</span>
                ) : (
                  stringify(t.result)
                )}
              </pre>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
