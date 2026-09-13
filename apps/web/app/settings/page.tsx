"use client";

import { useQuery } from "@tanstack/react-query";
import { api, API_URL, WS_URL } from "@/lib/api";
import { fmtAgo, fmtInt } from "@/lib/format";
import { useLive } from "@/lib/live";
import { PageHeader } from "@/components/shared/page-header";
import { IngestSnippet } from "@/components/settings/ingest-snippet";
import { Card } from "@/components/ui/card";

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[140px_1fr] gap-2 py-1.5 text-sm">
      <div className="text-muted-foreground">{k}</div>
      <div className="min-w-0 break-all font-mono">{v}</div>
    </div>
  );
}

export default function SettingsPage() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 10_000,
    retry: 0,
  });
  const apps = useQuery({ queryKey: ["apps"], queryFn: api.apps });
  const { connected } = useLive();
  const ok = health.isSuccess;

  return (
    <>
      <PageHeader
        title="Settings"
        description="Connection, ingest endpoints and data policy for this Lens instance"
      />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-4">
          <div className="text-[15px] font-medium">API</div>
          <div className="mt-2 divide-y">
            <Row
              k="Status"
              v={
                <span
                  className={
                    ok
                      ? "text-[color:var(--status-good-text)]"
                      : "text-[color:var(--status-critical)]"
                  }
                >
                  {ok ? health.data.status : health.isLoading ? "checking…" : "unreachable"}
                </span>
              }
            />
            <Row k="Endpoint" v={API_URL} />
            <Row k="WebSocket" v={`${WS_URL} · ${connected ? "connected" : "disconnected"}`} />
            <Row k="Version" v={health.data?.version ?? "—"} />
            <Row k="Span store" v={health.data?.span_store ?? "—"} />
            <Row k="OTLP ingest" v={`${API_URL}/v1/traces (JSON, protobuf, gzip)`} />
            <Row k="Collector" v="grpc :4317 · http :4318 (docker compose)" />
            <Row
              k="API docs"
              v={
                <a className="underline" href={`${API_URL}/docs`} target="_blank" rel="noreferrer">
                  {API_URL}/docs
                </a>
              }
            />
          </div>
        </Card>

        <Card className="p-4">
          <div className="text-[15px] font-medium">Data policy</div>
          <div className="mt-2 divide-y">
            <Row k="Attribute cap" v="64 KB per attribute, truncation flagged on the span" />
            <Row k="Unknown attributes" v="never dropped, stored verbatim" />
            <Row
              k="PII redaction"
              v="regex (+ Presidio if installed), per app via LENS_REDACT_APPS"
            />
            <Row k="Retention" v="30 days (ClickHouse TTL on spans)" />
            <Row k="Auth" v="X-Lens-API-Key / Bearer when LENS_API_KEY is set" />
            <Row k="Conventions" v="OTel GenAI · OpenLLMetry · lens.* (SPEC.md §4)" />
          </div>
        </Card>

        <Card className="p-4">
          <div className="text-[15px] font-medium">Instrumented apps</div>
          {apps.data && apps.data.length === 0 && (
            <div className="mt-2 text-sm text-muted-foreground">None yet.</div>
          )}
          <ul className="mt-2 divide-y">
            {apps.data?.map((a) => (
              <li key={a.app} className="flex items-center gap-3 py-1.5 text-sm">
                <span className="font-medium">{a.app}</span>
                <span className="tabular text-muted-foreground">{fmtInt(a.traces)} traces</span>
                <span className="tabular text-muted-foreground">{fmtInt(a.errors)} errors</span>
                <span className="ml-auto text-muted-foreground">{fmtAgo(a.last_seen_ns)}</span>
              </li>
            ))}
          </ul>
        </Card>

        <IngestSnippet />
      </div>
    </>
  );
}
