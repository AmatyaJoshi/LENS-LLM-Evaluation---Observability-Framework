"use client";

import { Bot, User, Wrench, Settings2 } from "lucide-react";
import type { LLMCall, Message, Trajectory } from "@/lib/api";
import { fmtInt, fmtMs, stringify } from "@/lib/format";
import { cn } from "@/lib/utils";
import { EmptyState } from "@/components/shared/empty-state";

function RoleIcon({ role }: { role: string }) {
  const cls = "h-3.5 w-3.5";
  if (role === "user") return <User className={cls} />;
  if (role === "assistant") return <Bot className={cls} />;
  if (role === "tool") return <Wrench className={cls} />;
  return <Settings2 className={cls} />;
}

function MessageBubble({ m, dim }: { m: Message; dim?: boolean }) {
  const isAssistant = m.role === "assistant";
  return (
    <div className={cn("flex gap-2.5", dim && "opacity-60")}>
      <div
        className={cn(
          "mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md border",
          isAssistant ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground",
        )}
      >
        <RoleIcon role={m.role} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="mb-0.5 flex items-center gap-2 text-[13px] text-muted-foreground">
          <span className="font-medium capitalize text-foreground">{m.role}</span>
          {m.name && <span className="font-mono">{m.name}</span>}
          {m.tool_call_id && <span className="font-mono">↩ {m.tool_call_id}</span>}
        </div>
        {m.content && (
          <pre className="whitespace-pre-wrap break-words rounded-md border bg-card px-3 py-2 font-sans text-[15px] leading-relaxed">
            {m.content}
          </pre>
        )}
        {m.tool_calls.length > 0 && (
          <div className="mt-1.5 space-y-1">
            {m.tool_calls.map((tc, i) => (
              <div key={i} className="rounded-md border border-dashed px-3 py-2 text-sm">
                <div className="flex items-center gap-2">
                  <Wrench className="kind-tool h-3.5 w-3.5" />
                  <span className="font-mono font-medium">{tc.name}</span>
                  {tc.id && <span className="font-mono text-muted-foreground">{tc.id}</span>}
                </div>
                {tc.arguments != null && (
                  <pre className="scrollbar-thin mt-1 overflow-x-auto font-mono text-[13px] text-muted-foreground">
                    {stringify(tc.arguments)}
                  </pre>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function CallHeader({ call, index }: { call: LLMCall; index: number }) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <span className="rounded-md bg-muted px-1.5 py-0.5 font-medium">LLM call {index + 1}</span>
      <span className="font-mono">{call.model}</span>
      <span className="text-muted-foreground">{call.provider}</span>
      <span className="tabular text-muted-foreground">
        {fmtInt(call.tokens_in)} in · {fmtInt(call.tokens_out)} out · {fmtMs(call.duration_ms)}
      </span>
      {call.finish_reason && (
        <span className="rounded border px-1 font-mono text-[12px]">{call.finish_reason}</span>
      )}
      {call.temperature != null && (
        <span className="font-mono text-[12px] text-muted-foreground">T={call.temperature}</span>
      )}
      {call.error && <span className="text-[color:var(--status-critical)]">{call.error}</span>}
    </div>
  );
}

/**
 * Renders the trajectory as a conversation. Consecutive LLM calls usually
 * re-send the growing message list; messages already shown by an earlier call
 * are dimmed so the new turn stands out.
 */
export function Conversation({ trajectory }: { trajectory: Trajectory }) {
  const calls = trajectory.steps.map((s) => s.llm_call).filter((c): c is LLMCall => c != null);
  if (calls.length === 0) {
    return (
      <EmptyState
        title="No LLM calls in this trace"
        description="Only tool, retrieval or chain spans were recorded."
      />
    );
  }
  const seen = new Set<string>();
  return (
    <div className="space-y-6">
      {calls.map((call, i) => (
        <section key={call.span_id} className="space-y-3">
          <CallHeader call={call} index={i} />
          <div className="space-y-3 border-l-2 pl-4">
            {call.messages_in.map((m, j) => {
              const key = `${m.role}|${m.content ?? ""}|${JSON.stringify(m.tool_calls)}|${m.tool_call_id ?? ""}`;
              const dup = seen.has(key);
              seen.add(key);
              return <MessageBubble key={j} m={m} dim={dup} />;
            })}
            {call.message_out ? (
              <div className="rounded-lg border border-primary/30 bg-primary/5 p-3">
                <MessageBubble m={call.message_out} />
              </div>
            ) : (
              <div className="text-sm text-muted-foreground">No completion recorded.</div>
            )}
          </div>
        </section>
      ))}
    </div>
  );
}
