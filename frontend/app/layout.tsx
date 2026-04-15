import type { Metadata } from 'next';
import { Inter, Source_Serif_4, IBM_Plex_Mono } from 'next/font/google';
import './globals.css';
import Link from 'next/link';

const sans = Inter({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-sans',
});
const serif = Source_Serif_4({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-serif',
});
const mono = IBM_Plex_Mono({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-mono',
  weight: ['400', '500'],
});

export const metadata: Metadata = {
  title: 'H-1B Transparency & Accountability Engine',
  description:
    'A public-interest investigation tool that surfaces anomalies in H-1B filings, maps employer entity networks, and generates formatted enforcement tips.',
};

const NAV: { href: string; label: string }[] = [
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
      <body>
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:bg-ink-900 focus:px-3 focus:py-2 focus:text-paper"
        >
          Skip to content
        </a>

        <header className="border-b-2 border-ink-900">
          <div className="mx-auto max-w-[1100px] px-6">
            <div className="flex items-center justify-between pt-6 pb-3">
              <span className="dateline">Vol. 1 · Public beta</span>
              <span className="dateline">
                {new Date().toLocaleDateString('en-US', {
                  weekday: 'long',
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric',
                })}
              </span>
            </div>
            <Link
              href="/"
              className="block pb-3 font-serif text-[40px] font-semibold leading-none tracking-[-0.03em] md:text-[54px]"
            >
              The H-1B Transparency Engine
            </Link>
            <p className="pb-5 text-sm italic text-ink-600">
              A public-interest accountability project. Not an official government service.
            </p>
          </div>
          <nav className="border-t border-ink-900">
            <div className="mx-auto flex max-w-[1100px] flex-wrap items-center gap-x-6 gap-y-1 px-6 py-2 text-[13px] text-ink-800">
              {NAV.map((n) => (
                <Link key={n.href} href={n.href} className="hover:text-accent">
                  {n.label}
                </Link>
              ))}
              <Link
                href="/api/v1/anomalies"
                className="ml-auto font-mono text-[11px] uppercase tracking-wider text-ink-500 hover:text-accent"
              >
                API
              </Link>
            </div>
          </nav>
        </header>

        <main id="main" className="mx-auto max-w-[1100px] px-6 py-12">
          {children}
        </main>

        <footer className="mt-24 border-t-2 border-ink-900">
          <div className="mx-auto max-w-[1100px] px-6 py-10">
            <div className="grid grid-cols-1 gap-10 md:grid-cols-12">
              <div className="md:col-span-5">
                <p className="font-serif text-xl leading-snug">
                  A reader-supported accountability project that joins federal labor,
                  immigration, and enforcement records into a single investigative tool.
                </p>
                <p className="mt-4 text-xs text-ink-500">
                  Findings are computed from public datasets and may contain errors. Always
                  verify against primary sources before acting.
                </p>
              </div>
              <div className="md:col-span-3">
                <div className="caps mb-3 text-ink-500">Primary sources</div>
                <ul className="space-y-1 text-sm text-ink-800">
                  <li>DOL OFLC — LCA disclosures</li>
                  <li>USCIS — H-1B employer data</li>
                  <li>DOL WHD — enforcement outcomes</li>
                  <li>BLS OEWS — wage benchmarks</li>
                  <li>Federal &amp; state WARN Act</li>
                </ul>
              </div>
              <div className="md:col-span-4">
                <div className="caps mb-3 text-ink-500">Take action</div>
                <ul className="space-y-1.5 text-sm">
                  <li>
                    <Link className="link" href="/methodology">
                      Methodology and limits
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
            <div className="mt-10 flex items-baseline justify-between border-t border-ink-200 pt-4">
              <span className="text-xs text-ink-500">
                Built by and for reporters, researchers, and workers.
              </span>
              <span className="font-mono text-[11px] uppercase tracking-wider text-ink-400">
                v0.1
              </span>
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
