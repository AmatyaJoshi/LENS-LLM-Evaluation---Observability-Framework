"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ExternalLink, GitBranch } from "lucide-react";
import { api } from "@/lib/api";
import { fmtAgo, fmtInt, fmtMs, shortId } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useAppFilter } from "@/components/shell/topbar";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { StatusBadge } from "@/components/shared/badges";
import { TrajectoryGraph } from "@/components/trace/trajectory-graph";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";

export default function TrajectoriesPage() {
  const [app] = useAppFilter();
  const list = useQuery({
    queryKey: ["traces", "traj", app],
    queryFn: () => api.traces({ app, limit: 40 }),
  });
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => {
    if (!selected && list.data?.items[0]) setSelected(list.data.items[0].trace_id);
  }, [list.data, selected]);
  const traj = useQuery({
    queryKey: ["trajectory", selected],
    queryFn: () => api.trajectory(selected!),
    enabled: !!selected,
  });

  return (
    <>
      <PageHeader
        title="Trajectories"
        description="Each agent run as a graph of steps: retrievals feed LLM calls, LLM calls request tools, tools feed the next step."
      />
      {list.data && list.data.items.length === 0 ? (
        <EmptyState
          icon={GitBranch}
          title="No runs yet"
          description="Trajectories are reconstructed from ingested traces. Send one and it appears here."
        />
      ) : (
        <div className="grid gap-3 lg:grid-cols-[320px_1fr]">
          <div className="overflow-hidden rounded-lg border bg-card">
            <div className="border-b px-3 py-2 text-sm text-muted-foreground">Recent runs</div>
            <ScrollArea className="h-[560px]">
              <ul className="divide-y">
                {list.isLoading &&
                  Array.from({ length: 8 }).map((_, i) => (
                    <li key={i} className="p-3">
                      <Skeleton className="h-4 w-3/4" />
                      <Skeleton className="mt-2 h-3 w-1/2" />
                    </li>
                  ))}
                {list.data?.items.map((t) => (
                  <li key={t.trace_id}>
                    <button
                      type="button"
                      onClick={() => setSelected(t.trace_id)}
                      className={cn(
                        "w-full px-3 py-2.5 text-left text-sm hover:bg-accent/50",
                        selected === t.trace_id && "bg-accent",
                      )}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate font-medium">{t.root_name}</span>
                        <StatusBadge status={t.status} />
                      </div>
                      <div className="mt-0.5 truncate text-muted-foreground">
                        {t.input_preview ?? shortId(t.trace_id, 16)}
                      </div>
                      <div className="tabular mt-1 flex gap-2 text-[12px] text-muted-foreground">
                        <span className="kind-llm">{t.llm_calls} llm</span>
                        <span className="kind-tool">{t.tool_calls} tool</span>
                        <span className="kind-retrieval">{t.retrievals} ret</span>
                        <span>{fmtMs(t.duration_ms)}</span>
                        <span className="ml-auto">{fmtAgo(t.start_ns)}</span>
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            </ScrollArea>
          </div>
          <div>
            {traj.data ? (
              <>
                <div className="mb-2 flex flex-wrap items-center gap-3 text-sm">
                  <span className="font-medium">{String(traj.data.metadata.root_span ?? "")}</span>
                  <span className="text-muted-foreground">{traj.data.app}</span>
                  <span className="tabular text-muted-foreground">
                    {traj.data.steps.length} steps · {fmtInt(traj.data.total_tokens)} tokens ·{" "}
                    {fmtMs(traj.data.duration_ms)}
                  </span>
                  <Button asChild variant="ghost" size="sm" className="ml-auto h-7 text-sm">
                    <Link href={`/traces/${traj.data.trace_id}`}>
                      Open trace <ExternalLink className="ml-1 h-3 w-3" />
                    </Link>
                  </Button>
                </div>
                <TrajectoryGraph trajectory={traj.data} className="h-[520px]" />
              </>
            ) : (
              <Skeleton className="h-[560px] w-full" />
            )}
          </div>
        </div>
      )}
    </>
  );
}
