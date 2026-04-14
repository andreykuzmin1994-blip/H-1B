import type { Metadata } from 'next';
import './globals.css';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'H-1B Transparency & Accountability Engine',
  description:
    'Public-interest transparency tool surfacing anomalies in H-1B filings and mapping employer entity relationships.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="border-b border-gray-200 bg-white">
          <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
            <Link href="/" className="text-lg font-bold">
              H-1B Transparency
            </Link>
            <nav className="flex gap-4 text-sm">
              <Link href="/search">Search</Link>
              <Link href="/map">Map</Link>
              <Link href="/violators">Violators</Link>
              <Link href="/api/v1/anomalies" className="text-gray-500">
                API
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
        <footer className="mx-auto mt-16 max-w-7xl px-4 py-6 text-xs text-gray-500">
          Data sources: DOL OFLC, USCIS, DOL WHD, BLS OEWS. Analysis provided as a public-interest
          transparency tool. Not an official government service.
        </footer>
      </body>
    </html>
  );
}
