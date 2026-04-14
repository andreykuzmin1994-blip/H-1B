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

  // Count H-1B LCAs filed within +/- 90 days of each layoff for flagged employers.
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

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Layoffs with concurrent H-1B filings</h1>
      <p className="text-sm text-gray-600">
        Mass-layoff notices from federal and state WARN Act filings plus supplemental trackers,
        joined against the employer&rsquo;s H-1B LCA history. The &ldquo;Concurrent H-1B&rdquo;
        column counts LCAs filed within <strong>±{WINDOW_DAYS} days</strong> of the layoff &mdash;
        the INA &sect;&nbsp;212(n)(1)(E) non-displacement window that applies to H-1B-dependent
        employers.
      </p>
      <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="bg-gray-50 text-left">
            <tr>
              <th className="px-3 py-2 font-medium">Employer</th>
              <th className="px-3 py-2 font-medium">Location</th>
              <th className="px-3 py-2 font-medium">Effective</th>
              <th className="px-3 py-2 font-medium">Workers</th>
              <th className="px-3 py-2 font-medium">Concurrent H-1B</th>
              <th className="px-3 py-2 font-medium">Source</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {layoffs.map((l) => {
              const concurrent = concurrentCount(l);
              return (
                <tr key={l.id}>
                  <td className="px-3 py-2">
                    {l.employer ? (
                      <Link
                        className="text-blue-700 hover:underline"
                        href={`/employer/${l.employer.id}`}
                      >
                        {l.employer.name}
                      </Link>
                    ) : (
                      <span className="text-gray-700">{l.employer_name_raw}</span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    {[l.location_city, l.location_state].filter(Boolean).join(', ') || '-'}
                  </td>
                  <td className="px-3 py-2">
                    {l.effective_date
                      ? new Date(l.effective_date).toLocaleDateString()
                      : l.notice_date
                      ? new Date(l.notice_date).toLocaleDateString()
                      : '-'}
                  </td>
                  <td className="px-3 py-2">
                    {l.workers_affected ? l.workers_affected.toLocaleString() : '-'}
                  </td>
                  <td
                    className={`px-3 py-2 ${
                      concurrent > 0 ? 'font-semibold text-red-700' : 'text-gray-500'
                    }`}
                  >
                    {concurrent}
                  </td>
                  <td className="px-3 py-2">
                    {l.source_url ? (
                      <a
                        className="text-blue-700 hover:underline"
                        href={l.source_url}
                        rel="noreferrer"
                        target="_blank"
                      >
                        {l.source}
                      </a>
                    ) : (
                      l.source
                    )}
                  </td>
                </tr>
              );
            })}
            {layoffs.length === 0 && (
              <tr>
                <td className="px-3 py-4 text-gray-500" colSpan={6}>
                  No WARN / layoff notices ingested yet. Run{' '}
                  <code className="rounded bg-gray-100 px-1">python scripts/ingest.py warn</code>{' '}
                  with state WARN CSVs in{' '}
                  <code className="rounded bg-gray-100 px-1">data/raw/warn/&lt;state&gt;/</code>.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
