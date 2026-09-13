"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Database, Plus } from "lucide-react";
import { api } from "@/lib/api";
import { fmtAgo } from "@/lib/format";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

export default function DatasetsPage() {
  const qc = useQueryClient();
  const datasets = useQuery({ queryKey: ["datasets"], queryFn: api.datasets });
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [open, setOpen] = useState(false);

  const create = useMutation({
    mutationFn: () => api.createDataset({ name, description: desc || undefined }),
    onSuccess: () => {
      setOpen(false);
      setName("");
      setDesc("");
      void qc.invalidateQueries({ queryKey: ["datasets"] });
    },
  });

  return (
    <>
      <PageHeader
        title="Datasets"
        description="Golden sets built from traces, split without leakage, used by lens eval and the CI gate"
        actions={
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button size="sm" className="h-8 text-xs">
                <Plus className="mr-1 h-3.5 w-3.5" /> New dataset
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>New dataset</DialogTitle>
              </DialogHeader>
              <div className="space-y-3">
                <Input
                  placeholder="name (e.g. golden)"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
                <Input
                  placeholder="description (optional)"
                  value={desc}
                  onChange={(e) => setDesc(e.target.value)}
                />
                {create.isError && (
                  <p className="text-xs text-[color:var(--status-critical)]">
                    {(create.error as Error).message}
                  </p>
                )}
              </div>
              <DialogFooter>
                <Button
                  size="sm"
                  disabled={!name || create.isPending}
                  onClick={() => create.mutate()}
                >
                  Create
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        }
      />

      {datasets.isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : datasets.data && datasets.data.length === 0 ? (
        <EmptyState
          icon={Database}
          title="No datasets yet"
          description="Create one here, then promote traces into it from the Traces page, or import a JSONL with lens."
        />
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {datasets.data?.map((d) => (
            <div key={d.id} className="rounded-lg border bg-card p-4">
              <div className="flex items-center justify-between">
                <span className="font-medium">{d.name}</span>
                <span className="rounded border px-1.5 py-0.5 text-[10px] text-muted-foreground">
                  {d.split_strategy}
                </span>
              </div>
              {d.description && (
                <p className="mt-1 text-xs text-muted-foreground">{d.description}</p>
              )}
              <div className="mt-3 flex items-baseline gap-2">
                <span className="text-2xl font-semibold">{d.example_count}</span>
                <span className="text-xs text-muted-foreground">examples</span>
              </div>
              <div className="mt-2 flex gap-3 text-[11px] text-muted-foreground">
                {Object.entries(d.splits).map(([split, n]) => (
                  <span key={split}>
                    {split} <span className="tabular font-medium text-foreground">{n}</span>
                  </span>
                ))}
              </div>
              <div className="mt-2 text-[10px] text-muted-foreground">
                created {fmtAgo(Date.parse(d.created_at) * 1e6)}
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
