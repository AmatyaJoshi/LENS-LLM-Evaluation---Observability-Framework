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
    <Tooltip>
      <TooltipTrigger asChild>
        <Link
          href={item.href}
          className={cn(
            "group flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[15px] transition-colors",
            active
              ? "bg-accent text-foreground"
              : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
          )}
        >
          <Icon className={cn("h-4 w-4 shrink-0", active ? "text-primary" : "opacity-80")} />
          <span className="flex-1 truncate">{item.label}</span>
          {pending && (
            <span className="rounded border px-1 font-mono text-[12px] leading-4 text-muted-foreground/70">
              P{item.phase}
            </span>
          )}
        </Link>
      </TooltipTrigger>
      <TooltipContent side="right" className="text-sm">
        {pending ? `Backend lands in phase ${item.phase}` : item.label}
        {item.shortcut && <span className="ml-2 font-mono opacity-60">{item.shortcut}</span>}
      </TooltipContent>
    </Tooltip>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const groups = Array.from(new Set(NAV.map((n) => n.group)));
  return (
    <aside className="sticky top-0 hidden h-screen w-[232px] shrink-0 flex-col border-r bg-card/60 backdrop-blur md:flex">
      <div className="flex h-14 items-center gap-2 px-4">
        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
          <Aperture className="h-4 w-4" />
        </div>
        <div className="leading-tight">
          <div className="text-[15px] font-semibold tracking-tight">Lens</div>
          <div className="text-[12px] uppercase tracking-wider text-muted-foreground">
            LLM observability
          </div>
        </div>
      </div>
      <nav className="scrollbar-thin flex-1 space-y-5 overflow-y-auto px-3 py-3">
        {groups.map((g) => (
          <div key={g}>
            <div className="px-2.5 pb-1.5 text-[12px] font-medium uppercase tracking-wider text-muted-foreground/70">
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
      <div className="border-t px-4 py-3 text-[13px] text-muted-foreground">
        <div className="flex items-center justify-between">
          <span>Phase 2 build</span>
          <kbd className="rounded border bg-muted px-1 font-mono text-[12px]">⌘K</kbd>
        </div>
      </div>
    </aside>
  );
}
