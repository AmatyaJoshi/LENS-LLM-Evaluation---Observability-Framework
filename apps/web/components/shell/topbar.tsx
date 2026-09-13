"use client";

import { useQuery } from "@tanstack/react-query";
import { Moon, Pause, Play, Search, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useLive } from "@/lib/live";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { NAV } from "@/components/shell/nav";

export const ALL_APPS = "__all__";

export function useAppFilter(): [string | undefined, (app: string | undefined) => void] {
  const sp = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const app = sp.get("app") ?? undefined;
  const set = (next: string | undefined) => {
    const params = new URLSearchParams(sp.toString());
    if (next) params.set("app", next);
    else params.delete("app");
    router.replace(`${pathname}${params.toString() ? `?${params}` : ""}`);
  };
  return [app, set];
}

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const dark = mounted ? resolvedTheme === "dark" : true;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button variant="ghost" size="icon" onClick={() => setTheme(dark ? "light" : "dark")}>
          {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </Button>
      </TooltipTrigger>
      <TooltipContent>Switch to {dark ? "light" : "dark"} theme</TooltipContent>
    </Tooltip>
  );
}

function LiveIndicator() {
  const { connected, events, paused, setPaused } = useLive();
  const recent = events.filter((e) => Date.now() - e.received_at < 5000).length;
  return (
    <div className="flex items-center gap-1.5">
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="flex items-center gap-1.5 rounded-md border px-2 py-1 text-sm">
            <span
              className={cn(
                "relative flex h-2 w-2 rounded-full",
                connected ? "bg-[var(--status-good)]" : "bg-[var(--status-critical)]",
              )}
            >
              {connected && recent > 0 && (
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--status-good)] opacity-75" />
              )}
            </span>
            <span className="text-muted-foreground">{connected ? "Live" : "Offline"}</span>
            {events.length > 0 && (
              <span className="tabular text-muted-foreground/70">{events.length}</span>
            )}
          </div>
        </TooltipTrigger>
        <TooltipContent>
          {connected ? "Receiving trace events over WebSocket" : "WebSocket disconnected, retrying"}
        </TooltipContent>
      </Tooltip>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={() => setPaused(!paused)}
          >
            {paused ? <Play className="h-3.5 w-3.5" /> : <Pause className="h-3.5 w-3.5" />}
          </Button>
        </TooltipTrigger>
        <TooltipContent>{paused ? "Resume live refresh" : "Pause live refresh"}</TooltipContent>
      </Tooltip>
    </div>
  );
}

export function Topbar() {
  const pathname = usePathname();
  const [app, setApp] = useAppFilter();
  const apps = useQuery({ queryKey: ["apps"], queryFn: api.apps, refetchInterval: 30_000 });
  const current = NAV.find((n) =>
    n.href === "/" ? pathname === "/" : pathname.startsWith(n.href),
  );

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b bg-background/80 px-6 backdrop-blur lg:px-8">
      <div className="min-w-0 flex-1">
        <div className="text-[15px] font-medium">{current?.label ?? "Lens"}</div>
      </div>

      <Select value={app ?? ALL_APPS} onValueChange={(v) => setApp(v === ALL_APPS ? undefined : v)}>
        <SelectTrigger className="h-8 w-[180px] text-sm">
          <SelectValue placeholder="All apps" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL_APPS}>All apps</SelectItem>
          {(apps.data ?? []).map((a) => (
            <SelectItem key={a.app} value={a.app}>
              <span className="flex items-center gap-2">
                {a.app}
                <span className="tabular text-[12px] text-muted-foreground">{a.traces}</span>
              </span>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Button
        variant="outline"
        size="sm"
        className="hidden h-8 w-[220px] justify-start gap-2 text-sm text-muted-foreground lg:flex"
        onClick={() => document.dispatchEvent(new CustomEvent("lens:command"))}
      >
        <Search className="h-3.5 w-3.5" />
        Search traces, jump to…
        <kbd className="ml-auto rounded border bg-muted px-1 font-mono text-[12px]">⌘K</kbd>
      </Button>

      <LiveIndicator />
      <ThemeToggle />
    </header>
  );
}
