import Link from 'next/link';
import { prisma } from '@/lib/db';
import {
  severityClass,
  severityDotClass,
  severityLabel,
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
    <div className="space-y-8">
      <div className="page-header">
        <div className="eyebrow">
          <span className="h-px w-6 bg-ember-500" /> Investigation
        </div>
        <h1>Search the H-1B filings index.</h1>
        <p>
          Look up any employer by name or city, filter by state or NAICS industry, or jump to a
          specific anomaly flag. Results are ordered by composite anomaly score.
        </p>
      </div>

      <form className="rounded-xl border border-ink-200 bg-white p-4 shadow-card md:p-5" method="get">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-12">
          <div className="md:col-span-5">
            <label className="stat-label">Employer / city</label>
            <input
              name="q"
              defaultValue={searchParams.q ?? ''}
              placeholder="e.g. Infosys, San Jose, Tata…"
              className="input mt-1.5"
            />
          </div>
          <div className="md:col-span-2">
            <label className="stat-label">State</label>
            <input
              name="state"
              defaultValue={searchParams.state ?? ''}
              placeholder="CA"
              maxLength={2}
              className="input mt-1.5 uppercase"
            />
          </div>
          <div className="md:col-span-2">
            <label className="stat-label">NAICS prefix</label>
            <input
              name="naics"
              defaultValue={searchParams.naics ?? ''}
              placeholder="5415"
              className="input mt-1.5"
            />
          </div>
          <div className="md:col-span-2">
            <label className="stat-label">Min score</label>
            <input
              name="minScore"
              type="number"
              min={0}
              max={100}
              defaultValue={searchParams.minScore ?? ''}
              placeholder="50"
              className="input mt-1.5"
            />
          </div>
          <div className="md:col-span-1 flex items-end">
            <button className="btn-primary w-full" type="submit">
              Search
            </button>
          </div>
          <div className="md:col-span-12">
            <label className="stat-label">Flag type (advanced)</label>
            <input
              name="flag"
              defaultValue={searchParams.flag ?? ''}
              placeholder="e.g. WAGE_BELOW_MEDIAN, ADDRESS_REUSE, DENIAL_SPIKE"
              className="input mt-1.5 font-mono text-xs"
            />
          </div>
        </div>
      </form>

      {hasFilters ? (
        <div className="flex items-center justify-between">
          <p className="text-sm text-ink-600">
            <span className="font-semibold text-ink-900">{results.length}</span> result
            {results.length === 1 ? '' : 's'} &middot; sorted by anomaly score
          </p>
          <Link href="/search" className="text-sm text-ink-500 hover:text-ember-600">
            Clear filters
          </Link>
        </div>
      ) : (
        <div className="rounded-xl border border-dashed border-ink-200 bg-white/60 p-8 text-center">
          <div className="eyebrow justify-center">
            <span className="h-px w-6 bg-ember-500" /> Tips
          </div>
          <p className="mx-auto mt-3 max-w-lg text-sm text-ink-600">
            Try searching for a familiar company, a suspicious staffing firm, or just the state
            where you live. Use the <span className="font-mono text-xs">Min score</span> filter to
            surface the most anomalous employers first.
          </p>
        </div>
      )}

      {hasFilters && (
        <div className="overflow-hidden rounded-xl border border-ink-200 bg-white shadow-card">
          <table className="data-table">
            <thead>
              <tr>
                <th>Employer</th>
                <th>City, State</th>
                <th>NAICS</th>
                <th className="text-right">LCAs</th>
                <th>Severity</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {results.map((e) => {
                const score = Number(e.anomaly_score);
                return (
                  <tr key={e.id} className="group">
                    <td>
                      <Link href={`/employer/${e.id}`} className="font-medium text-ink-900 hover:text-ember-600">
                        {e.name}
                      </Link>
                    </td>
                    <td className="text-ink-600">
                      {e.city}
                      {e.state ? `, ${e.state}` : ''}
                    </td>
                    <td className="num text-ink-600">{e.naics_code ?? '—'}</td>
                    <td className="num text-right">{e.total_lca_count?.toLocaleString() ?? '0'}</td>
                    <td>
                      <span className={`severity-badge ${severityClass(score)}`}>
                        <span className={`severity-dot ${severityDotClass(score)}`} />
                        {severityLabel(score)} · {score.toFixed(0)}
                      </span>
                    </td>
                    <td className="text-right">
                      <Link
                        href={`/compare?ids=${e.id}`}
                        className="text-xs text-ink-400 opacity-0 transition group-hover:opacity-100 hover:text-ember-600"
                      >
                        + compare
                      </Link>
                    </td>
                  </tr>
                );
              })}
              {results.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-sm text-ink-500">
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
