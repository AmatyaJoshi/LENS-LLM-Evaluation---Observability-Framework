import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export function EmptyState({
  icon: Icon,
  title,
  description,
  children,
  className,
}: {
  icon?: LucideIcon;
  title: string;
  description?: React.ReactNode;
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center rounded-xl border border-dashed border-border bg-card/40 px-6 py-16 text-center",
        className,
      )}
    >
      {Icon && (
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl border border-border/70 bg-muted/60 text-muted-foreground">
          <Icon className="h-5 w-5" />
        </div>
      )}
      <div className="text-sm font-semibold">{title}</div>
      {description && (
        <div className="mt-1.5 max-w-md text-sm leading-relaxed text-muted-foreground">
          {description}
        </div>
      )}
      {children && <div className="mt-5">{children}</div>}
    </div>
  );
}
