import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Lens",
  description: "LLM evaluation & observability",
};

const NAV: ReadonlyArray<{ href: string; label: string; phase: number }> = [
  { href: "/traces", label: "Traces", phase: 2 },
  { href: "/trajectories", label: "Trajectories", phase: 2 },
  { href: "/evaluations", label: "Evaluations", phase: 3 },
  { href: "/judges", label: "Judge quality", phase: 4 },
  { href: "/redteam", label: "Red team", phase: 5 },
  { href: "/labelling", label: "Labelling", phase: 4 },
  { href: "/datasets", label: "Datasets", phase: 4 },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen">
        <div className="flex min-h-screen">
          <aside className="w-56 shrink-0 border-r bg-card px-4 py-5">
            <Link href="/" className="font-mono text-sm font-semibold tracking-tight">
              lens
            </Link>
            <nav className="mt-6 flex flex-col gap-1 text-sm">
              {NAV.map((item) => (
                <span
                  key={item.href}
                  className="flex items-center justify-between rounded-md px-2 py-1.5 text-muted-foreground"
                  title={`Phase ${item.phase}`}
                >
                  {item.label}
                  <span className="font-mono text-[10px] opacity-60">p{item.phase}</span>
                </span>
              ))}
            </nav>
          </aside>
          <main className="flex-1 px-8 py-6">{children}</main>
        </div>
      </body>
    </html>
  );
}
