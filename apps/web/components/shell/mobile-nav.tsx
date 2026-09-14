"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Aperture, Menu } from "lucide-react";
import { cn } from "@/lib/utils";
import { GROUP_LABEL, NAV } from "@/components/shell/nav";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";

export function MobileNav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [pathname]);
  const groups = Array.from(new Set(NAV.map((n) => n.group)));
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon" className="h-8 w-8 md:hidden" aria-label="Menu">
          <Menu className="h-5 w-5" />
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="w-[260px] bg-sidebar p-0">
        <div className="flex h-14 items-center gap-2.5 border-b px-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Aperture className="h-[18px] w-[18px]" />
          </div>
          <div className="text-[15px] font-semibold tracking-tight">Lens</div>
        </div>
        <nav className="space-y-5 overflow-y-auto px-3 py-4">
          {groups.map((g) => (
            <div key={g}>
              <div className="px-2.5 pb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground/60">
                {GROUP_LABEL[g]}
              </div>
              <div className="space-y-0.5">
                {NAV.filter((n) => n.group === g).map((item) => {
                  const active =
                    item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      className={cn(
                        "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm font-medium",
                        active
                          ? "bg-accent-tint text-primary"
                          : "text-muted-foreground hover:bg-accent/70 hover:text-foreground",
                      )}
                    >
                      <item.icon className="h-[17px] w-[17px]" />
                      {item.label}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>
      </SheetContent>
    </Sheet>
  );
}
