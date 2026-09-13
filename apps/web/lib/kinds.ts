import type { SpanKind } from "@/lib/api";

/** Fixed categorical slot per span kind (never cycled). */
export const KIND_ORDER: SpanKind[] = [
  "llm",
  "tool",
  "retrieval",
  "chain",
  "embedding",
  "agent_step",
  "other",
];

export const KIND_LABEL: Record<SpanKind, string> = {
  llm: "LLM call",
  tool: "Tool",
  retrieval: "Retrieval",
  agent_step: "Agent step",
  chain: "Chain",
  embedding: "Embedding",
  other: "Other",
};

export const KIND_VAR: Record<SpanKind, string> = {
  llm: "var(--series-1)",
  tool: "var(--series-2)",
  retrieval: "var(--series-3)",
  chain: "var(--series-4)",
  embedding: "var(--series-5)",
  agent_step: "var(--series-7)",
  other: "var(--viz-muted)",
};

export function kindOf(k: string): SpanKind {
  return (KIND_ORDER as string[]).includes(k) ? (k as SpanKind) : "other";
}
