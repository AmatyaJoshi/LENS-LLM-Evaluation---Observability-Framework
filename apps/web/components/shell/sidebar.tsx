"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Aperture } from "lucide-react";
import { cn } from "@/lib/utils";
import { GROUP_LABEL, IMPLEMENTED_PHASE, NAV, type NavItem } from "@/components/shell/nav";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

function NavLink({ item, active }: { item: NavItem; active: boolean }) {
  const Icon = item.icon;
  const pending = item.phase > IMPLEMENTED_PHASE;
  return (
    <Link
      href={item.href}
      className={cn(
        "group relative flex items-center gap-2.5 rounded-md px-2.5 py-[7px] text-[13px] font-medium transition-colors",
        active
          ? "bg-accent-tint text-primary"
          : "text-muted-foreground hover:bg-accent/70 hover:text-foreground",
      )}
    >
      {active && (
        <span className="absolute -left-3 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-full bg-primary" />
      )}
      <Icon
        className={cn(
          "h-[17px] w-[17px] shrink-0 transition-colors",
          active ? "text-primary" : "text-muted-foreground/80 group-hover:text-foreground",
        )}
      />
      <span className="flex-1 truncate">{item.label}</span>
      {pending && (
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="rounded border border-border/70 px-1 font-mono text-[9px] leading-4 text-muted-foreground/60">
              soon
            </span>
          </TooltipTrigger>
          <TooltipContent side="right">Backend lands in phase {item.phase}</TooltipContent>
        </Tooltip>
      )}
    </Link>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const groups = Array.from(new Set(NAV.map((n) => n.group)));
  return (
    <aside className="sticky top-0 hidden h-screen w-[248px] shrink-0 flex-col border-r border-border/80 bg-sidebar md:flex">
      <div className="flex h-14 items-center gap-2.5 border-b border-border/70 px-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
          <Aperture className="h-[18px] w-[18px]" />
        </div>
        <div className="leading-tight">
          <div className="text-[15px] font-semibold tracking-tight">Lens</div>
          <div className="text-[10px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
            Observability
          </div>
        </div>
      </div>

      <nav className="flex-1 space-y-6 overflow-y-auto px-3 py-4">
        {groups.map((g) => (
          <div key={g}>
            <div className="px-2.5 pb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground/60">
              {GROUP_LABEL[g]}
            </div>
            <div className="space-y-0.5">
              {NAV.filter((n) => n.group === g).map((item) => (
                <NavLink
                  key={item.href}
                  item={item}
                  active={item.href === "/" ? pathname === "/" : pathname.startsWith(item.href)}
                />
              ))}
            </div>
          </div>
        ))}
      </nav>

      <div className="border-t border-border/70 px-3 py-3">
        <div className="flex items-center justify-between rounded-md bg-muted/60 px-2.5 py-2 text-[11px] text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--status-good)]" />
            v0.1.0
          </span>
          <kbd className="rounded border border-border bg-card px-1.5 py-0.5 font-mono text-[10px] shadow-xs">
            ⌘K
          </kbd>
        </div>
      </div>
    </aside>
  );
}
