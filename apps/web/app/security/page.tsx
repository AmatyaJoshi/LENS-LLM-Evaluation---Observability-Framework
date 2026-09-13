"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { ShieldAlert, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import { fmtAgo, shortId } from "@/lib/format";
import { useAppFilter } from "@/components/shell/topbar";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { KpiTile } from "@/components/shared/kpi-tile";
import { Skeleton } from "@/components/ui/skeleton";

export default function SecurityPage() {
  const [app] = useAppFilter();
  const flagged = useQuery({
    queryKey: ["flagged", app],
    queryFn: () => api.flaggedTraffic({ app }),
  });
  const caps = useQuery({
    queryKey: ["assistant-caps"],
    queryFn: api.assistantCapabilities,
    retry: 0,
  });

  const total = flagged.data?.length ?? 0;
  const maxScore = flagged.data?.reduce((m, f) => Math.max(m, f.max_score), 0) ?? 0;

  return (
    <>
      <PageHeader
        title="Security"
        description="Live prompt-injection detection over incoming messages, retrieved docs and tool results"
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <KpiTile
          label="Flagged traces"
          value={flagged.isLoading ? "…" : total}
          icon={ShieldAlert}
          tone={total > 0 ? "critical" : "good"}
        />
        <KpiTile label="Max injection score" value={maxScore ? maxScore.toFixed(2) : "0.00"} />
        <KpiTile
          label="Detector"
          value="heuristic"
          hint="ONNX DeBERTa when LENS_DETECTOR_PATH is set"
        />
        <KpiTile label="Threshold" value="0.50" hint="lens.security.flagged" />
      </div>

      <div className="mt-4 rounded-xl border border-border/80 bg-card shadow-xs">
        <div className="flex items-center gap-2 border-b px-4 py-2 text-sm font-medium">
          <ShieldCheck className="h-4 w-4 text-muted-foreground" /> Flagged traffic
        </div>
        {flagged.isLoading ? (
          <Skeleton className="m-4 h-40" />
        ) : total === 0 ? (
          <EmptyState
            icon={ShieldCheck}
            title="No flagged traffic"
            description="The injection detector scans every ingested user message, retrieved document and tool result. Nothing has crossed the threshold in this window."
            className="m-4 border-0"
          />
        ) : (
          <ul className="divide-y">
            {flagged.data?.map((f) => (
              <li key={f.trace_id} className="px-4 py-2.5 text-xs">
                <div className="flex items-center gap-3">
                  <Link href={`/traces/${f.trace_id}`} className="font-mono hover:underline">
                    {shortId(f.trace_id, 16)}
                  </Link>
                  <span className="text-muted-foreground">{f.app}</span>
                  <span
                    className="ml-auto rounded px-1.5 py-0.5 font-medium"
                    style={{
                      background: "var(--status-critical)",
                      color: "white",
                      opacity: 0.15 + 0.85 * f.max_score,
                    }}
                  >
                    {f.max_score.toFixed(2)}
                  </span>
                  <span className="w-16 text-right text-muted-foreground">
                    {fmtAgo(f.start_ns)}
                  </span>
                </div>
                <div className="mt-1 flex flex-wrap gap-2">
                  {f.flagged_spans.map((s) => (
                    <span
                      key={s.span_id}
                      className="rounded border px-1.5 py-0.5 text-[10px] text-muted-foreground"
                    >
                      {s.kind} · {(s.score ?? 0).toFixed(2)}
                      {s.reasons && <span className="ml-1 opacity-70">{s.reasons}</span>}
                    </span>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="mt-4 rounded-xl border border-border/80 bg-card p-4 text-xs text-muted-foreground shadow-xs">
        <div className="text-sm font-medium text-foreground">How detection works</div>
        <p className="mt-1">
          At ingest, every untrusted text segment (user and tool messages, retrieved documents, tool
          results) is scored by the injection detector. Spans over the threshold get{" "}
          <code className="font-mono">lens.security.injection_score</code> and{" "}
          <code className="font-mono">lens.security.flagged</code> attributes, and can trigger
          online evaluation. The default is a fast heuristic detector; a fine-tuned ONNX DeBERTa
          classifier (phase 6/7 training) loads when{" "}
          <code className="font-mono">LENS_DETECTOR_PATH</code> is set, targeting under 50 ms p95 on
          CPU.
        </p>
        {caps.data && (
          <p className="mt-2">
            Assistant grounding: {caps.data.grounded_answers ? "LLM configured" : caps.data.note}
          </p>
        )}
      </div>
    </>
  );
}
