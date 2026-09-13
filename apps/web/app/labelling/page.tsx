"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Keyboard, Tags } from "lucide-react";
import { api, type MetricSpec, type QueueItem } from "@/lib/api";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

const KEYS: Record<string, number> = { "0": 0, "1": 1, "2": 0.25, "3": 0.5, "4": 0.75, "5": 1 };

export default function LabellingPage() {
  const qc = useQueryClient();
  const metrics = useQuery({ queryKey: ["metrics"], queryFn: api.metrics });
  const [metric, setMetric] = useState("faithfulness");
  const [labeller, setLabeller] = useState("");
  const [idx, setIdx] = useState(0);

  const queue = useQuery({
    queryKey: ["labelQueue", metric, labeller],
    queryFn: () => api.labelQueue({ metric, labeller: labeller || undefined, limit: 50 }),
    enabled: !!metric,
  });

  const save = useMutation({
    mutationFn: (v: { item: QueueItem; value: number }) =>
      api.createLabel({
        trace_id: v.item.trace_id,
        example_id: v.item.example_id,
        metric,
        value: v.value,
        labeller: labeller || "me",
      }),
    onSuccess: () => {
      setIdx((i) => i + 1);
      void qc.invalidateQueries({ queryKey: ["labelQueue"] });
    },
  });

  const items = queue.data ?? [];
  const item = items[idx];

  useEffect(() => setIdx(0), [metric, labeller]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!item || save.isPending) return;
      const el = e.target as HTMLElement;
      if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") return;
      if (e.key in KEYS) {
        e.preventDefault();
        save.mutate({ item, value: KEYS[e.key]! });
      } else if (e.key === "s") {
        setIdx((i) => i + 1);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [item, save]);

  return (
    <>
      <PageHeader
        title="Labelling"
        description="Human labels for the gold set, disagreement-first. Keys 0-5 score, s skips."
        actions={
          <div className="flex items-center gap-2">
            <Input
              value={labeller}
              onChange={(e) => setLabeller(e.target.value)}
              placeholder="your name"
              className="h-8 w-32 text-xs"
            />
            <Select value={metric} onValueChange={setMetric}>
              <SelectTrigger className="h-8 w-[180px] text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(metrics.data ?? []).map((m: MetricSpec) => (
                  <SelectItem key={m.name} value={m.name}>
                    {m.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        }
      />

      {queue.isLoading ? (
        <Skeleton className="h-80 w-full" />
      ) : items.length === 0 ? (
        <EmptyState
          icon={Tags}
          title="Nothing to label"
          description="The queue is empty for this metric. Score some traces first, or you've labelled everything with disagreement."
        />
      ) : !item ? (
        <EmptyState
          icon={Tags}
          title="Queue complete"
          description={`You labelled ${items.length} items this session.`}
        >
          <Button variant="outline" size="sm" onClick={() => setIdx(0)}>
            Restart
          </Button>
        </EmptyState>
      ) : (
        <div className="mx-auto max-w-3xl">
          <div className="mb-2 flex items-center justify-between text-xs text-muted-foreground">
            <span>
              {idx + 1} of {items.length}
            </span>
            <span>
              disagreement{" "}
              <span className="font-medium text-foreground">{item.priority.toFixed(2)}</span> ·{" "}
              {item.human_labels} existing label{item.human_labels === 1 ? "" : "s"}
            </span>
          </div>

          <div className="space-y-3 rounded-lg border bg-card p-4">
            <div>
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Input
              </div>
              <p className="mt-1 whitespace-pre-wrap text-sm">{item.input ?? "—"}</p>
            </div>
            {item.contexts.length > 0 && (
              <div>
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                  Context
                </div>
                <ul className="mt-1 space-y-1">
                  {item.contexts.slice(0, 4).map((c, i) => (
                    <li key={i} className="rounded border-l-2 pl-2 text-xs text-muted-foreground">
                      {c}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <div>
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Output
              </div>
              <p className="mt-1 whitespace-pre-wrap text-sm">{item.output ?? "—"}</p>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Judge scores
              </div>
              <div className="mt-1 flex flex-wrap gap-2">
                {item.judge_scores.map((js, i) => (
                  <span
                    key={i}
                    className="rounded-md border px-2 py-1 text-xs"
                    title={js.rationale ?? ""}
                  >
                    <span className="font-mono text-[10px] text-muted-foreground">
                      {js.judge_model}
                    </span>{" "}
                    <span className="font-medium">{js.value.toFixed(2)}</span>
                  </span>
                ))}
              </div>
            </div>
          </div>

          <div className="mt-3 flex items-center justify-center gap-2">
            {[
              { k: "0", v: 0, label: "0.0" },
              { k: "2", v: 0.25, label: "0.25" },
              { k: "3", v: 0.5, label: "0.5" },
              { k: "4", v: 0.75, label: "0.75" },
              { k: "5", v: 1, label: "1.0" },
            ].map((b) => (
              <Button
                key={b.k}
                variant="outline"
                className="h-11 w-16 flex-col gap-0"
                disabled={save.isPending}
                onClick={() => save.mutate({ item, value: b.v })}
              >
                <span className="text-sm font-semibold">{b.label}</span>
                <span className="text-[9px] text-muted-foreground">key {b.k}</span>
              </Button>
            ))}
            <Button variant="ghost" className="h-11" onClick={() => setIdx((i) => i + 1)}>
              Skip <span className="ml-1 text-[9px] text-muted-foreground">s</span>
            </Button>
          </div>
          <div className="mt-3 flex items-center justify-center gap-1.5 text-[11px] text-muted-foreground">
            <Keyboard className="h-3 w-3" /> keyboard-driven: press 0-5 to score, s to skip
          </div>
        </div>
      )}
    </>
  );
}
