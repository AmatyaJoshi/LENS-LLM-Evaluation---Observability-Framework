"use client";

import { useMemo } from "react";
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Bot, Database, Flag, MessageSquare, Wrench } from "lucide-react";
import type { Trajectory } from "@/lib/api";
import { fmtInt, fmtMs, truncate } from "@/lib/format";
import { KIND_VAR } from "@/lib/kinds";
import { cn } from "@/lib/utils";

type LensNodeData = {
  kind: "input" | "llm" | "tool" | "retrieval" | "output" | "step";
  title: string;
  subtitle?: string;
  body?: string;
  error?: boolean;
  spanId?: string | null;
};
type LensNode = Node<LensNodeData, "lens">;

const ICON = {
  input: MessageSquare,
  llm: Bot,
  tool: Wrench,
  retrieval: Database,
  output: Flag,
  step: Flag,
} as const;

const COLOR: Record<LensNodeData["kind"], string> = {
  input: "var(--viz-muted)",
  llm: KIND_VAR.llm,
  tool: KIND_VAR.tool,
  retrieval: KIND_VAR.retrieval,
  output: "var(--status-good-text)",
  step: KIND_VAR.agent_step,
};

function LensNodeView({ data, selected }: NodeProps<LensNode>) {
  const Icon = ICON[data.kind];
  return (
    <div
      className={cn(
        "w-[220px] rounded-lg border bg-card text-left shadow-sm transition-shadow",
        selected && "ring-2 ring-primary",
        data.error && "border-[color:var(--status-critical)]",
      )}
      style={{ borderLeft: `3px solid ${COLOR[data.kind]}` }}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!h-2 !w-2 !border-0 !bg-[var(--viz-axis)]"
      />
      <div className="flex items-center gap-2 px-2.5 pt-2 text-sm">
        <Icon className="h-3.5 w-3.5 shrink-0" style={{ color: COLOR[data.kind] }} />
        <span className="truncate font-medium">{data.title}</span>
      </div>
      {data.subtitle && (
        <div className="tabular px-2.5 pt-0.5 text-[12px] text-muted-foreground">
          {data.subtitle}
        </div>
      )}
      {data.body && (
        <div className="px-2.5 pb-2 pt-1 text-[13px] leading-snug text-muted-foreground">
          {truncate(data.body, 110)}
        </div>
      )}
      {!data.body && <div className="pb-2" />}
      <Handle
        type="source"
        position={Position.Right}
        className="!h-2 !w-2 !border-0 !bg-[var(--viz-axis)]"
      />
    </div>
  );
}

const nodeTypes = { lens: LensNodeView };

const COL_W = 270;
const ROW_H = 120;

export function buildGraph(t: Trajectory): { nodes: LensNode[]; edges: Edge[] } {
  const nodes: LensNode[] = [];
  const edges: Edge[] = [];
  let col = 0;
  let prev: string | null = null;
  const link = (from: string | null, to: string, animated = false) => {
    if (from)
      edges.push({ id: `${from}->${to}`, source: from, target: to, animated, type: "smoothstep" });
  };

  nodes.push({
    id: "input",
    type: "lens",
    position: { x: 0, y: ROW_H },
    data: { kind: "input", title: "User input", body: t.user_input ?? "(none)" },
  });
  prev = "input";
  col = 1;

  for (const step of t.steps) {
    const stepPrev = prev;
    const chainInStep: string[] = [];
    // retrievals stack vertically before the llm call
    step.retrievals.forEach((r, i) => {
      const id = `ret-${r.span_id}`;
      nodes.push({
        id,
        type: "lens",
        position: { x: col * COL_W, y: i * ROW_H },
        data: {
          kind: "retrieval",
          title: `retrieve · ${r.documents.length} docs`,
          subtitle: fmtMs(r.duration_ms),
          body: r.query,
          spanId: r.span_id,
        },
      });
      link(stepPrev, id);
      chainInStep.push(id);
    });
    if (step.retrievals.length) col += 1;

    if (step.llm_call) {
      const c = step.llm_call;
      const id = `llm-${c.span_id}`;
      const out =
        c.message_out?.content ??
        (c.tool_calls.length ? `→ ${c.tool_calls.map((x) => x.name).join(", ")}` : "");
      nodes.push({
        id,
        type: "lens",
        position: { x: col * COL_W, y: ROW_H },
        data: {
          kind: "llm",
          title: `${step.name} · ${c.model}`,
          subtitle: `${fmtInt(c.tokens_in)}→${fmtInt(c.tokens_out)} tok · ${fmtMs(c.duration_ms)}`,
          body: out,
          error: !!c.error,
          spanId: c.span_id,
        },
      });
      if (chainInStep.length) chainInStep.forEach((rid) => link(rid, id));
      else link(stepPrev, id);
      prev = id;
      col += 1;
    } else if (chainInStep.length) {
      prev = chainInStep[chainInStep.length - 1]!;
    } else {
      const id = `step-${step.index}`;
      nodes.push({
        id,
        type: "lens",
        position: { x: col * COL_W, y: ROW_H },
        data: { kind: "step", title: step.name, subtitle: "no LLM call", spanId: step.span_id },
      });
      link(stepPrev, id);
      prev = id;
      col += 1;
    }

    step.tool_calls.forEach((tc, i) => {
      const id = `tool-${tc.span_id}`;
      nodes.push({
        id,
        type: "lens",
        position: { x: col * COL_W, y: (i + 1) * ROW_H },
        data: {
          kind: "tool",
          title: tc.name,
          subtitle: fmtMs(tc.duration_ms),
          body: JSON.stringify(tc.args),
          error: !!tc.error,
          spanId: tc.span_id,
        },
      });
      link(prev, id, true);
    });
    if (step.tool_calls.length) {
      // tools feed the next step's LLM call
      const toolIds = step.tool_calls.map((tc) => `tool-${tc.span_id}`);
      prev = toolIds[toolIds.length - 1]!;
      col += 1;
      // connect every tool to whatever comes next by remembering them
      (nodes as unknown as { __pendingTools?: string[] }).__pendingTools = toolIds;
    }
  }

  nodes.push({
    id: "output",
    type: "lens",
    position: { x: col * COL_W, y: ROW_H },
    data: {
      kind: "output",
      title: "Final output",
      subtitle: `${fmtInt(t.total_tokens)} tokens · ${fmtMs(t.duration_ms)}`,
      body: t.final_output ?? "(none)",
      error: t.status === "error",
    },
  });
  link(prev, "output");
  return { nodes, edges };
}

export function TrajectoryGraph({
  trajectory,
  onSelectSpan,
  className,
}: {
  trajectory: Trajectory;
  onSelectSpan?: (spanId: string) => void;
  className?: string;
}) {
  const { nodes, edges } = useMemo(() => buildGraph(trajectory), [trajectory]);
  return (
    <div className={cn("h-[520px] overflow-hidden rounded-lg border bg-card", className)}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2, maxZoom: 1 }}
        minZoom={0.2}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        onNodeClick={(_, n) => {
          const id = (n.data as LensNodeData).spanId;
          if (id && onSelectSpan) onSelectSpan(id);
        }}
      >
        <Background gap={18} size={1} color="var(--viz-grid)" />
        <Controls showInteractive={false} />
        <MiniMap
          pannable
          zoomable
          nodeColor={(n) => COLOR[(n.data as LensNodeData).kind]}
          maskColor="transparent"
        />
      </ReactFlow>
    </div>
  );
}
