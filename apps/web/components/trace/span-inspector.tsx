"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";
import type { Span } from "@/lib/api";
import { fmtMs, fmtDateTime, stringify } from "@/lib/format";
import { KindBadge, StatusBadge } from "@/components/shared/badges";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

function KV({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data).sort(([a], [b]) => a.localeCompare(b));
  if (entries.length === 0)
    return <div className="px-3 py-4 text-sm text-muted-foreground">None</div>;
  return (
    <table className="w-full table-fixed text-sm">
      <tbody>
        {entries.map(([k, v]) => {
          const text = stringify(v, false);
          const long = text.length > 160;
          return (
            <tr key={k} className="border-b align-top last:border-0">
              <td className="w-[42%] break-all py-1.5 pl-3 pr-2 font-mono text-[13px] text-muted-foreground">
                {k}
              </td>
              <td className="py-1.5 pr-3">
                <pre
                  className={
                    long
                      ? "scrollbar-thin max-h-40 overflow-auto whitespace-pre-wrap break-words font-mono text-[13px]"
                      : "whitespace-pre-wrap break-words font-mono text-[13px]"
                  }
                >
                  {long ? stringify(v, true) : text}
                </pre>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export function SpanInspector({ span }: { span: Span | null }) {
  const [copied, setCopied] = useState(false);
  if (!span) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-center text-sm text-muted-foreground">
        Select a span in the waterfall to inspect its attributes and events.
      </div>
    );
  }
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(span, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore */
    }
  };
  return (
    <div className="flex h-full flex-col">
      <div className="border-b px-3 py-2.5">
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0 truncate text-[15px] font-medium">{span.name}</div>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 shrink-0"
            onClick={copy}
            aria-label="Copy span JSON"
          >
            {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          </Button>
        </div>
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          <KindBadge kind={span.kind} />
          <StatusBadge status={span.status} />
          <span className="tabular rounded-md border px-1.5 py-0.5 text-[13px]">
            {fmtMs((span.end_ns - span.start_ns) / 1e6)}
          </span>
        </div>
        <dl className="mt-2 grid grid-cols-[70px_1fr] gap-y-0.5 font-mono text-[12px] text-muted-foreground">
          <dt>span</dt>
          <dd className="truncate text-foreground">{span.span_id}</dd>
          <dt>parent</dt>
          <dd className="truncate text-foreground">{span.parent_span_id ?? "—"}</dd>
          <dt>start</dt>
          <dd className="text-foreground">{fmtDateTime(span.start_ns)}</dd>
          {span.status_message && (
            <>
              <dt>message</dt>
              <dd className="text-[color:var(--status-critical)]">{span.status_message}</dd>
            </>
          )}
        </dl>
        {span.truncated_attributes.length > 0 && (
          <div className="border-[color:var(--status-warning)]/40 mt-2 rounded-md border px-2 py-1 text-[13px]">
            Truncated at 64 KB: {span.truncated_attributes.join(", ")}
          </div>
        )}
      </div>
      <Tabs defaultValue="attributes" className="flex min-h-0 flex-1 flex-col">
        <TabsList className="mx-3 mt-2 h-8 w-fit">
          <TabsTrigger value="attributes" className="h-6 text-sm">
            Attributes{" "}
            <span className="tabular ml-1 text-muted-foreground">
              {Object.keys(span.attributes).length}
            </span>
          </TabsTrigger>
          <TabsTrigger value="events" className="h-6 text-sm">
            Events <span className="tabular ml-1 text-muted-foreground">{span.events.length}</span>
          </TabsTrigger>
          <TabsTrigger value="resource" className="h-6 text-sm">
            Resource
          </TabsTrigger>
        </TabsList>
        <ScrollArea className="min-h-0 flex-1">
          <TabsContent value="attributes" className="mt-1">
            <KV data={span.attributes} />
          </TabsContent>
          <TabsContent value="events" className="mt-1">
            {span.events.length === 0 ? (
              <div className="px-3 py-4 text-sm text-muted-foreground">No events</div>
            ) : (
              span.events.map((e, i) => (
                <div key={i} className="border-b last:border-0">
                  <div className="flex items-center justify-between px-3 pt-2 text-sm">
                    <span className="font-medium">{e.name}</span>
                    <span className="tabular text-muted-foreground">
                      +{fmtMs((e.time_ns - span.start_ns) / 1e6)}
                    </span>
                  </div>
                  <KV data={e.attributes} />
                </div>
              ))
            )}
          </TabsContent>
          <TabsContent value="resource" className="mt-1">
            <KV data={span.resource} />
          </TabsContent>
        </ScrollArea>
      </Tabs>
    </div>
  );
}
