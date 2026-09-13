"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { API_URL } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

const COLLECTOR = API_URL.replace(":8000", ":4318");

const SNIPPETS: Record<string, { label: string; code: string }> = {
  env: {
    label: "Any OTel app",
    code: `# OpenLLMetry / OpenTelemetry SDKs read these automatically
export OTEL_EXPORTER_OTLP_ENDPOINT=${COLLECTOR}
export OTEL_SERVICE_NAME=my-agent          # becomes the Lens "app"
export TRACELOOP_BASE_URL=${COLLECTOR}      # if you use Traceloop.init()`,
  },
  python: {
    label: "Python",
    code: `from traceloop.sdk import Traceloop
from traceloop.sdk.decorators import workflow, tool

Traceloop.init(app_name="my-agent", api_endpoint="${COLLECTOR}")

@workflow(name="answer")
def answer(question: str) -> str:
    docs = retrieve(question)          # set lens.retrieval.query / lens.retrieval.docs
    return llm(question, docs)         # any OpenAI/Anthropic call is captured`,
  },
  ts: {
    label: "TypeScript",
    code: `import * as traceloop from "@traceloop/node-server-sdk";

traceloop.initialize({
  appName: "my-agent",
  baseUrl: "${COLLECTOR}",
  disableBatch: true,
});`,
  },
  replay: {
    label: "Replay fixture",
    code: `# from the Lens repo root: sends a recorded run straight to the API
uv run lens ingest tests/fixtures/otlp/openllmetry_python.json --endpoint ${API_URL}`,
  },
};

export function IngestSnippet({ compact, className }: { compact?: boolean; className?: string }) {
  const [copied, setCopied] = useState<string | null>(null);
  const copy = async (key: string) => {
    try {
      await navigator.clipboard.writeText(SNIPPETS[key]!.code);
      setCopied(key);
      setTimeout(() => setCopied(null), 1500);
    } catch {
      /* clipboard unavailable */
    }
  };
  return (
    <div className={cn("rounded-lg border bg-card", className)}>
      <div className="px-4 pt-3">
        <div className="text-[15px] font-medium">Connect an app</div>
        <div className="text-[13px] text-muted-foreground">
          Lens speaks OTLP. Anything instrumented with OpenLLMetry or the OTel GenAI conventions
          works unchanged.
        </div>
      </div>
      <Tabs defaultValue="env" className="mt-2">
        <TabsList className="mx-4 h-8">
          {Object.entries(SNIPPETS).map(([k, v]) => (
            <TabsTrigger key={k} value={k} className="h-6 text-sm">
              {v.label}
            </TabsTrigger>
          ))}
        </TabsList>
        {Object.entries(SNIPPETS).map(([k, v]) => (
          <TabsContent key={k} value={k} className="relative mt-2 px-4 pb-4">
            <pre
              className={cn(
                "scrollbar-thin overflow-x-auto rounded-md border bg-muted/50 p-3 font-mono text-[13px] leading-relaxed",
                compact ? "max-h-[220px]" : "",
              )}
            >
              {v.code}
            </pre>
            <Button
              variant="ghost"
              size="icon"
              className="absolute right-6 top-2 h-7 w-7"
              onClick={() => copy(k)}
              aria-label="Copy"
            >
              {copied === k ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            </Button>
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}
