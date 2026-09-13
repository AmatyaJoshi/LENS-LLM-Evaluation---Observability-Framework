import type { Metadata } from "next";
import { Suspense } from "react";
import { Providers } from "@/lib/providers";
import { Sidebar } from "@/components/shell/sidebar";
import { Topbar } from "@/components/shell/topbar";
import { CommandMenu } from "@/components/shell/command-menu";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Lens", template: "%s · Lens" },
  description: "LLM evaluation & observability",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen">
        <Providers>
          <div className="flex min-h-screen">
            <Sidebar />
            <div className="flex min-w-0 flex-1 flex-col">
              <Suspense fallback={<div className="h-14 border-b" />}>
                <Topbar />
              </Suspense>
              <main className="flex-1 px-6 pb-10 pt-5 lg:px-8">
                <Suspense fallback={null}>{children}</Suspense>
              </main>
            </div>
          </div>
          <CommandMenu />
        </Providers>
      </body>
    </html>
  );
}
