"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Crosshair, ShieldAlert } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "@/lib/api";
import { fmtPct, shortId } from "@/lib/format";
import { useAppFilter } from "@/components/shell/topbar";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { KpiTile } from "@/components/shared/kpi-tile";
import { AXIS, ChartCard, ChartTooltip, GRID } from "@/components/charts/chart-kit";
import { Skeleton } from "@/components/ui/skeleton";

export default function RedteamPage() {
  const [app] = useAppFilter();
  const catalogue = useQuery({ queryKey: ["probes"], queryFn: api.probes });
  const runs = useQuery({
    queryKey: ["redteamRuns", app],
    queryFn: () => api.redteamRuns({ app }),
  });
  const targetApp = app ?? runs.data?.[0]?.app;
  const asr = useQuery({
    queryKey: ["redteamAsr", targetApp],
    queryFn: () => api.redteamAsr({ app: targetApp! }),
    enabled: !!targetApp,
  });
  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const runId = selectedRun ?? runs.data?.[0]?.id ?? null;
  const results = useQuery({
    queryKey: ["redteamResults", runId],
    queryFn: () => api.redteamResults(runId!, { success: true }),
    enabled: !!runId,
  });

  const latest = runs.data?.[0];
  const catData = catalogue.data
    ? Object.entries(catalogue.data.by_category).map(([k, v]) => ({
        category: k.replace(/_/g, " "),
        n: v,
      }))
    : [];
  const asrData = (asr.data ?? []).map((p) => ({
    t: p.defence ?? p.git_sha ?? shortId(p.run_id, 6),
    asr: p.asr,
  }));

  return (
    <>
      <PageHeader
        title="Red team"
        description="Adversarial testing of your own app; attack success rate over time, before and after defences"
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <KpiTile
          label="Probes"
          value={catalogue.data?.total ?? "…"}
          hint={`${catalogue.data?.categories.length ?? 0} categories · ${catalogue.data?.mutators.length ?? 0} mutators`}
        />
        <KpiTile
          label="Latest ASR"
          value={latest ? fmtPct(latest.asr) : "–"}
          tone={
            latest && latest.asr > 0.2 ? "critical" : latest && latest.asr > 0 ? "warning" : "good"
          }
          hint={latest ? `${latest.successes}/${latest.total_probes} succeeded` : "no runs"}
        />
        <KpiTile
          label="Detector caught"
          value={latest ? fmtPct(latest.detector_caught_rate) : "–"}
          hint="of successful attacks"
        />
        <KpiTile
          label="Runs"
          value={runs.data?.length ?? 0}
          hint={latest?.defence ? `latest: ${latest.defence}` : undefined}
        />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <ChartCard title="Probe library" subtitle="Seed probes by category (before mutators)">
          {catData.length === 0 ? (
            <Skeleton className="h-[220px] w-full" />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart
                data={catData}
                layout="vertical"
                margin={{ top: 4, right: 12, left: 40, bottom: 0 }}
              >
                <CartesianGrid {...GRID} horizontal={false} />
                <XAxis type="number" {...AXIS} allowDecimals={false} />
                <YAxis type="category" dataKey="category" {...AXIS} width={110} />
                <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--viz-grid)" }} />
                <Bar dataKey="n" name="probes" radius={[0, 3, 3, 0]}>
                  {catData.map((_, i) => (
                    <Cell key={i} fill={`var(--series-${(i % 8) + 1})`} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        <ChartCard title="Attack success rate over time" subtitle="The before/after-defence chart">
          {asrData.length === 0 ? (
            <EmptyState
              icon={Crosshair}
              title="No runs yet"
              description="Run `lens redteam --target <url> --app <app>` to attack your app and record ASR."
              className="border-0 py-10"
            />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={asrData} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
                <CartesianGrid {...GRID} />
                <XAxis dataKey="t" {...AXIS} minTickGap={16} />
                <YAxis
                  {...AXIS}
                  domain={[0, 1]}
                  width={44}
                  tickFormatter={(v: number) => fmtPct(v, 0)}
                />
                <Tooltip content={<ChartTooltip format={(v) => fmtPct(v)} />} />
                <Line
                  type="monotone"
                  dataKey="asr"
                  name="ASR"
                  stroke="var(--status-critical)"
                  strokeWidth={2}
                  dot={{ r: 4, fill: "var(--status-critical)", strokeWidth: 0 }}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </ChartCard>
      </div>

      {runs.data && runs.data.length > 0 && (
        <div className="mt-4 grid gap-4 lg:grid-cols-[320px_1fr]">
          <div className="overflow-hidden rounded-lg border bg-card">
            <div className="border-b px-3 py-2 text-sm font-medium">Runs</div>
            <ul className="divide-y">
              {runs.data.map((r) => (
                <li key={r.id}>
                  <button
                    onClick={() => setSelectedRun(r.id)}
                    className={`w-full px-3 py-2 text-left text-xs hover:bg-accent/50 ${runId === r.id ? "bg-accent" : ""}`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium">
                        {r.defence ?? r.git_sha ?? shortId(r.id, 8)}
                      </span>
                      <span
                        className="font-medium"
                        style={{
                          color: r.asr > 0.2 ? "var(--status-critical)" : "var(--status-good-text)",
                        }}
                      >
                        {fmtPct(r.asr)}
                      </span>
                    </div>
                    <div className="tabular mt-0.5 text-[10px] text-muted-foreground">
                      {r.successes}/{r.total_probes} · caught {fmtPct(r.detector_caught_rate, 0)}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </div>

          <div className="overflow-hidden rounded-lg border bg-card">
            <div className="flex items-center gap-2 border-b px-3 py-2 text-sm font-medium">
              <ShieldAlert className="h-4 w-4 text-[color:var(--status-critical)]" /> Successful
              attacks
            </div>
            {results.isLoading ? (
              <Skeleton className="m-3 h-40" />
            ) : results.data && results.data.length === 0 ? (
              <div className="p-6 text-center text-xs text-muted-foreground">
                No successful attacks in this run.
              </div>
            ) : (
              <div className="scrollbar-thin max-h-[420px] overflow-y-auto">
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-card text-muted-foreground">
                    <tr className="[&>th]:px-3 [&>th]:py-1.5 [&>th]:text-left [&>th]:font-normal">
                      <th>Probe</th>
                      <th>Category</th>
                      <th>Mutator</th>
                      <th>Why</th>
                    </tr>
                  </thead>
                  <tbody>
                    {results.data?.map((r) => (
                      <tr key={r.id} className="border-t">
                        <td className="px-3 py-1.5 font-mono text-[10px]">{r.probe_id}</td>
                        <td className="px-3 py-1.5">{r.category.replace(/_/g, " ")}</td>
                        <td className="px-3 py-1.5 text-muted-foreground">{r.mutator ?? "seed"}</td>
                        <td className="px-3 py-1.5 text-muted-foreground">{r.success_reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      <p className="mt-4 text-[11px] text-muted-foreground">
        Ethics: probes target your own application and contain no harmful how-to content. Success
        means a policy violation of the target (a leaked canary, a forbidden tool call, an
        exfiltration URL), never the production of dangerous content.
      </p>
    </>
  );
}
