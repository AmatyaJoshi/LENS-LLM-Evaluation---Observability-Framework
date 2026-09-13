"use client";

import Link from "next/link";
import { Activity } from "lucide-react";
import { useLive } from "@/lib/live";
import { shortId } from "@/lib/format";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { Button } from "@/components/ui/button";

export default function LivePage() {
  const { connected, events, paused, setPaused } = useLive();
  return (
    <>
      <PageHeader
        title="Live feed"
        description={
          connected
            ? "Streaming ingest events from the API over WebSocket"
            : "Waiting for the API WebSocket…"
        }
        actions={
          <Button
            variant="outline"
            size="sm"
            className="h-8 text-sm"
            onClick={() => setPaused(!paused)}
          >
            {paused ? "Resume" : "Pause"}
          </Button>
        }
      />
      {events.length === 0 ? (
        <EmptyState
          icon={Activity}
          title="No events this session"
          description="Every trace batch the API accepts shows up here within milliseconds. Replay a fixture or send traffic to see it."
        />
      ) : (
        <ul className="divide-y rounded-2xl border border-border/70 bg-card shadow-xs">
          {events.map((e, i) => (
            <li
              key={`${e.trace_id}-${e.received_at}-${i}`}
              className="flex items-center gap-3 px-4 py-2 text-sm"
            >
              <span className="tabular w-20 text-muted-foreground">
                {new Date(e.received_at).toLocaleTimeString(undefined, { hour12: false })}
              </span>
              <span className="rounded-md border px-1.5 py-0.5">{e.app}</span>
              <Link href={`/traces/${e.trace_id}`} className="font-mono hover:underline">
                {shortId(e.trace_id, 16)}
              </Link>
              <span className="tabular ml-auto text-muted-foreground">{e.spans} spans</span>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
