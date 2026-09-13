"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Moon, Pause, Play, Search, Sparkles, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
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
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-muted-foreground"
          onClick={() => setTheme(dark ? "light" : "dark")}
        >
          {dark ? <Sun className="h-[17px] w-[17px]" /> : <Moon className="h-[17px] w-[17px]" />}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{dark ? "Light theme" : "Dark theme"}</TooltipContent>
    </Tooltip>
  );
}

function LiveIndicator() {
  const { connected, events, paused, setPaused } = useLive();
  const recent = events.filter((e) => Date.now() - e.received_at < 5000).length;
  return (
    <div className="flex items-center gap-1">
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="flex items-center gap-1.5 rounded-md border border-border/80 bg-card px-2 py-1 text-xs shadow-xs">
            <span
              className={cn(
                "relative flex h-1.5 w-1.5 rounded-full",
                connected ? "bg-[var(--status-good)]" : "bg-[var(--status-critical)]",
              )}
            >
              {connected && recent > 0 && (
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--status-good)] opacity-75" />
              )}
            </span>
            <span className="font-medium text-muted-foreground">
              {connected ? "Live" : "Offline"}
            </span>
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
            className="h-8 w-8 text-muted-foreground"
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
  const isDetail = pathname.split("/").filter(Boolean).length > 1;

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border/80 bg-background/80 px-5 backdrop-blur-md lg:px-8">
      <nav className="flex min-w-0 flex-1 items-center gap-1.5 text-sm">
        <span className="hidden text-muted-foreground sm:inline">Lens</span>
        <ChevronRight className="hidden h-3.5 w-3.5 text-muted-foreground/50 sm:inline" />
        {current && isDetail ? (
          <Link href={current.href} className="text-muted-foreground hover:text-foreground">
            {current.label}
          </Link>
        ) : (
          <span className="font-medium">{current?.label ?? "Overview"}</span>
        )}
        {isDetail && (
          <>
            <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/50" />
            <span className="truncate font-medium">Detail</span>
          </>
        )}
      </nav>

      <Select value={app ?? ALL_APPS} onValueChange={(v) => setApp(v === ALL_APPS ? undefined : v)}>
        <SelectTrigger className="h-8 w-[172px] gap-1 text-xs shadow-xs">
          <SelectValue placeholder="All applications" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL_APPS}>All applications</SelectItem>
          {(apps.data ?? []).map((a) => (
            <SelectItem key={a.app} value={a.app}>
              <span className="flex items-center gap-2">
                {a.app}
                <span className="tabular text-[10px] text-muted-foreground">{a.traces}</span>
              </span>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Button
        variant="outline"
        size="sm"
        className="hidden h-8 w-[200px] justify-start gap-2 border-border/80 text-xs font-normal text-muted-foreground shadow-xs lg:flex"
        onClick={() => document.dispatchEvent(new CustomEvent("lens:command"))}
      >
        <Search className="h-3.5 w-3.5" />
        Search…
        <kbd className="ml-auto rounded border bg-muted px-1.5 font-mono text-[10px]">⌘K</kbd>
      </Button>

      <LiveIndicator />
      <ThemeToggle />

      <Button
        size="sm"
        className="h-8 gap-1.5 text-xs shadow-sm"
        onClick={() => document.dispatchEvent(new CustomEvent("lens:assistant"))}
      >
        <Sparkles className="h-3.5 w-3.5" />
        <span className="hidden sm:inline">Ask Lens</span>
      </Button>
    </header>
  );
}
