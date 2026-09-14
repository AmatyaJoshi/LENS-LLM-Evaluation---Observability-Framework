"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { DatabaseZap } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const NEW = "__new__";

export function PromoteDialog({ traceIds }: { traceIds: string[] }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [target, setTarget] = useState<string>("");
  const [newName, setNewName] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const datasets = useQuery({ queryKey: ["datasets"], queryFn: api.datasets, enabled: open });

  const promote = useMutation({
    mutationFn: async () => {
      let id = target;
      if (target === NEW) {
        const d = await api.createDataset({ name: newName });
        id = d.id;
      }
      await api.promoteTraces(id, traceIds);
      return id;
    },
    onSuccess: () => {
      setDone(`Promoted ${traceIds.length} trace${traceIds.length === 1 ? "" : "s"}.`);
      void qc.invalidateQueries({ queryKey: ["datasets"] });
    },
  });

  const canGo = traceIds.length > 0 && (target === NEW ? !!newName : !!target);

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) setDone(null);
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="h-8 text-sm" disabled={!traceIds.length}>
          <DatabaseZap className="mr-1.5 h-3.5 w-3.5" /> Promote to dataset
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Promote {traceIds.length} traces to a dataset</DialogTitle>
        </DialogHeader>
        {done ? (
          <p className="text-sm text-[color:var(--status-good-text)]">{done}</p>
        ) : (
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">
              Each trace becomes an example (input, expected output, contexts) for offline
              evaluation and the CI gate.
            </p>
            <Select value={target} onValueChange={setTarget}>
              <SelectTrigger className="text-sm">
                <SelectValue placeholder="Choose a dataset" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NEW}>+ New dataset…</SelectItem>
                {(datasets.data ?? []).map((d) => (
                  <SelectItem key={d.id} value={d.id}>
                    {d.name} ({d.example_count})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {target === NEW && (
              <Input
                placeholder="new dataset name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
              />
            )}
            {promote.isError && (
              <p className="text-xs text-[color:var(--status-critical)]">
                {(promote.error as Error).message}
              </p>
            )}
          </div>
        )}
        <DialogFooter>
          {done ? (
            <Button size="sm" onClick={() => setOpen(false)}>
              Done
            </Button>
          ) : (
            <Button
              size="sm"
              disabled={!canGo || promote.isPending}
              onClick={() => promote.mutate()}
            >
              {promote.isPending ? "Promoting…" : "Promote"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
