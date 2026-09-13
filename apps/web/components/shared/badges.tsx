import { AlertCircle, CheckCircle2 } from "lucide-react";
import type { SpanStatus } from "@/lib/api";
import { KIND_LABEL, kindOf } from "@/lib/kinds";
import { cn } from "@/lib/utils";

export function StatusBadge({
  status,
  className,
}: {
  status: SpanStatus | string;
  className?: string;
}) {
  const ok = status === "ok";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[13px] font-medium",
        ok
          ? "border-[color:var(--status-good)]/30 text-[color:var(--status-good-text)]"
          : "border-[color:var(--status-critical)]/40 text-[color:var(--status-critical)]",
        className,
      )}
    >
      {ok ? <CheckCircle2 className="h-3 w-3" /> : <AlertCircle className="h-3 w-3" />}
      {ok ? "ok" : "error"}
    </span>
  );
}

export function KindDot({ kind, className }: { kind: string; className?: string }) {
  return (
    <span className={cn("inline-block h-2 w-2 rounded-sm", `bg-kind-${kindOf(kind)}`, className)} />
  );
}

export function KindBadge({ kind, className }: { kind: string; className?: string }) {
  const k = kindOf(kind);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border bg-card px-1.5 py-0.5 text-[13px] font-medium",
        className,
      )}
    >
      <KindDot kind={k} />
      {KIND_LABEL[k]}
    </span>
  );
}

export function Mono({ children, className }: { children: React.ReactNode; className?: string }) {
  return <span className={cn("font-mono text-sm", className)}>{children}</span>;
}
