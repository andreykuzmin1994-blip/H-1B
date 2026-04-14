import Link from 'next/link';
import { prisma } from '@/lib/db';
import { formatCurrency } from '@/lib/formatters';

export const revalidate = 300;

export default async function ViolatorsPage() {
  const violations = await prisma.violation.findMany({
    orderBy: { violation_date: 'desc' },
    include: { employer: true },
    take: 200,
  });
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">H-1B violators & enforcement history</h1>
      <p className="text-sm text-gray-600">
        Employers with recorded DOL or USCIS enforcement outcomes, plus the DOL Willful Violator
        list.
      </p>
      <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="bg-gray-50 text-left">
            <tr>
              <th className="px-3 py-2 font-medium">Employer</th>
              <th className="px-3 py-2 font-medium">Source</th>
              <th className="px-3 py-2 font-medium">Violation</th>
              <th className="px-3 py-2 font-medium">Date</th>
              <th className="px-3 py-2 font-medium">Back wages</th>
              <th className="px-3 py-2 font-medium">Penalty</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {violations.map((v) => (
              <tr key={v.id}>
                <td className="px-3 py-2">
                  {v.employer_id ? (
                    <Link className="text-blue-700 hover:underline" href={`/employer/${v.employer_id}`}>
                      {v.employer?.name ?? v.employer_name_raw}
                    </Link>
                  ) : (
                    v.employer_name_raw
                  )}
                </td>
                <td className="px-3 py-2">{v.source}</td>
                <td className="px-3 py-2">{v.violation_type}</td>
                <td className="px-3 py-2">
                  {v.violation_date ? new Date(v.violation_date).toLocaleDateString() : ''}
                </td>
                <td className="px-3 py-2">
                  {v.back_wages_amount ? formatCurrency(Number(v.back_wages_amount)) : '-'}
                </td>
                <td className="px-3 py-2">
                  {v.penalty_amount ? formatCurrency(Number(v.penalty_amount)) : '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
