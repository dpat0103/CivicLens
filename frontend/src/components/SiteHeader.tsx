"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/", label: "Overview" },
  { href: "/places", label: "Municipalities" },
  { href: "/compare", label: "Compare" },
  { href: "/ask", label: "Ask" },
  { href: "/about", label: "Method" },
];

export default function SiteHeader() {
  const pathname = usePathname();

  function isActive(href: string) {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  }

  return (
    <header className="border-b border-rule bg-surface">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-6 px-6 py-4">
        <Link href="/" className="flex items-baseline gap-2">
          <span className="serif text-lg font-semibold tracking-tight text-ink">
            CivicLens
          </span>
          <span className="hidden text-xs text-ink-faint sm:inline">New Jersey</span>
        </Link>

        <nav aria-label="Sections">
          <ul className="flex items-center gap-1">
            {TABS.map((tab) => {
              const active = isActive(tab.href);
              return (
                <li key={tab.href}>
                  <Link
                    href={tab.href}
                    aria-current={active ? "page" : undefined}
                    className={
                      active
                        ? "block rounded px-3 py-1.5 text-sm font-medium text-ink"
                        : "block rounded px-3 py-1.5 text-sm text-ink-muted transition-colors hover:text-ink"
                    }
                  >
                    <span className="relative">
                      {tab.label}
                      {active && (
                        <span className="absolute -bottom-2 left-0 right-0 h-0.5 bg-accent" />
                      )}
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      </div>
    </header>
  );
}
