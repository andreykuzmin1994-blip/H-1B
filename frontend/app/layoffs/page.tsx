import Link from 'next/link';
import { prisma } from '@/lib/db';

export const revalidate = 300;

const DAY_MS = 24 * 60 * 60 * 1000;
const WINDOW_DAYS = 90;

type LayoffRow = {
  id: number;
  employer_id: number | null;
  employer_name_raw: string | null;
  source: string;
  notice_date: Date | null;
  effective_date: Date | null;
  workers_affected: number | null;
  location_city: string | null;
  location_state: string | null;
  reason: string | null;
  source_url: string | null;
  employer: { id: number; name: string } | null;
};

export default async function LayoffsPage() {
  const layoffs = (await prisma.layoffEvent.findMany({
    orderBy: [{ effective_date: 'desc' }, { notice_date: 'desc' }],
    include: { employer: { select: { id: true, name: true } } },
    take: 200,
  })) as LayoffRow[];

  const employerIds = Array.from(
    new Set(layoffs.map((l) => l.employer_id).filter((v): v is number => v !== null)),
  );
  const filings = employerIds.length
    ? await prisma.lcaFiling.findMany({
        where: { employer_id: { in: employerIds } },
        select: { employer_id: true, received_date: true },
      })
    : [];
  const filingsByEmployer = new Map<number, Date[]>();
  for (const f of filings) {
    if (!f.employer_id || !f.received_date) continue;
    const arr = filingsByEmployer.get(f.employer_id) ?? [];
    arr.push(f.received_date);
    filingsByEmployer.set(f.employer_id, arr);
  }

  function concurrentCount(row: LayoffRow): number {
    if (!row.employer_id) return 0;
    const pivot = row.effective_date ?? row.notice_date;
    if (!pivot) return 0;
    const dates = filingsByEmployer.get(row.employer_id) ?? [];
    const pivotMs = pivot.getTime();
    return dates.filter(
      (d) => Math.abs(d.getTime() - pivotMs) <= WINDOW_DAYS * DAY_MS,
    ).length;
  }

  const totalWorkers = layoffs.reduce((s, l) => s + (l.workers_affected ?? 0), 0);
  const redFlagCount = layoffs.filter((l) => concurrentCount(l) > 0).length;

  return (
    <div className="space-y-10">
      <header className="md:grid md:grid-cols-12 md:gap-10">
        <div className="md:col-span-8">
          <div className="dateline">Displacement watch</div>
          <h1 className="mt-3 font-serif">
            Who laid off workers, then filed H-1B petitions.
          </h1>
          <p className="mt-3 max-w-[65ch] text-[15px] leading-[1.55] text-ink-700">
            Mass-layoff notices from federal and state WARN Act filings, joined against each
            employer&rsquo;s H-1B LCA history. The <em>Concurrent</em> column counts LCAs filed
            within ±{WINDOW_DAYS} days of the layoff &mdash; the INA §212(n)(1)(E) non-displacement
            window for H-1B-dependent employers.
          </p>
        </div>
        <aside className="mt-8 md:col-span-4 md:mt-0">
          <div className="border-t-2 border-ink-900 pt-3">
            <dl className="space-y-3 text-sm">
              <SidebarStat label="Layoff events" value={layoffs.length.toLocaleString()} />
              <SidebarStat label="Workers affected" value={totalWorkers.toLocaleString()} />
              <SidebarStat
                label="With concurrent H-1B"
                value={redFlagCount.toString()}
                accent
              />
            </dl>
          </div>
        </aside>
      </header>

      <div className="overflow-x-auto">
        <table className="ledger">
          <thead>
            <tr>
              <th>Employer</th>
              <th>Location</th>
              <th>Effective</th>
              <th className="text-right">Workers</th>
              <th className="text-right">Concurrent</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {layoffs.map((l) => {
              const concurrent = concurrentCount(l);
              return (
                <tr key={l.id}>
                  <td>
                    {l.employer ? (
                      <Link href={`/employer/${l.employer.id}`} className="link">
                        {l.employer.name}
                      </Link>
                    ) : (
                      <span className="text-ink-800">{l.employer_name_raw}</span>
                    )}
                  </td>
                  <td className="text-ink-700">
                    {[l.location_city, l.location_state].filter(Boolean).join(', ') || '—'}
                  </td>
                  <td className="num">
                    {l.effective_date
                      ? new Date(l.effective_date).toLocaleDateString()
                      : l.notice_date
                      ? new Date(l.notice_date).toLocaleDateString()
                      : '—'}
                  </td>
                  <td className="num text-right">
                    {l.workers_affected ? l.workers_affected.toLocaleString() : '—'}
                  </td>
                  <td
                    className={`num text-right ${
                      concurrent > 0 ? 'font-semibold text-accent' : 'text-ink-400'
                    }`}
                  >
                    {concurrent}
                  </td>
                  <td>
                    {l.source_url ? (
                      <a
                        className="font-mono text-[11px] uppercase tracking-wider text-ink-700 hover:text-accent"
                        href={l.source_url}
                        rel="noreferrer"
                        target="_blank"
                      >
                        {l.source}
                      </a>
                    ) : (
                      <span className="font-mono text-[11px] uppercase tracking-wider text-ink-600">
                        {l.source}
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
            {layoffs.length === 0 && (
              <tr>
                <td colSpan={6} className="py-10 text-center text-sm text-ink-500">
                  No WARN notices ingested yet. Run{' '}
                  <code className="font-mono text-xs">python scripts/ingest.py warn</code>.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SidebarStat({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between border-b border-ink-100 pb-1.5">
      <dt className="text-ink-600">{label}</dt>
      <dd
        className={`font-mono text-sm tabular ${
          accent ? 'text-accent' : 'text-ink-900'
        }`}
      >
        {value}
      </dd>
    </div>
  );
}
