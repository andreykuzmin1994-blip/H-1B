import type { Metadata } from 'next';
import { Inter, Fraunces, JetBrains_Mono } from 'next/font/google';
import './globals.css';
import Link from 'next/link';
import { FreshnessPing } from '@/components/FreshnessPing';

const sans = Inter({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-sans',
});
const serif = Fraunces({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-serif',
  axes: ['opsz'],
});
const mono = JetBrains_Mono({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-mono',
});

export const metadata: Metadata = {
  title: 'H-1B Transparency & Accountability Engine',
  description:
    'A public-interest investigation tool that surfaces anomalies in H-1B filings, maps employer entity networks, and generates formatted enforcement tips.',
};

const NAV = [
  { href: '/search', label: 'Search' },
  { href: '/compare', label: 'Compare' },
  { href: '/map', label: 'Map' },
  { href: '/violators', label: 'Violators' },
  { href: '/layoffs', label: 'Layoffs' },
  { href: '/methodology', label: 'Methodology' },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${serif.variable} ${mono.variable}`}>
      <body className="min-h-screen">
        <header className="sticky top-0 z-20 border-b border-ink-200/80 bg-[var(--paper)]/85 backdrop-blur">
          <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3 md:px-6">
            <Link href="/" className="group flex items-center gap-2.5">
              <span
                aria-hidden
                className="relative inline-flex h-7 w-7 items-center justify-center rounded-md bg-ink-900 text-[10px] font-bold tracking-tight text-ember-400 shadow-card"
              >
                H1B
                <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-ember-500 animate-pulseDot" />
              </span>
              <span className="leading-tight">
                <span className="block font-serif text-[15px] font-semibold tracking-tight text-ink-900">
                  Transparency Engine
                </span>
                <span className="block text-[10px] uppercase tracking-[0.18em] text-ink-500">
                  Public-interest investigative tool
                </span>
              </span>
            </Link>
            <nav className="hidden items-center gap-1 text-sm text-ink-700 md:flex">
              {NAV.map((n) => (
                <Link
                  key={n.href}
                  href={n.href}
                  className="rounded-md px-3 py-1.5 hover:bg-ink-100 hover:text-ink-900"
                >
                  {n.label}
                </Link>
              ))}
              <Link
                href="/api/v1/anomalies"
                className="ml-1 rounded-md border border-ink-200 px-3 py-1.5 font-mono text-xs text-ink-500 hover:border-ink-300 hover:text-ink-800"
              >
                API
              </Link>
              <FreshnessPing />
            </nav>
            {/* Mobile compact nav */}
            <nav className="flex items-center gap-1 text-xs md:hidden">
              {NAV.map((n) => (
                <Link
                  key={n.href}
                  href={n.href}
                  className="rounded-md px-2 py-1 text-ink-600 hover:bg-ink-100 hover:text-ink-900"
                >
                  {n.label}
                </Link>
              ))}
            </nav>
          </div>
        </header>

        <main className="mx-auto max-w-7xl px-4 py-8 md:px-6 md:py-10">{children}</main>

        <footer className="mt-20 border-t border-ink-200/80 bg-white/70">
          <div className="mx-auto grid max-w-7xl grid-cols-1 gap-8 px-4 py-10 md:grid-cols-4 md:px-6">
            <div className="md:col-span-2">
              <div className="eyebrow">
                <span className="h-px w-6 bg-ember-500" /> About
              </div>
              <p className="mt-3 max-w-md font-serif text-lg leading-snug text-ink-800">
                A public-interest transparency tool that joins federal labor, immigration, and
                enforcement data to surface where the H-1B system is being abused &mdash; and who is
                being harmed.
              </p>
              <p className="mt-4 text-xs text-ink-500">
                Not an official government service. Findings are computed from public datasets and
                may contain errors. Always verify before acting.
              </p>
            </div>
            <div>
              <div className="stat-label text-ink-700">Data sources</div>
              <ul className="mt-3 space-y-1.5 text-sm text-ink-600">
                <li>DOL OFLC — LCA disclosures</li>
                <li>USCIS — H-1B employer datasets</li>
                <li>DOL WHD — enforcement outcomes</li>
                <li>BLS OEWS — wage benchmarks</li>
                <li>Federal &amp; state WARN Act notices</li>
              </ul>
            </div>
            <div>
              <div className="stat-label text-ink-700">Take action</div>
              <ul className="mt-3 space-y-1.5 text-sm">
                <li>
                  <Link className="link" href="/methodology">
                    Methodology &amp; limits
                  </Link>
                </li>
                <li>
                  <a
                    className="link"
                    href="https://www.dol.gov/agencies/whd/forms/wh4"
                    target="_blank"
                    rel="noreferrer"
                  >
                    File a DOL WH-4 complaint
                  </a>
                </li>
                <li>
                  <a
                    className="link"
                    href="https://www.uscis.gov/report-fraud"
                    target="_blank"
                    rel="noreferrer"
                  >
                    Report fraud to USCIS
                  </a>
                </li>
                <li>
                  <Link className="link" href="/api/v1/anomalies">
                    Developer API
                  </Link>
                </li>
              </ul>
            </div>
          </div>
          <div className="border-t border-ink-200/70">
            <div className="mx-auto flex max-w-7xl flex-col items-start justify-between gap-2 px-4 py-4 text-[11px] uppercase tracking-[0.16em] text-ink-400 md:flex-row md:items-center md:px-6">
              <span>Transparency Engine · built for reporters, researchers, and workers</span>
              <span className="font-mono normal-case tracking-normal">
                v0.1 · public beta
              </span>
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
