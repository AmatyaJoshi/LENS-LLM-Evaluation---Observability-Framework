"use client";

import { WINDOWS, type Window } from "@/lib/api";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export function WindowSelect({
  value,
  onChange,
}: {
  value: Window;
  onChange: (w: Window) => void;
}) {
  return (
    <Select value={value} onValueChange={(v) => onChange(v as Window)}>
      <SelectTrigger className="h-8 w-[170px] text-sm">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {WINDOWS.map((w) => (
          <SelectItem key={w.value} value={w.value}>
            {w.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
