"use client";

import { Search, X } from "lucide-react";
import type { TraceQuery, Window } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { WindowSelect } from "@/components/shared/window-select";

export interface Filters {
  q: string;
  status: "" | "ok" | "error";
  kind: "" | "llm" | "tool" | "retrieval";
  model: string;
  minDuration: string;
  window: Window;
  sort: NonNullable<TraceQuery["sort"]>;
}

export const DEFAULT_FILTERS: Filters = {
  q: "",
  status: "",
  kind: "",
  model: "",
  minDuration: "",
  window: "24h",
  sort: "start_desc",
};

const ANY = "__any__";

export function TraceFilters({
  value,
  onChange,
  models,
}: {
  value: Filters;
  onChange: (f: Filters) => void;
  models: string[];
}) {
  const set = <K extends keyof Filters>(k: K, v: Filters[K]) => onChange({ ...value, [k]: v });
  const dirty =
    JSON.stringify({ ...value, window: "x", sort: "x" }) !==
    JSON.stringify({ ...DEFAULT_FILTERS, window: "x", sort: "x" });

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={value.q}
          onChange={(e) => set("q", e.target.value)}
          placeholder="Search id, run, question, answer"
          className="h-8 w-[280px] pl-8 text-sm"
        />
      </div>
      <Select
        value={value.status || ANY}
        onValueChange={(v) => set("status", v === ANY ? "" : (v as Filters["status"]))}
      >
        <SelectTrigger className="h-8 w-[120px] text-sm">
          <SelectValue placeholder="Status" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY}>Any status</SelectItem>
          <SelectItem value="ok">ok</SelectItem>
          <SelectItem value="error">error</SelectItem>
        </SelectContent>
      </Select>
      <Select
        value={value.kind || ANY}
        onValueChange={(v) => set("kind", v === ANY ? "" : (v as Filters["kind"]))}
      >
        <SelectTrigger className="h-8 w-[140px] text-sm">
          <SelectValue placeholder="Contains" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY}>Any spans</SelectItem>
          <SelectItem value="llm">Has LLM call</SelectItem>
          <SelectItem value="tool">Has tool call</SelectItem>
          <SelectItem value="retrieval">Has retrieval</SelectItem>
        </SelectContent>
      </Select>
      <Select value={value.model || ANY} onValueChange={(v) => set("model", v === ANY ? "" : v)}>
        <SelectTrigger className="h-8 w-[170px] text-sm">
          <SelectValue placeholder="Model" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY}>Any model</SelectItem>
          {models.map((m) => (
            <SelectItem key={m} value={m}>
              <span className="font-mono text-sm">{m}</span>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Input
        value={value.minDuration}
        onChange={(e) => set("minDuration", e.target.value.replace(/[^\d.]/g, ""))}
        placeholder="≥ ms"
        className="h-8 w-[84px] text-sm"
        inputMode="decimal"
      />
      <WindowSelect value={value.window} onChange={(w) => set("window", w)} />
      <Select value={value.sort} onValueChange={(v) => set("sort", v as Filters["sort"])}>
        <SelectTrigger className="h-8 w-[150px] text-sm">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="start_desc">Newest first</SelectItem>
          <SelectItem value="start_asc">Oldest first</SelectItem>
          <SelectItem value="duration_desc">Slowest first</SelectItem>
          <SelectItem value="tokens_desc">Most tokens</SelectItem>
        </SelectContent>
      </Select>
      {dirty && (
        <Button
          variant="ghost"
          size="sm"
          className="h-8 text-sm"
          onClick={() => onChange({ ...DEFAULT_FILTERS, window: value.window, sort: value.sort })}
        >
          <X className="mr-1 h-3 w-3" /> Clear
        </Button>
      )}
    </div>
  );
}
