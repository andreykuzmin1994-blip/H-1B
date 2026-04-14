import Link from 'next/link';
import { prisma } from '@/lib/db';
import { severityClass, severityLabel } from '@/lib/formatters';

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
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Employer search</h1>
      <form className="grid grid-cols-1 gap-2 md:grid-cols-6" method="get">
        <input
          name="q"
          defaultValue={searchParams.q ?? ''}
          placeholder="Name, city, keyword"
          className="rounded border border-gray-300 px-3 py-2 text-sm md:col-span-2"
        />
        <input
          name="state"
          defaultValue={searchParams.state ?? ''}
          placeholder="State (2-char)"
          maxLength={2}
          className="rounded border border-gray-300 px-3 py-2 text-sm"
        />
        <input
          name="naics"
          defaultValue={searchParams.naics ?? ''}
          placeholder="NAICS prefix"
          className="rounded border border-gray-300 px-3 py-2 text-sm"
        />
        <input
          name="minScore"
          type="number"
          min={0}
          max={100}
          defaultValue={searchParams.minScore ?? ''}
          placeholder="Min score"
          className="rounded border border-gray-300 px-3 py-2 text-sm"
        />
        <input
          name="flag"
          defaultValue={searchParams.flag ?? ''}
          placeholder="Flag type"
          className="rounded border border-gray-300 px-3 py-2 text-sm"
        />
        <button
          className="rounded bg-blue-600 px-4 py-2 text-sm text-white md:col-span-6"
          type="submit"
        >
          Search
        </button>
      </form>
      {hasFilters && (
        <div className="text-sm text-gray-600">
          {results.length} result{results.length === 1 ? '' : 's'}
        </div>
      )}
      <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="bg-gray-50 text-left">
            <tr>
              <th className="px-3 py-2 font-medium">Employer</th>
              <th className="px-3 py-2 font-medium">City, State</th>
              <th className="px-3 py-2 font-medium">NAICS</th>
              <th className="px-3 py-2 font-medium">LCAs</th>
              <th className="px-3 py-2 font-medium">Score</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {results.map((e) => (
              <tr key={e.id} className="hover:bg-gray-50">
                <td className="px-3 py-2">
                  <Link className="text-blue-700 hover:underline" href={`/employer/${e.id}`}>
                    {e.name}
                  </Link>
                </td>
                <td className="px-3 py-2">
                  {e.city}, {e.state}
                </td>
                <td className="px-3 py-2">{e.naics_code}</td>
                <td className="px-3 py-2">{e.total_lca_count}</td>
                <td className="px-3 py-2">
                  <span className={`severity-badge ${severityClass(Number(e.anomaly_score))}`}>
                    {severityLabel(Number(e.anomaly_score))} · {Number(e.anomaly_score).toFixed(0)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
