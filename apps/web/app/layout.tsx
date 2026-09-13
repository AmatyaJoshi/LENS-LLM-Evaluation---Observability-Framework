import type { Metadata } from "next";
import { Suspense } from "react";
import { Inter, JetBrains_Mono } from "next/font/google";
import { Providers } from "@/lib/providers";
import { Sidebar } from "@/components/shell/sidebar";
import { Topbar } from "@/components/shell/topbar";
import { CommandMenu } from "@/components/shell/command-menu";
import { AssistantPanel } from "@/components/assistant/assistant-panel";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono-jb", display: "swap" });

export const metadata: Metadata = {
  title: { default: "Lens — LLM Observability", template: "%s · Lens" },
  description: "Observability and evaluation for LLM applications and agents",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning className={`${inter.variable} ${mono.variable}`}>
      <body className="min-h-screen font-sans">
        <Providers>
          <div className="flex min-h-screen">
            <Sidebar />
            <div className="flex min-w-0 flex-1 flex-col">
              <Suspense fallback={<div className="h-14 border-b" />}>
                <Topbar />
              </Suspense>
              <main className="flex-1 px-5 pb-16 pt-6 lg:px-8">
                <div className="mx-auto w-full max-w-[1400px] animate-fade-in">
                  <Suspense fallback={null}>{children}</Suspense>
                </div>
              </main>
            </div>
          </div>
          <CommandMenu />
          <Suspense fallback={null}>
            <AssistantPanel />
          </Suspense>
        </Providers>
      </body>
    </html>
  );
}
