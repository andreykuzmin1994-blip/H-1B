import Link from 'next/link';
import { prisma } from '@/lib/db';
import { severityClass, severityLabel } from '@/lib/formatters';

export const dynamic = 'force-dynamic';

export default async function AddressPage({ params }: { params: { hash: string } }) {
  const [line1, city, state] = decodeURIComponent(params.hash).split('|');
  const employers = await prisma.employer.findMany({
    where: {
      address_line1: line1,
      city: city || undefined,
      state: state || undefined,
    },
    orderBy: { anomaly_score: 'desc' },
  });

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Entities at this address</h1>
      <p className="text-sm text-gray-600">
        {line1}
        {city && `, ${city}`}
        {state && `, ${state}`}
      </p>
      <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="bg-gray-50 text-left">
            <tr>
              <th className="px-3 py-2 font-medium">Employer</th>
              <th className="px-3 py-2 font-medium">NAICS</th>
              <th className="px-3 py-2 font-medium">Address type</th>
              <th className="px-3 py-2 font-medium">LCAs</th>
              <th className="px-3 py-2 font-medium">Score</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {employers.map((e) => (
              <tr key={e.id}>
                <td className="px-3 py-2">
                  <Link className="text-blue-700 hover:underline" href={`/employer/${e.id}`}>
                    {e.name}
                  </Link>
                </td>
                <td className="px-3 py-2">{e.naics_code}</td>
                <td className="px-3 py-2">{e.address_type ?? 'UNKNOWN'}</td>
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
      <p className="text-xs text-gray-500">
        Consider cross-referencing against{' '}
        <a className="underline" href={`https://fraudreporter.visadata.org/?q=${encodeURIComponent(line1 || '')}`}>
          visadata.org physical verification
        </a>
        .
      </p>
    </div>
  );
}
