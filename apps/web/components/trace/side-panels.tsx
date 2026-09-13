"use client";

import Link from "next/link";
import { FlaskConical, ShieldCheck, Scissors } from "lucide-react";
import type { Span, Trajectory } from "@/lib/api";
import { fmtInt } from "@/lib/format";
import { Button } from "@/components/ui/button";

export function ScoresPanel({ trajectory }: { trajectory: Trajectory }) {
  const expected = trajectory.metadata["lens.eval.expected_output"];
  const feedback = trajectory.metadata["lens.user.feedback"];
  return (
    <div className="rounded-lg border bg-card p-3">
      <div className="flex items-center gap-2 text-[15px] font-medium">
        <FlaskConical className="h-4 w-4 text-muted-foreground" /> Evaluation
      </div>
      <p className="mt-1.5 text-sm text-muted-foreground">
        No scores recorded for this trace. Faithfulness, relevance, context precision/recall and
        hallucination scores are produced by <code className="font-mono">lens eval</code> and online
        sampling (phase 3).
      </p>
      <dl className="mt-3 grid grid-cols-[110px_1fr] gap-y-1 text-sm">
        <dt className="text-muted-foreground">Expected output</dt>
        <dd className="truncate">
          {expected ? (
            String(expected)
          ) : (
            <span className="text-muted-foreground">not provided</span>
          )}
        </dd>
        <dt className="text-muted-foreground">User feedback</dt>
        <dd>
          {feedback != null ? (
            String(feedback)
          ) : (
            <span className="text-muted-foreground">none</span>
          )}
        </dd>
      </dl>
      <Button asChild variant="outline" size="sm" className="mt-3 h-7 text-sm">
        <Link href="/evaluations">About evaluations</Link>
      </Button>
    </div>
  );
}

export function SecurityPanel({ spans }: { spans: Span[] }) {
  const truncated = spans.filter((s) => s.truncated_attributes.length > 0);
  const attrBytes = spans.reduce((acc, s) => acc + JSON.stringify(s.attributes).length, 0);
  const externalDocs = spans.filter((s) => s.kind === "retrieval").length;
  const toolResults = spans.filter((s) => s.kind === "tool").length;
  return (
    <div className="rounded-lg border bg-card p-3">
      <div className="flex items-center gap-2 text-[15px] font-medium">
        <ShieldCheck className="h-4 w-4 text-muted-foreground" /> Security
      </div>
      <dl className="mt-2 grid grid-cols-[130px_1fr] gap-y-1 text-sm">
        <dt className="text-muted-foreground">Injection scan</dt>
        <dd className="text-muted-foreground">not scanned · detector ships in phase 6</dd>
        <dt className="text-muted-foreground">Untrusted inputs</dt>
        <dd>
          {externalDocs} retrieval span{externalDocs === 1 ? "" : "s"}, {toolResults} tool result
          {toolResults === 1 ? "" : "s"}
        </dd>
        <dt className="text-muted-foreground">Payload size</dt>
        <dd className="tabular">{fmtInt(Math.round(attrBytes / 1024))} KB of attributes</dd>
        <dt className="text-muted-foreground">Truncation</dt>
        <dd>
          {truncated.length === 0 ? (
            "none"
          ) : (
            <span className="inline-flex items-center gap-1 text-[color:var(--status-warning)]">
              <Scissors className="h-3 w-3" /> {truncated.length} span
              {truncated.length === 1 ? "" : "s"} clipped at 64 KB
            </span>
          )}
        </dd>
        <dt className="text-muted-foreground">PII redaction</dt>
        <dd className="text-muted-foreground">per-app policy (LENS_REDACT_APPS)</dd>
      </dl>
    </div>
  );
}
