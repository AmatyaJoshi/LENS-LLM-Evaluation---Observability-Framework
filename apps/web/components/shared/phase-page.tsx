"use client";

import { useQuery } from "@tanstack/react-query";
import type { LucideIcon } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { Card } from "@/components/ui/card";

/**
 * Page for a capability whose backend lands in a later SPEC.md phase. It calls the
 * real (stub) endpoint so the moment the backend ships the page reports data
 * instead of the roadmap, and it never shows invented numbers.
 */
export function PhasePage({
  title,
  description,
  icon,
  phase,
  fetcher,
  will,
  metrics,
}: {
  title: string;
  description: string;
  icon: LucideIcon;
  phase: number;
  fetcher: () => Promise<unknown[]>;
  will: string[];
  metrics?: { name: string; formula: string }[];
}) {
  const q = useQuery({ queryKey: ["phase", title], queryFn: fetcher });
  const hasData = Array.isArray(q.data) && q.data.length > 0;
  return (
    <>
      <PageHeader title={title} description={description} />
      {hasData ? (
        <pre className="rounded-lg border bg-card p-4 font-mono text-sm">
          {JSON.stringify(q.data, null, 2)}
        </pre>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[1fr_380px]">
          <EmptyState
            icon={icon}
            title={q.isError ? "API unreachable" : `No ${title.toLowerCase()} data yet`}
            description={
              q.isError
                ? "Start the Lens API to load this page."
                : `The ${title.toLowerCase()} backend ships in phase ${phase} of the delivery plan. This page is wired to its endpoint and will populate automatically.`
            }
            className="min-h-[320px]"
          />
          <div className="space-y-3">
            <Card className="p-4">
              <div className="text-[15px] font-medium">What this page will show</div>
              <ul className="mt-2 list-disc space-y-1 pl-4 text-sm text-muted-foreground">
                {will.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </Card>
            {metrics && (
              <Card className="p-4">
                <div className="text-[15px] font-medium">Metric definitions</div>
                <dl className="mt-2 space-y-2 text-sm">
                  {metrics.map((m) => (
                    <div key={m.name}>
                      <dt className="font-medium">{m.name}</dt>
                      <dd className="text-muted-foreground">{m.formula}</dd>
                    </div>
                  ))}
                </dl>
              </Card>
            )}
          </div>
        </div>
      )}
    </>
  );
}
