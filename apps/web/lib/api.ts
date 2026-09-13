/**
 * Typed client for the Lens API. Types mirror the Pydantic models in
 * apps/api/lens_api (SPEC.md §3.1) and lens_api/models/clickhouse.py.
 */

export const API_URL = process.env.NEXT_PUBLIC_LENS_API_URL ?? "http://localhost:8000";

export const WS_URL = API_URL.replace(/^http/, "ws") + "/ws/traces";

export type SpanKind =
  "llm" | "tool" | "retrieval" | "agent_step" | "chain" | "embedding" | "other";
export type SpanStatus = "ok" | "error";

export interface SpanEvent {
  name: string;
  time_ns: number;
  attributes: Record<string, unknown>;
}

export interface Span {
  trace_id: string;
  span_id: string;
  parent_span_id: string | null;
  name: string;
  kind: SpanKind;
  start_ns: number;
  end_ns: number;
  status: SpanStatus;
  status_message: string | null;
  attributes: Record<string, unknown>;
  resource: Record<string, unknown>;
  events: SpanEvent[];
  truncated_attributes: string[];
}

export interface ToolCallRequest {
  id: string | null;
  name: string;
  arguments: Record<string, unknown> | string | null;
}

export interface Message {
  role: string;
  content: string | null;
  name: string | null;
  tool_call_id: string | null;
  tool_calls: ToolCallRequest[];
}

export interface LLMCall {
  span_id: string;
  provider: string;
  model: string;
  messages_in: Message[];
  message_out: Message | null;
  tool_calls: ToolCallRequest[];
  tokens_in: number;
  tokens_out: number;
  cost_usd: number | null;
  temperature: number | null;
  prompt_version: string | null;
  finish_reason: string | null;
  error: string | null;
  duration_ms: number;
}

export interface RetrievedDoc {
  text: string;
  id: string | null;
  score: number | null;
  rank: number;
}

export interface Retrieval {
  span_id: string;
  query: string;
  documents: RetrievedDoc[];
  duration_ms: number;
}

export interface ToolCall {
  span_id: string;
  name: string;
  call_id: string | null;
  args: Record<string, unknown>;
  result: unknown;
  error: string | null;
  duration_ms: number;
}

export interface Step {
  index: number;
  name: string;
  span_id: string | null;
  llm_call: LLMCall | null;
  tool_calls: ToolCall[];
  retrievals: Retrieval[];
  start_ns: number;
  end_ns: number;
}

export interface Trajectory {
  trace_id: string;
  app: string;
  run_id: string | null;
  steps: Step[];
  final_output: string | null;
  user_input: string | null;
  total_cost_usd: number;
  total_tokens: number;
  duration_ms: number;
  status: SpanStatus;
  metadata: Record<string, unknown>;
}

export interface TraceSummary {
  trace_id: string;
  app: string;
  root_name: string;
  start_ns: number;
  end_ns: number;
  duration_ms: number;
  span_count: number;
  llm_calls: number;
  tool_calls: number;
  retrievals: number;
  errors: number;
  tokens_in: number;
  tokens_out: number;
  models: string[];
  providers: string[];
  status: SpanStatus;
  input_preview: string | null;
  output_preview: string | null;
  truncated: boolean;
  run_id: string | null;
  session_id: string | null;
}

export interface TracePage {
  items: TraceSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface SeriesPoint {
  t_ns: number;
  traces: number;
  errors: number;
  tokens: number;
  p95_ms: number;
}

export interface ModelUsage {
  model: string;
  provider: string;
  calls: number;
  tokens_in: number;
  tokens_out: number;
}

export interface AppUsage {
  app: string;
  traces: number;
  errors: number;
  last_seen_ns: number;
}

export interface OverviewStats {
  since_ns: number;
  until_ns: number;
  bucket_ns: number;
  traces: number;
  spans: number;
  llm_calls: number;
  tool_calls: number;
  retrievals: number;
  errors: number;
  error_rate: number;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  p50_ms: number;
  p95_ms: number;
  avg_ms: number;
  by_kind: Record<string, number>;
  by_model: ModelUsage[];
  by_app: AppUsage[];
  series: SeriesPoint[];
}

export interface Health {
  status: string;
  version: string;
  span_store: string;
  ws_clients: number;
}

export type Window = "15m" | "1h" | "6h" | "24h" | "7d" | "30d" | "all";
export const WINDOWS: { value: Window; label: string }[] = [
  { value: "15m", label: "Last 15 minutes" },
  { value: "1h", label: "Last hour" },
  { value: "6h", label: "Last 6 hours" },
  { value: "24h", label: "Last 24 hours" },
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
  { value: "all", label: "All time" },
];

export interface TraceQuery {
  app?: string;
  status?: SpanStatus;
  model?: string;
  provider?: string;
  kind?: "llm" | "tool" | "retrieval";
  q?: string;
  since_ns?: number;
  until_ns?: number;
  min_duration_ms?: number;
  max_duration_ms?: number;
  has_tools?: boolean;
  has_retrievals?: boolean;
  limit?: number;
  offset?: number;
  sort?: "start_desc" | "start_asc" | "duration_desc" | "tokens_desc";
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

function qs(params: object): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params as Record<string, unknown>)) {
    if (v === undefined || v === null || v === "") continue;
    sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

async function get<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { ...init, cache: "no-store" });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => get<Health>("/health"),
  apps: () => get<AppUsage[]>("/apps"),
  overview: (params: { app?: string; window: Window; buckets?: number }) =>
    get<OverviewStats>(`/stats/overview${qs(params)}`),
  traces: (params: TraceQuery) => get<TracePage>(`/traces${qs(params)}`),
  trace: (traceId: string) => get<Span[]>(`/traces/${traceId}`),
  trajectory: (traceId: string) => get<Trajectory>(`/traces/${traceId}/trajectory`),
  // later-phase resources (return [] until their phase lands)
  datasets: () => get<unknown[]>("/datasets"),
  evals: () => get<unknown[]>("/evals"),
  redteam: () => get<unknown[]>("/redteam"),
  labels: () => get<unknown[]>("/labels"),
};

export function windowToSinceNs(w: Window, now = Date.now()): number | undefined {
  const ms: Record<Window, number> = {
    "15m": 15 * 60e3,
    "1h": 3600e3,
    "6h": 6 * 3600e3,
    "24h": 24 * 3600e3,
    "7d": 7 * 24 * 3600e3,
    "30d": 30 * 24 * 3600e3,
    all: 0,
  };
  return ms[w] ? (now - ms[w]) * 1e6 : undefined;
}
