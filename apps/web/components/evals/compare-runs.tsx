"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ArrowRight } from "lucide-react";
import { api, type EvalRun } from "@/lib/api";
import { shortId } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

function label(r: EvalRun): string {
  return `${r.git_sha ?? shortId(r.id, 8)} · ${r.app}`;
}

export function CompareRuns({ runs }: { runs: EvalRun[] }) {
  const finished = runs.filter((r) => r.finished_at);
  const [a, setA] = useState<string>(finished[1]?.id ?? "");
  const [b, setB] = useState<string>(finished[0]?.id ?? "");
  const cmp = useQuery({
    queryKey: ["evalCompare", a, b],
    queryFn: () => api.evalCompare(a, b),
    enabled: !!a && !!b && a !== b,
  });

  if (finished.length < 2) return null;
  const metrics = cmp.data ? Object.keys(cmp.data.deltas).sort() : [];

  const Picker = ({ value, onChange }: { value: string; onChange: (v: string) => void }) => (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="h-8 w-full text-xs">
        <SelectValue placeholder="Select a run" />
      </SelectTrigger>
      <SelectContent>
        {finished.map((r) => (
          <SelectItem key={r.id} value={r.id}>
            {label(r)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );

  return (
    <div className="rounded-2xl border border-border/70 bg-card shadow-xs">
      <div className="border-b border-border/60 px-4 py-3">
        <div className="text-sm font-semibold">Compare runs</div>
        <div className="mt-0.5 text-xs text-muted-foreground">
          Metric deltas from baseline (A) to candidate (B); green is an improvement.
        </div>
      </div>
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 px-4 py-3">
        <Picker value={a} onChange={setA} />
        <ArrowRight className="h-4 w-4 text-muted-foreground" />
        <Picker value={b} onChange={setB} />
      </div>
      {a === b ? (
        <p className="px-4 pb-4 text-xs text-muted-foreground">Pick two different runs.</p>
      ) : cmp.data && metrics.length > 0 ? (
        <div className="px-4 pb-4">
          <div className="space-y-2">
            {metrics.map((m) => {
              const d = cmp.data!.deltas[m] ?? 0;
              const lowerBetter = m === "hallucination";
              const good = lowerBetter ? d < 0 : d > 0;
              const flat = Math.abs(d) < 1e-6;
              return (
                <div key={m} className="grid grid-cols-[160px_1fr_72px] items-center gap-3 text-xs">
                  <span>{m.replace(/_/g, " ")}</span>
                  <div className="relative h-2 rounded-full bg-muted">
                    <div
                      className={cn(
                        "absolute top-0 h-full rounded-full",
                        flat
                          ? "bg-muted-foreground/40"
                          : good
                            ? "bg-[var(--status-good)]"
                            : "bg-[var(--status-critical)]",
                      )}
                      style={{ width: `${Math.min(100, Math.abs(d) * 100)}%` }}
                    />
                  </div>
                  <span
                    className="tabular text-right font-medium"
                    style={{
                      color: flat
                        ? "var(--muted-foreground)"
                        : good
                          ? "var(--status-good-text)"
                          : "var(--status-critical)",
                    }}
                  >
                    {d >= 0 ? "+" : ""}
                    {d.toFixed(3)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <p className="px-4 pb-4 text-xs text-muted-foreground">
          No shared metrics between these runs.
        </p>
      )}
    </div>
  );
}
