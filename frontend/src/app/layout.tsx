import type { Metadata } from "next";
import { Inter, Newsreader } from "next/font/google";
import Link from "next/link";
import NavLinks from "@/components/NavLinks";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const display = Newsreader({ subsets: ["latin"], variable: "--font-display-face", display: "swap" });

export const metadata: Metadata = {
  title: { default: "Groundwork", template: "%s · Groundwork" },
  description: "US home values by metro and ZIP, with a backtested 12-month forecast",
};

function Logo() {
  return (
    <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="7" fill="var(--accent)" />
      <path d="M8 16.5 16 9l8 7.5V24h-5.5v-5h-5v5H8z" fill="var(--on-accent)" />
    </svg>
  );
}

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${inter.variable} ${display.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <header className="sticky top-0 z-10 border-b border-line bg-surface/90 backdrop-blur">
          <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
            <Link href="/" className="flex items-center gap-2.5">
              <Logo />
              <span className="display text-xl font-semibold">Groundwork</span>
            </Link>
            <NavLinks />
          </div>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-10">{children}</main>
        <footer className="border-t border-line bg-surface">
          <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-6 text-xs text-muted sm:flex-row sm:justify-between">
            <span>
              Home values: Zillow Home Value Index (Zillow Research). Market activity: Redfin Data Center. Mortgage rates:
              Freddie Mac via FRED. Forecasts are this site&apos;s own and are not financial advice.
            </span>
            <span className="whitespace-nowrap">
              Next.js · FastAPI · PostgreSQL · LightGBM ·{" "}
              <a className="underline hover:text-ink" href="https://github.com/seacoastcreates/groundwork-housing">
                Source on GitHub
              </a>
            </span>
          </div>
        </footer>
      </body>
    </html>
  );
}
