import Link from 'next/link';
import { prisma } from '@/lib/db';
import { severityClass, severityLabel } from '@/lib/formatters';

export const dynamic = 'force-dynamic';

async function search(q: string) {
  if (!q) return [];
  return prisma.employer.findMany({
    where: {
      OR: [
        { name: { contains: q, mode: 'insensitive' } },
        { name_normalized: { contains: q.toUpperCase() } },
        { city: { contains: q, mode: 'insensitive' } },
      ],
    },
    orderBy: { anomaly_score: 'desc' },
    take: 50,
  });
}

export default async function SearchPage({ searchParams }: { searchParams: { q?: string } }) {
  const q = (searchParams.q || '').trim();
  const results = await search(q);

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Employer search</h1>
      <form className="flex gap-2" method="get">
        <input
          name="q"
          defaultValue={q}
          placeholder="Employer name, city, or keyword"
          className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
        />
        <button className="rounded bg-blue-600 px-4 py-2 text-sm text-white" type="submit">
          Search
        </button>
      </form>
      {q && (
        <div className="text-sm text-gray-600">
          {results.length} result{results.length === 1 ? '' : 's'} for &ldquo;{q}&rdquo;
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
