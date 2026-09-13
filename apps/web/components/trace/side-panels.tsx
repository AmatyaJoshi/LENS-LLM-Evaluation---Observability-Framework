"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { FlaskConical, Play, Scissors, ShieldCheck } from "lucide-react";
import type { Span, Trajectory } from "@/lib/api";
import { api } from "@/lib/api";
import { fmtInt } from "@/lib/format";
import { ScoreBar } from "@/components/shared/score-bar";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

export function ScoresPanel({ trajectory }: { trajectory: Trajectory }) {
  const qc = useQueryClient();
  const scores = useQuery({
    queryKey: ["traceScores", trajectory.trace_id],
    queryFn: () => api.traceScores(trajectory.trace_id),
  });
  const evaluate = useMutation({
    mutationFn: () => api.evaluateTrace(trajectory.trace_id),
    onSuccess: () =>
      setTimeout(
        () => void qc.invalidateQueries({ queryKey: ["traceScores", trajectory.trace_id] }),
        1500,
      ),
  });
  const expected = trajectory.metadata["lens.eval.expected_output"];
  const rows = scores.data ?? [];

  return (
    <div className="rounded-lg border bg-card p-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-medium">
          <FlaskConical className="h-4 w-4 text-muted-foreground" /> Evaluation
        </div>
        <Button
          variant="outline"
          size="sm"
          className="h-7 text-xs"
          disabled={evaluate.isPending}
          onClick={() => evaluate.mutate()}
        >
          <Play className="mr-1 h-3 w-3" /> {evaluate.isPending ? "scoring…" : "Score now"}
        </Button>
      </div>

      {scores.isLoading ? (
        <Skeleton className="mt-3 h-16" />
      ) : rows.length === 0 ? (
        <p className="mt-2 text-xs text-muted-foreground">
          No scores yet. Score now runs the online metrics, or run{" "}
          <code className="font-mono">lens eval</code>.
        </p>
      ) : (
        <ul className="mt-3 space-y-2">
          {rows.map((s, i) => (
            <li key={i} className="text-xs" title={s.rationale ?? ""}>
              <div className="flex items-center justify-between gap-2">
                <span>{s.metric.replace(/_/g, " ")}</span>
                <ScoreBar value={s.value} higherIsBetter={s.metric !== "hallucination"} />
              </div>
              {s.rationale && (
                <div className="mt-0.5 line-clamp-2 text-muted-foreground">{s.rationale}</div>
              )}
            </li>
          ))}
        </ul>
      )}

      <dl className="mt-3 grid grid-cols-[110px_1fr] gap-y-1 border-t pt-2 text-xs">
        <dt className="text-muted-foreground">Expected</dt>
        <dd className="truncate">
          {expected ? (
            String(expected)
          ) : (
            <span className="text-muted-foreground">not provided</span>
          )}
        </dd>
      </dl>
      <Button asChild variant="ghost" size="sm" className="mt-2 h-7 text-xs">
        <Link href="/evaluations">All evaluations</Link>
      </Button>
    </div>
  );
}

export function SecurityPanel({ spans }: { spans: Span[] }) {
  const flaggedSpans = spans.filter((s) => s.attributes["lens.security.flagged"]);
  const scored = spans.filter((s) => s.attributes["lens.security.injection_score"] != null);
  const truncated = spans.filter((s) => s.truncated_attributes.length > 0);
  const attrBytes = spans.reduce((acc, s) => acc + JSON.stringify(s.attributes).length, 0);
  const maxScore = scored.reduce(
    (m, s) => Math.max(m, Number(s.attributes["lens.security.injection_score"] ?? 0)),
    0,
  );

  return (
    <div className="rounded-lg border bg-card p-3">
      <div className="flex items-center gap-2 text-sm font-medium">
        <ShieldCheck className="h-4 w-4 text-muted-foreground" /> Security
      </div>
      <dl className="mt-2 grid grid-cols-[130px_1fr] gap-y-1 text-xs">
        <dt className="text-muted-foreground">Injection scan</dt>
        <dd>
          {scored.length === 0 ? (
            <span className="text-muted-foreground">not scanned</span>
          ) : flaggedSpans.length > 0 ? (
            <span className="font-medium text-[color:var(--status-critical)]">
              {flaggedSpans.length} span{flaggedSpans.length === 1 ? "" : "s"} flagged (max{" "}
              {maxScore.toFixed(2)})
            </span>
          ) : (
            <span className="text-[color:var(--status-good-text)]">
              clean (max {maxScore.toFixed(2)})
            </span>
          )}
        </dd>
        <dt className="text-muted-foreground">Payload size</dt>
        <dd className="tabular">{fmtInt(Math.round(attrBytes / 1024))} KB attributes</dd>
        <dt className="text-muted-foreground">Truncation</dt>
        <dd>
          {truncated.length === 0 ? (
            "none"
          ) : (
            <span className="inline-flex items-center gap-1 text-[color:var(--status-warning)]">
              <Scissors className="h-3 w-3" /> {truncated.length} clipped at 64 KB
            </span>
          )}
        </dd>
      </dl>
      {flaggedSpans.length > 0 && (
        <div className="mt-2 space-y-1">
          {flaggedSpans.map((s) => (
            <div
              key={s.span_id}
              className="rounded border-l-2 border-[color:var(--status-critical)] pl-2 text-[11px]"
            >
              <span className="font-mono">{s.name}</span>{" "}
              <span className="text-muted-foreground">
                {String(s.attributes["lens.security.reasons"] ?? "")}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
