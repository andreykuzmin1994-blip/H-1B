import Link from 'next/link';
import { prisma } from '@/lib/db';
import {
  severityClass,
  severityLabel,
  severityMarkClass,
} from '@/lib/formatters';

export const dynamic = 'force-dynamic';

interface SearchParams {
  q?: string;
  state?: string;
  naics?: string;
  minScore?: string;
  flag?: string;
}

async function search({ q, state, naics, minScore, flag }: SearchParams) {
  const anyFilter = q || state || naics || minScore || flag;
  if (!anyFilter) return [];

  const where: any = {};
  if (q) {
    where.OR = [
      { name: { contains: q, mode: 'insensitive' } },
      { name_normalized: { contains: q.toUpperCase() } },
      { city: { contains: q, mode: 'insensitive' } },
    ];
  }
  if (state) where.state = state.toUpperCase().slice(0, 2);
  if (naics) where.naics_code = { startsWith: naics };
  if (minScore) {
    const n = Number(minScore);
    if (Number.isFinite(n)) where.anomaly_score = { gte: n };
  }
  if (flag) where.flags = { some: { flag_type: flag } };

  return prisma.employer.findMany({
    where,
    orderBy: { anomaly_score: 'desc' },
    take: 100,
  });
}

export default async function SearchPage({ searchParams }: { searchParams: SearchParams }) {
  const results = await search(searchParams);
  const hasFilters = Boolean(
    searchParams.q ||
      searchParams.state ||
      searchParams.naics ||
      searchParams.minScore ||
      searchParams.flag,
  );

  return (
    <div className="space-y-10">
      <header>
        <div className="dateline">Investigation</div>
        <h1 className="mt-3 font-serif">Search the filings index.</h1>
        <p className="mt-3 max-w-[65ch] text-[15px] leading-[1.55] text-ink-700">
          Look up any employer by name, city, state, or NAICS industry. Results are sorted by
          composite anomaly score. A score is a lead, not a verdict.
        </p>
      </header>

      <form method="get" className="border-t-2 border-ink-900 pt-4">
        <div className="grid grid-cols-1 gap-x-6 gap-y-4 md:grid-cols-12">
          <div className="md:col-span-5">
            <label className="field-label">Employer or city</label>
            <input
              name="q"
              defaultValue={searchParams.q ?? ''}
              placeholder="Infosys, San Jose, Tata…"
              className="field"
            />
          </div>
          <div className="md:col-span-2">
            <label className="field-label">State</label>
            <input
              name="state"
              defaultValue={searchParams.state ?? ''}
              placeholder="CA"
              maxLength={2}
              className="field uppercase"
            />
          </div>
          <div className="md:col-span-2">
            <label className="field-label">NAICS</label>
            <input
              name="naics"
              defaultValue={searchParams.naics ?? ''}
              placeholder="5415"
              className="field"
            />
          </div>
          <div className="md:col-span-2">
            <label className="field-label">Min score</label>
            <input
              name="minScore"
              type="number"
              min={0}
              max={100}
              defaultValue={searchParams.minScore ?? ''}
              placeholder="50"
              className="field"
            />
          </div>
          <div className="md:col-span-1 flex items-end">
            <button className="btn btn-primary w-full" type="submit">
              Search
            </button>
          </div>
          <div className="md:col-span-12">
            <label className="field-label">Flag type</label>
            <input
              name="flag"
              defaultValue={searchParams.flag ?? ''}
              placeholder="WAGE_BELOW_MEDIAN, ADDRESS_REUSE, DENIAL_SPIKE…"
              className="field font-mono text-[13px]"
            />
          </div>
        </div>
      </form>

      {hasFilters ? (
        <div className="flex items-baseline justify-between text-sm">
          <p className="text-ink-700">
            <span className="tabular font-semibold text-ink-900">{results.length}</span>{' '}
            result{results.length === 1 ? '' : 's'}, sorted by anomaly score.
          </p>
          <Link href="/search" className="btn-text text-sm">
            Clear filters
          </Link>
        </div>
      ) : (
        <p className="max-w-[65ch] text-sm italic text-ink-600">
          Try a familiar company, a suspicious staffing firm, or the state where you live.
          Raise <span className="font-mono text-xs">Min score</span> to surface the most
          anomalous employers first.
        </p>
      )}

      {hasFilters && (
        <div className="overflow-x-auto">
          <table className="ledger">
            <thead>
              <tr>
                <th>Employer</th>
                <th>Location</th>
                <th>NAICS</th>
                <th className="text-right">LCAs</th>
                <th>Severity</th>
                <th className="text-right">Score</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {results.map((e) => {
                const score = Number(e.anomaly_score);
                return (
                  <tr key={e.id}>
                    <td>
                      <Link href={`/employer/${e.id}`} className="link">
                        {e.name}
                      </Link>
                    </td>
                    <td className="text-ink-700">
                      {e.city}
                      {e.state ? `, ${e.state}` : ''}
                    </td>
                    <td className="num">{e.naics_code ?? '—'}</td>
                    <td className="num text-right">
                      {e.total_lca_count?.toLocaleString() ?? '0'}
                    </td>
                    <td>
                      <span className={`sev ${severityClass(score)}`}>
                        <span className={`sev-mark ${severityMarkClass(score)}`} />
                        {severityLabel(score)}
                      </span>
                    </td>
                    <td className="num text-right">{score.toFixed(0)}</td>
                    <td className="text-right">
                      <Link
                        href={`/compare?ids=${e.id}`}
                        className="text-xs text-ink-500 hover:text-accent"
                      >
                        compare
                      </Link>
                    </td>
                  </tr>
                );
              })}
              {results.length === 0 && (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-sm text-ink-500">
                    No matches. Try loosening your filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
