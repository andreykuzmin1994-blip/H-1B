import Link from 'next/link';
import { prisma } from '@/lib/db';

/**
 * Small "last updated" indicator that sits in the site header. Gives readers
 * an at-a-glance sense of data freshness before they trust the numbers.
 *
 * Server component: reads once per request. `revalidate` on the layout caches
 * the response.
 */
export async function FreshnessPing() {
  const row = await prisma.lcaFiling.findFirst({
    orderBy: { received_date: 'desc' },
    select: { received_date: true },
  });
  const d = row?.received_date;
  const label = d ? humanize(d) : 'pending';
  return (
    <Link
      href="/methodology"
      title="How this data is computed"
      className="hidden items-center gap-2 rounded-full border border-ink-200/80 bg-white/80 px-3 py-1 text-[11px] font-medium text-ink-600 hover:border-ember-500/50 hover:text-ember-600 lg:inline-flex"
    >
      <span className="relative flex h-2 w-2">
        <span className="absolute inset-0 rounded-full bg-lime-500 animate-pulseDot" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-lime-600" />
      </span>
      <span className="uppercase tracking-[0.14em]">Data · {label}</span>
    </Link>
  );
}

function humanize(d: Date): string {
  const delta = Math.floor(
    (Date.now() - new Date(d).getTime()) / (1000 * 60 * 60 * 24),
  );
  if (delta <= 0) return 'today';
  if (delta === 1) return 'yesterday';
  if (delta < 30) return `${delta}d ago`;
  if (delta < 365) return `${Math.floor(delta / 30)}mo ago`;
  return `${Math.floor(delta / 365)}y ago`;
}
