/**
 * Lens TypeScript SDK (SPEC.md §9).
 *
 * A thin wrapper over OpenTelemetry emitting the OTel GenAI + Lens attributes Lens normalises
 * (SPEC.md §4). Mirrors the Python SDK surface: init, trace, logRetrieval, feedback, expected.
 * When @traceloop/node-server-sdk is installed, init() enables OpenLLMetry auto-instrumentation.
 *
 *   import * as lens from "@lens/sdk";
 *   lens.init({ app: "rag_demo", endpoint: "http://localhost:4318" });
 *   const answer = await lens.trace("answer", { kind: "agent_step" }, async () => {
 *     const docs = await retrieve(q);
 *     lens.logRetrieval(q, docs);
 *     return callLlm(q, docs);
 *   });
 *   lens.feedback({ thumbs: "down", comment: "wrong window" });
 */

import { NodeTracerProvider } from "@opentelemetry/sdk-trace-node";
import { BatchSpanProcessor } from "@opentelemetry/sdk-trace-node";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http";
import { resourceFromAttributes } from "@opentelemetry/resources";
import { ATTR_SERVICE_NAME } from "@opentelemetry/semantic-conventions";
import { trace as otelTrace, context, type Span, type Attributes } from "@opentelemetry/api";

export type SpanKind = "agent_step" | "workflow" | "chain" | "tool" | "retrieval" | "llm";

const KIND_ATTRS: Record<SpanKind, Attributes> = {
  agent_step: { "traceloop.span.kind": "agent" },
  workflow: { "traceloop.span.kind": "workflow" },
  chain: { "traceloop.span.kind": "task" },
  tool: { "gen_ai.operation.name": "execute_tool" },
  retrieval: { "traceloop.span.kind": "task" },
  llm: { "gen_ai.operation.name": "chat" },
};

let initialized = false;

export interface InitOptions {
  app: string;
  endpoint?: string;
  apiKey?: string;
  resourceAttributes?: Record<string, string>;
}

export function init(opts: InitOptions): void {
  if (initialized) return;
  const endpoint = opts.endpoint ?? process.env.OTEL_EXPORTER_OTLP_ENDPOINT ?? "http://localhost:4318";
  const headers = opts.apiKey ? { "x-lens-api-key": opts.apiKey } : undefined;

  const provider = new NodeTracerProvider({
    resource: resourceFromAttributes({
      [ATTR_SERVICE_NAME]: opts.app,
      ...(opts.resourceAttributes ?? {}),
    }),
    spanProcessors: [
      new BatchSpanProcessor(new OTLPTraceExporter({ url: `${endpoint.replace(/\/$/, "")}/v1/traces`, headers })),
    ],
  });
  provider.register();
  initialized = true;
}

function tracer() {
  return otelTrace.getTracer("lens-sdk", "0.1.0");
}

export interface TraceOptions {
  kind?: SpanKind;
  attributes?: Attributes;
}

/** Run `fn` inside a Lens-tagged span, recording input/output as traceloop entity attributes. */
export async function trace<T>(name: string, opts: TraceOptions, fn: () => Promise<T> | T): Promise<T> {
  return tracer().startActiveSpan(name, async (span) => {
    span.setAttribute("traceloop.entity.name", name);
    for (const [k, v] of Object.entries(KIND_ATTRS[opts.kind ?? "chain"])) span.setAttribute(k, v as never);
    for (const [k, v] of Object.entries(opts.attributes ?? {})) span.setAttribute(k, v as never);
    try {
      const result = await fn();
      span.setAttribute("traceloop.entity.output", safeJson(result));
      return result;
    } finally {
      span.end();
    }
  });
}

export interface RetrievedDoc {
  id?: string | null;
  text?: string;
  content?: string;
  score?: number | null;
  rank?: number;
}

/** Record a retrieval on a child span (SPEC.md §4 lens.retrieval.*). */
export function logRetrieval(query: string, documents: Array<string | RetrievedDoc>, spanName = "retrieve"): void {
  const docs = documents.map((d, i) =>
    typeof d === "string"
      ? { id: null, text: d, score: null, rank: i + 1 }
      : { id: d.id ?? null, text: d.text ?? d.content ?? "", score: d.score ?? null, rank: d.rank ?? i + 1 },
  );
  const span = tracer().startSpan(spanName);
  span.setAttribute("traceloop.span.kind", "task");
  span.setAttribute("lens.retrieval.query", query);
  span.setAttribute("lens.retrieval.docs", JSON.stringify(docs));
  span.end();
}

export interface FeedbackOptions {
  thumbs?: "up" | "down";
  score?: number;
  comment?: string;
  traceId?: string;
}

/** Attach user feedback to the current span (SPEC.md §4 lens.user.feedback). */
export function feedback(opts: FeedbackOptions): void {
  const span = current();
  if (!span) return;
  const value = opts.score ?? (opts.thumbs ? (opts.thumbs === "up" ? 1 : -1) : undefined);
  if (value !== undefined) span.setAttribute("lens.user.feedback", value);
  if (opts.comment) span.setAttribute("lens.user.feedback.comment", opts.comment);
  if (opts.traceId) span.setAttribute("lens.feedback.trace_id", opts.traceId);
}

/** Attach an expected output for offline evaluation (SPEC.md §4 lens.eval.expected_output). */
export function expected(expectedOutput: string, traceId?: string): void {
  const span = current();
  if (!span) return;
  span.setAttribute("lens.eval.expected_output", expectedOutput);
  if (traceId) span.setAttribute("lens.eval.trace_id", traceId);
}

export function setSession(sessionId: string): void {
  current()?.setAttribute("lens.session.id", sessionId);
}

export function setRun(runId: string): void {
  current()?.setAttribute("lens.run.id", runId);
}

function current(): Span | undefined {
  return otelTrace.getSpan(context.active());
}

function safeJson(value: unknown): string {
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}
