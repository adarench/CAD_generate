import type { Metadata } from "next";
import Link from "next/link";

import "@/styles/globals.css";
import "leaflet/dist/leaflet.css";

import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "Utah Subdivision Studio",
  description: "Parcel-first land feasibility and concept planning for Utah acquisitions.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-950 text-slate-100">
        <Providers>
          <div className="flex min-h-screen flex-col">
            <header className="sticky top-0 z-40 border-b border-slate-800 bg-slate-950/90 backdrop-blur">
              <nav className="mx-auto flex w-full max-w-[1600px] items-center justify-between px-6 py-4">
                <div className="flex items-center gap-3">
                  <div>
                    <div className="text-lg font-semibold text-emerald-300">
                      Utah Subdivision Studio
                    </div>
                    <div className="text-xs uppercase tracking-[0.28em] text-slate-500">
                      Parcel-driven feasibility
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-5 text-sm text-slate-400">
                  <Link href="/" className="transition hover:text-emerald-300">
                    Home
                  </Link>
                  <Link href="/map" className="transition hover:text-emerald-300">
                    Discovery
                  </Link>
                  <Link href="/runs" className="transition hover:text-emerald-300">
                    Runs
                  </Link>
                </div>
              </nav>
            </header>
            <main className="flex-1">{children}</main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
