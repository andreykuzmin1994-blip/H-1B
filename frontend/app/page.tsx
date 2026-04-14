import Link from 'next/link';
import { prisma } from '@/lib/db';
import { severityClass, severityLabel } from '@/lib/formatters';

export const revalidate = 300;

async function getStats() {
  const [employers, filings, violations, flagged] = await Promise.all([
    prisma.employer.count(),
    prisma.lcaFiling.count(),
    prisma.violation.count(),
    prisma.employer.count({ where: { anomaly_score: { gte: 50 } } }),
  ]);
  return { employers, filings, violations, flagged };
}

async function getTopFlagged() {
  return prisma.employer.findMany({
    where: { anomaly_score: { gt: 0 } },
    orderBy: { anomaly_score: 'desc' },
    take: 20,
  });
}

export default async function HomePage() {
  const [stats, top] = await Promise.all([getStats(), getTopFlagged()]);
  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-2xl font-bold">H-1B Transparency & Accountability Engine</h1>
        <p className="mt-2 max-w-3xl text-sm text-gray-600">
          A public-interest tool that connects DOL OFLC LCA disclosure data, USCIS H-1B employer
          data, DOL WHD enforcement records, and BLS OEWS wage benchmarks into a single system
          that surfaces anomalies, maps entity relationships, and generates formatted enforcement
          tips.
        </p>
      </section>

      <section className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label="Employers tracked" value={stats.employers.toLocaleString()} />
        <Stat label="LCA filings" value={stats.filings.toLocaleString()} />
        <Stat label="Enforcement records" value={stats.violations.toLocaleString()} />
        <Stat label="Flagged (score ≥ 50)" value={stats.flagged.toLocaleString()} />
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">Top flagged employers</h2>
        <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50 text-left">
              <tr>
                <th className="px-3 py-2 font-medium">Employer</th>
                <th className="px-3 py-2 font-medium">State</th>
                <th className="px-3 py-2 font-medium">NAICS</th>
                <th className="px-3 py-2 font-medium">LCAs</th>
                <th className="px-3 py-2 font-medium">Score</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {top.map((e) => (
                <tr key={e.id} className="hover:bg-gray-50">
                  <td className="px-3 py-2">
                    <Link className="text-blue-700 hover:underline" href={`/employer/${e.id}`}>
                      {e.name}
                    </Link>
                  </td>
                  <td className="px-3 py-2">{e.state}</td>
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
      </section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="card">
      <div className="text-xs uppercase tracking-wider text-gray-500">{label}</div>
      <div className="mt-1 text-2xl font-bold">{value}</div>
    </div>
  );
}
