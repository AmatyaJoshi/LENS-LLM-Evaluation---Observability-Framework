import { LENS_API_INTERNAL_URL, LENS_API_URL } from "@/lib/utils";

type Health = {
  status: string;
  version: string;
  span_store: string;
  ws_clients: number;
};

async function fetchHealth(): Promise<Health | null> {
  try {
    const res = await fetch(`${LENS_API_INTERNAL_URL}/health`, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as Health;
  } catch {
    return null;
  }
}

export const dynamic = "force-dynamic";

export default async function Home() {
  const health = await fetchHealth();
  return (
    <div className="max-w-2xl">
      <h1 className="text-xl font-semibold tracking-tight">Lens</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        LLM evaluation &amp; observability. Phase 1: ingest and normalise.
      </p>

      <section className="mt-8 rounded-lg border bg-card p-4">
        <h2 className="text-sm font-medium">API</h2>
        <dl className="mt-3 grid grid-cols-[8rem_1fr] gap-y-1 font-mono text-xs">
          <dt className="text-muted-foreground">endpoint</dt>
          <dd>{LENS_API_URL}</dd>
          <dt className="text-muted-foreground">status</dt>
          <dd className={health ? "text-emerald-400" : "text-destructive"}>
            {health ? health.status : "unreachable"}
          </dd>
          {health && (
            <>
              <dt className="text-muted-foreground">version</dt>
              <dd>{health.version}</dd>
              <dt className="text-muted-foreground">span store</dt>
              <dd>{health.span_store}</dd>
              <dt className="text-muted-foreground">ws clients</dt>
              <dd>{health.ws_clients}</dd>
            </>
          )}
        </dl>
      </section>

      <section className="mt-6 text-sm text-muted-foreground">
        <p>
          Send OTLP traces to <code className="font-mono">localhost:4318</code> (collector) or{" "}
          <code className="font-mono">{LENS_API_URL}/v1/traces</code> (direct). Trace pages arrive
          in phase 2.
        </p>
      </section>
    </div>
  );
}
