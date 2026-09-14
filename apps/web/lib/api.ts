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

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const b = (await res.json()) as { detail?: string };
      if (b.detail) detail = b.detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

// ---- eval / judge / label / redteam / assistant types --------------------------------------

export interface MetricSpec {
  name: string;
  version: string;
  requires: string[];
  higher_is_better: boolean;
  description: string;
}

export interface EvalRun {
  id: string;
  app: string;
  dataset_id: string | null;
  dataset_name: string | null;
  git_sha: string | null;
  mode: string;
  judge_tier: string | null;
  judge_model: string | null;
  started_at: string;
  finished_at: string | null;
  metrics: Record<string, number>;
  n_scores: number;
  n_items: number;
  cost_usd: number;
  errors: number;
}

export interface RunDetail extends EvalRun {
  items: Array<{
    trace_id: string | null;
    example_id: string | null;
    input?: string;
    output?: string;
    expected_output?: string;
    scores: Record<
      string,
      {
        value: number;
        rationale: string | null;
        skipped: boolean;
        error: string | null;
        judge_model: string | null;
      }
    >;
  }>;
  distributions: Record<string, number[]>;
}

export interface TrendPoint {
  run_id: string;
  git_sha: string | null;
  started_at: string;
  mean: number;
  n: number;
}

export interface DatasetOut {
  id: string;
  name: string;
  description: string | null;
  split_strategy: string;
  created_at: string;
  example_count: number;
  splits: Record<string, number>;
}

export interface AgreementReport {
  metric: string;
  judge: string;
  reference: string;
  n: number;
  cohen_kappa: number;
  krippendorff_alpha: number;
  spearman_rho: number;
  mean_abs_error: number;
}

export interface JudgeCost {
  judge_model: string;
  metric: string;
  n: number;
  cost_per_1k_usd: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
}

export interface SimilarTrace {
  trace_id: string;
  app: string;
  root_name: string;
  status: SpanStatus;
  input_preview: string | null;
  duration_ms: number;
  similarity: number;
}

export interface JudgeQuality {
  vs_human: AgreementReport[];
  between_judges: AgreementReport[];
  inter_annotator: AgreementReport[];
  costs: JudgeCost[];
  judges: string[];
  metrics: string[];
  human_labels: number;
}

export interface QueueItem {
  trace_id: string | null;
  example_id: string | null;
  metric: string;
  priority: number;
  judge_scores: Array<{ judge_model: string; value: number; rationale: string | null }>;
  human_labels: number;
  input: string | null;
  output: string | null;
  contexts: string[];
}

export interface ProbeCatalogue {
  total: number;
  by_category: Record<string, number>;
  categories: string[];
  mutators: string[];
}

export interface RedteamRun {
  id: string;
  app: string;
  target: string;
  git_sha: string | null;
  defence: string | null;
  total_probes: number;
  successes: number;
  asr: number;
  detector_caught: number;
  detector_caught_rate: number;
  started_at: string;
  finished_at: string | null;
}

export interface ProbeResultOut {
  id: string;
  probe_id: string;
  parent_probe_id: string | null;
  category: string;
  tactic: string | null;
  mutator: string | null;
  response: string | null;
  success: boolean;
  success_reason: string | null;
  detector_score: number | null;
  detector_flagged: boolean;
  trace_id: string | null;
}

export interface AsrPoint {
  run_id: string;
  git_sha: string | null;
  defence: string | null;
  started_at: string;
  total: number;
  successes: number;
  asr: number;
}

export interface FlaggedTrace {
  trace_id: string;
  app: string;
  start_ns: number;
  flagged_spans: Array<{
    span_id: string;
    kind: string;
    score: number | null;
    reasons: string | null;
  }>;
  max_score: number;
}

export type AssistantFocus = "overview" | "trace" | "eval_run" | "redteam_run";

export interface ChatResponse {
  answer: string;
  grounded: boolean;
  model: string | null;
  context_summary: Record<string, unknown>;
  cost_usd: number;
  suggestions: string[];
}

export const api = {
  health: () => get<Health>("/health"),
  apps: () => get<AppUsage[]>("/apps"),
  overview: (params: { app?: string; window: Window; buckets?: number }) =>
    get<OverviewStats>(`/stats/overview${qs(params)}`),
  traces: (params: TraceQuery) => get<TracePage>(`/traces${qs(params)}`),
  trace: (traceId: string) => get<Span[]>(`/traces/${traceId}`),
  trajectory: (traceId: string) => get<Trajectory>(`/traces/${traceId}/trajectory`),
  similar: (traceId: string) => get<SimilarTrace[]>(`/traces/${traceId}/similar`),

  metrics: () => get<MetricSpec[]>("/metrics"),
  evalRuns: (params: { app?: string; mode?: string; limit?: number } = {}) =>
    get<EvalRun[]>(`/evals/runs${qs(params)}`),
  evalRun: (id: string) => get<RunDetail>(`/evals/runs/${id}`),
  evalCompare: (a: string, b: string) =>
    get<{ a: EvalRun; b: EvalRun; deltas: Record<string, number> }>(
      `/evals/compare${qs({ a, b })}`,
    ),
  evalTrends: (params: { metric: string; app?: string }) =>
    get<TrendPoint[]>(`/evals/trends${qs(params)}`),
  traceScores: (traceId: string) =>
    get<
      Array<{
        metric: string;
        value: number;
        rationale: string | null;
        judge_model: string | null;
        sub_scores: Record<string, number> | null;
      }>
    >(`/evals/traces/${traceId}/scores`),
  evaluateTrace: (trace_id: string, metrics?: string[]) =>
    post<{ status: string }>("/evals/evaluate", { trace_id, metrics }),

  datasets: () => get<DatasetOut[]>("/datasets"),
  createDataset: (body: { name: string; description?: string; split_strategy?: string }) =>
    post<DatasetOut>("/datasets", body),
  datasetExamples: (id: string, params: { limit?: number } = {}) =>
    get<{ items: Array<Record<string, unknown>>; total: number }>(
      `/datasets/${id}/examples${qs(params)}`,
    ),
  promoteTraces: (id: string, trace_ids: string[]) =>
    post(`/datasets/${id}/promote`, { trace_ids }),

  judgeQuality: (metric?: string) => get<JudgeQuality>(`/judges/quality${qs({ metric })}`),
  judgePrompts: () =>
    get<Array<{ name: string; version: string; variables: string[] }>>("/judges/prompts"),

  labels: (params: Record<string, unknown> = {}) => get<unknown[]>(`/labels${qs(params)}`),
  labelQueue: (params: { metric: string; labeller?: string; limit?: number }) =>
    get<QueueItem[]>(`/labels/queue${qs(params)}`),
  createLabel: (body: {
    trace_id?: string | null;
    example_id?: string | null;
    metric: string;
    value: number;
    labeller: string;
  }) => post("/labels", body),

  probes: () => get<ProbeCatalogue>("/redteam/probes"),
  redteamRuns: (params: { app?: string } = {}) => get<RedteamRun[]>(`/redteam/runs${qs(params)}`),
  redteamResults: (id: string, params: { success?: boolean; category?: string } = {}) =>
    get<ProbeResultOut[]>(`/redteam/runs/${id}/results${qs(params)}`),
  redteamAsr: (params: { app: string; category?: string }) =>
    get<AsrPoint[]>(`/redteam/asr${qs(params)}`),
  flaggedTraffic: (params: { app?: string } = {}) =>
    get<FlaggedTrace[]>(`/redteam/flagged${qs(params)}`),

  assistantCapabilities: () =>
    get<{ grounded_answers: boolean; focuses: string[]; note: string }>("/assistant/capabilities"),
  assistantChat: (body: {
    messages: Array<{ role: "user" | "assistant"; content: string }>;
    focus?: AssistantFocus;
    trace_id?: string | null;
    run_id?: string | null;
    app?: string | null;
  }) => post<ChatResponse>("/assistant/chat", body),
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
