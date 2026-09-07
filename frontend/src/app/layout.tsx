import type { Metadata } from "next";
import { IBM_Plex_Sans, IBM_Plex_Serif } from "next/font/google";
import SiteHeader from "@/components/SiteHeader";
import "./globals.css";

const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-sans",
  display: "swap",
});

const plexSerif = IBM_Plex_Serif({
  subsets: ["latin"],
  weight: ["400", "600"],
  variable: "--font-serif",
  display: "swap",
});

export const metadata: Metadata = {
  title: "CivicLens | New Jersey municipal statistics",
  description:
    "Housing, income, employment, education and commuting statistics for all 564 New Jersey municipalities, drawn from Census ACS and Bureau of Labor Statistics data.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`h-full antialiased ${plexSans.variable} ${plexSerif.variable}`}
    >
      <body
        className="flex min-h-full flex-col bg-paper text-ink"
        style={{ fontFamily: "var(--font-sans), system-ui, sans-serif" }}
      >
        <SiteHeader />
        <div className="flex-1">{children}</div>

        <footer className="mt-20 border-t border-rule bg-surface">
          <div className="mx-auto max-w-6xl px-6 py-8">
            <p className="max-w-2xl text-sm leading-relaxed text-ink-muted">
              Built from the U.S. Census Bureau American Community Survey 5-Year
              Estimates and the Bureau of Labor Statistics Local Area
              Unemployment Statistics program. Figures are estimates and carry
              margins of error that widen for smaller municipalities.
            </p>
            <p className="mt-3 text-sm text-ink-faint">
              CivicLens is an independent project and is not affiliated with any
              government agency.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
