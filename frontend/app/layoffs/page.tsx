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
    <div className="space-y-8">
      <div className="page-header">
        <div className="eyebrow">
          <span className="h-px w-6 bg-ember-500" /> Displacement watch
        </div>
        <h1>Who laid off workers &mdash; then filed H-1B petitions?</h1>
        <p>
          Mass-layoff notices from federal and state WARN Act filings joined against each
          employer&rsquo;s H-1B LCA history. The <em>Concurrent H-1B</em> column counts LCAs filed
          within <strong>±{WINDOW_DAYS} days</strong> of the layoff &mdash; the INA &sect;&nbsp;212(n)(1)(E)
          non-displacement window that applies to H-1B-dependent employers.
        </p>
      </div>

      <section className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <div className="stat stat-accent">
          <div className="stat-label">Layoff events</div>
          <div className="stat-value">{layoffs.length.toLocaleString()}</div>
          <div className="stat-sub">Most recent 200 WARN filings</div>
        </div>
        <div className="stat stat-accent">
          <div className="stat-label">Workers affected</div>
          <div className="stat-value">{totalWorkers.toLocaleString()}</div>
          <div className="stat-sub">Across all events shown</div>
        </div>
        <div className="stat stat-accent">
          <div className="stat-label">With concurrent H-1B filings</div>
          <div className="stat-value text-ember-600">{redFlagCount}</div>
          <div className="stat-sub">Within ±{WINDOW_DAYS} days of the layoff</div>
        </div>
      </section>

      <div className="overflow-hidden rounded-xl border border-ink-200 bg-white shadow-card">
        <table className="data-table">
          <thead>
            <tr>
              <th>Employer</th>
              <th>Location</th>
              <th>Effective</th>
              <th className="text-right">Workers</th>
              <th className="text-right">Concurrent H-1B</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {layoffs.map((l) => {
              const concurrent = concurrentCount(l);
              return (
                <tr key={l.id} className={concurrent > 0 ? 'bg-red-50/40' : undefined}>
                  <td>
                    {l.employer ? (
                      <Link
                        className="font-medium text-ink-900 hover:text-ember-600"
                        href={`/employer/${l.employer.id}`}
                      >
                        {l.employer.name}
                      </Link>
                    ) : (
                      <span className="text-ink-700">{l.employer_name_raw}</span>
                    )}
                  </td>
                  <td className="text-ink-600">
                    {[l.location_city, l.location_state].filter(Boolean).join(', ') || '—'}
                  </td>
                  <td className="num text-ink-600">
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
                      concurrent > 0 ? 'font-semibold text-red-700' : 'text-ink-400'
                    }`}
                  >
                    {concurrent > 0 ? (
                      <span className="inline-flex items-center gap-1.5">
                        <span className="severity-dot bg-red-600 animate-pulseDot" />
                        {concurrent}
                      </span>
                    ) : (
                      '0'
                    )}
                  </td>
                  <td>
                    {l.source_url ? (
                      <a
                        className="font-mono text-[11px] uppercase tracking-wider text-ink-700 hover:text-ember-600"
                        href={l.source_url}
                        rel="noreferrer"
                        target="_blank"
                      >
                        {l.source} ↗
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
                  No WARN / layoff notices ingested yet. Run{' '}
                  <code className="rounded bg-ink-100 px-1.5 py-0.5 text-xs">
                    python scripts/ingest.py warn
                  </code>{' '}
                  with state WARN CSVs in{' '}
                  <code className="rounded bg-ink-100 px-1.5 py-0.5 text-xs">
                    data/raw/warn/&lt;state&gt;/
                  </code>
                  .
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
