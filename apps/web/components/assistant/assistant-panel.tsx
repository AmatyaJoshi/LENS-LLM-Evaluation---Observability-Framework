"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Bot, Send, X } from "lucide-react";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, type AssistantFocus, type ChatResponse } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface Turn {
  role: "user" | "assistant";
  content: string;
  grounded?: boolean;
  model?: string | null;
}

function useFocus(): { focus: AssistantFocus; trace_id?: string; run_id?: string; app?: string } {
  const pathname = usePathname();
  const sp = useSearchParams();
  const app = sp.get("app") ?? undefined;
  const traceMatch = pathname.match(/^\/traces\/([^/]+)/);
  if (traceMatch) return { focus: "trace", trace_id: traceMatch[1], app };
  const runMatch = pathname.match(/^\/evaluations\/([^/]+)/);
  if (runMatch) return { focus: "eval_run", run_id: runMatch[1], app };
  if (pathname.startsWith("/redteam")) return { focus: "redteam_run", app };
  return { focus: "overview", app };
}

const FOCUS_LABEL: Record<AssistantFocus, string> = {
  overview: "your traffic overview",
  trace: "this trace",
  eval_run: "this evaluation run",
  redteam_run: "your red-team runs",
};

export function AssistantPanel() {
  const [open, setOpen] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const focus = useFocus();
  const scrollRef = useRef<HTMLDivElement>(null);
  const caps = useQuery({
    queryKey: ["assistant-caps"],
    queryFn: api.assistantCapabilities,
    enabled: open,
    retry: 0,
  });

  useEffect(() => {
    const onOpen = () => setOpen(true);
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === "j" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    document.addEventListener("lens:assistant", onOpen);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("lens:assistant", onOpen);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  const chat = useMutation({
    mutationFn: (question: string) => {
      const history: Turn[] = [...turns, { role: "user", content: question }];
      return api.assistantChat({
        messages: history.map((t) => ({ role: t.role, content: t.content })),
        focus: focus.focus,
        trace_id: focus.trace_id ?? null,
        run_id: focus.run_id ?? null,
        app: focus.app ?? null,
      });
    },
    onSuccess: (res: ChatResponse) => {
      setTurns((t) => [
        ...t,
        { role: "assistant", content: res.answer, grounded: res.grounded, model: res.model },
      ]);
    },
    onError: (err: Error) => {
      setTurns((t) => [...t, { role: "assistant", content: `Error: ${err.message}` }]);
    },
  });

  const send = (question: string) => {
    const q = question.trim();
    if (!q || chat.isPending) return;
    setTurns((t) => [...t, { role: "user", content: q }]);
    setInput("");
    chat.mutate(q);
  };

  const suggestions =
    focus.focus === "trace"
      ? ["Why did this trace get its scores?", "Is this trace safe from prompt injection?"]
      : focus.focus === "redteam_run"
        ? ["Which attack category has the highest ASR?", "Did the last defence reduce ASR?"]
        : [
            "What is driving my error rate?",
            "Which model uses the most tokens?",
            "Summarise the latest red-team run",
          ];

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-50 flex justify-end bg-black/30 backdrop-blur-sm duration-200 animate-in fade-in"
          onClick={() => setOpen(false)}
        >
          <aside
            className="flex h-full w-full max-w-md flex-col border-l border-border/80 bg-card/95 shadow-pop backdrop-blur-xl duration-300 animate-in slide-in-from-right"
            onClick={(e) => e.stopPropagation()}
          >
            <header className="flex items-center gap-2 border-b px-4 py-3">
              <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
                <Bot className="h-4 w-4" />
              </div>
              <div className="flex-1">
                <div className="text-sm font-semibold">Lens Assistant</div>
                <div className="text-xs text-muted-foreground">
                  Answering about {FOCUS_LABEL[focus.focus]}
                </div>
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={() => setOpen(false)}
              >
                <X className="h-4 w-4" />
              </Button>
            </header>

            {caps.data && !caps.data.grounded_answers && (
              <div className="bg-[color:var(--status-warning)]/10 border-b px-4 py-2 text-xs text-muted-foreground">
                No LLM key configured. Answers return the raw Lens data used to ground them. Set{" "}
                <code className="font-mono">ANTHROPIC_API_KEY</code> on the API for natural-language
                answers.
              </div>
            )}

            <div ref={scrollRef} className="scrollbar-thin flex-1 space-y-4 overflow-y-auto p-4">
              {turns.length === 0 && (
                <div className="space-y-3">
                  <p className="text-sm text-muted-foreground">
                    I answer from your own Lens data: traces, evaluation scores, judge quality and
                    red-team results. I cite what I use and never invent numbers.
                  </p>
                  <div className="space-y-1.5">
                    {suggestions.map((s) => (
                      <button
                        key={s}
                        onClick={() => send(s)}
                        className="block w-full rounded-md border px-3 py-2 text-left text-sm hover:bg-accent"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {turns.map((t, i) => (
                <div
                  key={i}
                  className={cn("flex gap-2.5", t.role === "user" && "flex-row-reverse")}
                >
                  <div
                    className={cn(
                      "mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md",
                      t.role === "assistant"
                        ? "bg-primary/10 text-primary"
                        : "bg-muted text-muted-foreground",
                    )}
                  >
                    {t.role === "assistant" ? <Bot className="h-3.5 w-3.5" /> : "You"}
                  </div>
                  <div
                    className={cn(
                      "max-w-[85%] whitespace-pre-wrap rounded-lg border px-3 py-2 text-sm leading-relaxed",
                      t.role === "user" ? "bg-primary/5" : "bg-background",
                    )}
                  >
                    {t.content}
                    {t.role === "assistant" && t.grounded === false && (
                      <div className="mt-1 text-[10px] text-muted-foreground">
                        raw data (no LLM key)
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {chat.isPending && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Bot className="h-3.5 w-3.5 animate-pulse" /> thinking…
                </div>
              )}
            </div>

            <div className="border-t p-3">
              <div className="flex items-end gap-2">
                <Textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      send(input);
                    }
                  }}
                  placeholder="Ask about your traces, scores, or attacks…"
                  className="max-h-32 min-h-[40px] resize-none text-sm"
                  rows={1}
                />
                <Button
                  size="icon"
                  className="h-10 w-10 shrink-0"
                  disabled={chat.isPending}
                  onClick={() => send(input)}
                >
                  <Send className="h-4 w-4" />
                </Button>
              </div>
              <div className="mt-1.5 text-[10px] text-muted-foreground">
                Grounded in your Lens data ·{" "}
                <kbd className="rounded border bg-muted px-1 font-mono">⌘J</kbd> to toggle
              </div>
            </div>
          </aside>
        </div>
      )}
    </>
  );
}
