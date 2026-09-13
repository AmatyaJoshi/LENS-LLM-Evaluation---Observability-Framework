"use client";

import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Hash, Moon, Sun } from "lucide-react";
import { api } from "@/lib/api";
import { fmtAgo, shortId } from "@/lib/format";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import { NAV } from "@/components/shell/nav";

export function CommandMenu() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const router = useRouter();
  const { resolvedTheme, setTheme } = useTheme();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.key === "k" && (e.metaKey || e.ctrlKey)) || (e.key === "/" && !isTyping(e))) {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    const onOpen = () => setOpen(true);
    document.addEventListener("keydown", onKey);
    document.addEventListener("lens:command", onOpen);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("lens:command", onOpen);
    };
  }, []);

  const search = useQuery({
    queryKey: ["traces", "cmd", query],
    queryFn: () => api.traces({ q: query, limit: 6 }),
    enabled: open && query.trim().length >= 2,
  });

  const go = (href: string) => {
    setOpen(false);
    router.push(href);
  };

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput
        placeholder="Search traces by id, run, question… or type a page"
        value={query}
        onValueChange={setQuery}
      />
      <CommandList>
        <CommandEmpty>No results.</CommandEmpty>
        {search.data && search.data.items.length > 0 && (
          <CommandGroup heading="Traces">
            {search.data.items.map((t) => (
              <CommandItem
                key={t.trace_id}
                value={`trace ${t.trace_id} ${t.input_preview ?? ""}`}
                onSelect={() => go(`/traces/${t.trace_id}`)}
              >
                <Hash className="mr-2 h-3.5 w-3.5 text-muted-foreground" />
                <span className="font-mono text-sm">{shortId(t.trace_id, 12)}</span>
                <span className="ml-2 truncate text-sm text-muted-foreground">
                  {t.input_preview ?? t.root_name}
                </span>
                <span className="ml-auto text-[12px] text-muted-foreground">
                  {fmtAgo(t.start_ns)}
                </span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}
        <CommandGroup heading="Pages">
          {NAV.map((n) => (
            <CommandItem key={n.href} value={`page ${n.label}`} onSelect={() => go(n.href)}>
              <n.icon className="mr-2 h-3.5 w-3.5 text-muted-foreground" />
              {n.label}
              {n.shortcut && (
                <span className="ml-auto font-mono text-[12px] text-muted-foreground">
                  {n.shortcut}
                </span>
              )}
            </CommandItem>
          ))}
        </CommandGroup>
        <CommandSeparator />
        <CommandGroup heading="Preferences">
          <CommandItem
            value="toggle theme"
            onSelect={() => {
              setTheme(resolvedTheme === "dark" ? "light" : "dark");
              setOpen(false);
            }}
          >
            {resolvedTheme === "dark" ? (
              <Sun className="mr-2 h-3.5 w-3.5" />
            ) : (
              <Moon className="mr-2 h-3.5 w-3.5" />
            )}
            Toggle theme
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}

function isTyping(e: KeyboardEvent): boolean {
  const el = e.target as HTMLElement | null;
  if (!el) return false;
  const tag = el.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || el.isContentEditable;
}
