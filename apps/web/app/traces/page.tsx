"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Download, ListTree, Scissors } from "lucide-react";
import { api, windowToSinceNs, type TraceQuery } from "@/lib/api";
import { fmtCompact, fmtDateTime, fmtMs, shortId } from "@/lib/format";
import { useAppFilter } from "@/components/shell/topbar";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { StatusBadge } from "@/components/shared/badges";
import { DEFAULT_FILTERS, TraceFilters, type Filters } from "@/components/traces/trace-filters";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const PAGE = 25;

function useDebounced<T>(value: T, ms = 250): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export default function TracesPage() {
  const router = useRouter();
  const [app] = useAppFilter();
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [page, setPage] = useState(0);
  const debounced = useDebounced(filters);

  useEffect(() => setPage(0), [debounced, app]);

  const query: TraceQuery = useMemo(
    () => ({
      app,
      q: debounced.q || undefined,
      status: debounced.status || undefined,
      kind: debounced.kind || undefined,
      model: debounced.model || undefined,
      min_duration_ms: debounced.minDuration ? Number(debounced.minDuration) : undefined,
      since_ns: windowToSinceNs(debounced.window),
      sort: debounced.sort,
      limit: PAGE,
      offset: page * PAGE,
    }),
    [debounced, app, page],
  );

  const traces = useQuery({
    queryKey: ["traces", "list", query],
    queryFn: () => api.traces(query),
    placeholderData: keepPreviousData,
  });
  const stats = useQuery({
    queryKey: ["overview", app, "all"],
    queryFn: () => api.overview({ app, window: "all" }),
  });
  const models = useMemo(() => (stats.data?.by_model ?? []).map((m) => m.model), [stats.data]);

  const total = traces.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE));

  const exportCsv = () => {
    const rows = traces.data?.items ?? [];
    const head = [
      "trace_id",
      "app",
      "root_name",
      "start",
      "status",
      "duration_ms",
      "llm_calls",
      "tool_calls",
      "retrievals",
      "tokens_in",
      "tokens_out",
      "models",
      "run_id",
    ];
    const csv = [head.join(",")]
      .concat(
        rows.map((t) =>
          [
            t.trace_id,
            t.app,
            t.root_name,
            new Date(t.start_ns / 1e6).toISOString(),
            t.status,
            t.duration_ms,
            t.llm_calls,
            t.tool_calls,
            t.retrievals,
            t.tokens_in,
            t.tokens_out,
            t.models.join("|"),
            t.run_id ?? "",
          ]
            .map((v) => `"${String(v).replace(/"/g, '""')}"`)
            .join(","),
        ),
      )
      .join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `lens-traces-${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <PageHeader
        title="Traces"
        description={
          traces.data
            ? `${total.toLocaleString()} trace${total === 1 ? "" : "s"} match`
            : "Every instrumented run, newest first"
        }
        actions={
          <Button
            variant="outline"
            size="sm"
            className="h-8 text-sm"
            onClick={exportCsv}
            disabled={!traces.data?.items.length}
          >
            <Download className="mr-1.5 h-3.5 w-3.5" /> Export page
          </Button>
        }
      />
      <div className="mb-3">
        <TraceFilters value={filters} onChange={setFilters} models={models} />
      </div>

      <div className="overflow-hidden rounded-2xl border border-border/70 bg-card shadow-xs">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent [&>th]:h-9 [&>th]:text-sm">
              <TableHead className="w-[90px]">Status</TableHead>
              <TableHead>Trace</TableHead>
              <TableHead className="hidden lg:table-cell">Input</TableHead>
              <TableHead className="w-[110px] text-right">Duration</TableHead>
              <TableHead className="hidden w-[150px] text-right md:table-cell">
                LLM · Tool · Ret
              </TableHead>
              <TableHead className="hidden w-[90px] text-right md:table-cell">Tokens</TableHead>
              <TableHead className="hidden w-[150px] xl:table-cell">Model</TableHead>
              <TableHead className="w-[150px] text-right">Started</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {traces.isLoading &&
              Array.from({ length: 8 }).map((_, i) => (
                <TableRow key={i}>
                  {Array.from({ length: 8 }).map((__, j) => (
                    <TableCell key={j}>
                      <Skeleton className="h-4 w-full" />
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            {traces.data?.items.map((t) => (
              <TableRow
                key={t.trace_id}
                className="cursor-pointer text-sm"
                onClick={() => router.push(`/traces/${t.trace_id}`)}
              >
                <TableCell>
                  <StatusBadge status={t.status} />
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{t.root_name}</span>
                    {t.truncated && (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Scissors className="h-3 w-3 text-[color:var(--status-warning)]" />
                        </TooltipTrigger>
                        <TooltipContent>
                          Some attributes exceeded 64 KB and were truncated
                        </TooltipContent>
                      </Tooltip>
                    )}
                  </div>
                  <div className="font-mono text-[12px] text-muted-foreground">
                    {shortId(t.trace_id, 16)}
                    {!app && <span className="ml-2">{t.app}</span>}
                    {t.run_id && <span className="ml-2">run {t.run_id}</span>}
                  </div>
                </TableCell>
                <TableCell className="hidden max-w-[420px] lg:table-cell">
                  <div className="truncate text-muted-foreground">{t.input_preview ?? "—"}</div>
                </TableCell>
                <TableCell className="tabular text-right">{fmtMs(t.duration_ms)}</TableCell>
                <TableCell className="tabular hidden text-right text-muted-foreground md:table-cell">
                  <span className="kind-llm">{t.llm_calls}</span> ·{" "}
                  <span className="kind-tool">{t.tool_calls}</span> ·{" "}
                  <span className="kind-retrieval">{t.retrievals}</span>
                </TableCell>
                <TableCell className="tabular hidden text-right md:table-cell">
                  {fmtCompact(t.tokens_in + t.tokens_out)}
                </TableCell>
                <TableCell className="hidden font-mono text-[13px] text-muted-foreground xl:table-cell">
                  <span className="block truncate">{t.models.join(", ") || "—"}</span>
                </TableCell>
                <TableCell className="tabular text-right text-muted-foreground">
                  {fmtDateTime(t.start_ns)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {traces.data && traces.data.items.length === 0 && (
          <EmptyState
            icon={ListTree}
            title="No traces match"
            description="Widen the time window or clear a filter. New traces appear here live as they are ingested."
            className="m-4"
          />
        )}
        <div className="flex items-center justify-between border-t px-3 py-2 text-sm text-muted-foreground">
          <span>
            Page {page + 1} of {pages}
          </span>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              disabled={page === 0}
              onClick={() => setPage((p) => p - 1)}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              disabled={page + 1 >= pages}
              onClick={() => setPage((p) => p + 1)}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    </>
  );
}
