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

  const totalBackWages = violations.reduce(
    (s, v) => s + Number(v.back_wages_amount ?? 0),
    0,
  );
  const totalPenalty = violations.reduce(
    (s, v) => s + Number(v.penalty_amount ?? 0),
    0,
  );
  const uniqueEmployers = new Set(
    violations.map((v) => v.employer_id ?? v.employer_name_raw).filter(Boolean),
  ).size;

  return (
    <div className="space-y-10">
      <header className="md:grid md:grid-cols-12 md:gap-10">
        <div className="md:col-span-8">
          <div className="dateline">Enforcement record</div>
          <h1 className="mt-3 font-serif">
            The employers the government has already caught.
          </h1>
          <p className="mt-3 max-w-[65ch] text-[15px] leading-[1.55] text-ink-700">
            Every row below is a documented outcome from a Department of Labor Wage &amp; Hour
            investigation, a USCIS enforcement referral, or the DOL Willful Violator list. These
            are not allegations. They are resolved findings.
          </p>
        </div>
        <aside className="mt-8 md:col-span-4 md:mt-0">
          <div className="border-t-2 border-ink-900 pt-3">
            <dl className="space-y-3 text-sm">
              <SidebarStat
                label="Resolved violations"
                value={violations.length.toLocaleString()}
              />
              <SidebarStat
                label="Distinct employers"
                value={uniqueEmployers.toLocaleString()}
              />
              <SidebarStat
                label="Back wages"
                value={formatCurrency(totalBackWages)}
              />
              <SidebarStat label="Penalties" value={formatCurrency(totalPenalty)} />
            </dl>
          </div>
        </aside>
      </header>

      <div className="overflow-x-auto">
        <table className="ledger">
          <thead>
            <tr>
              <th>Employer</th>
              <th>Source</th>
              <th>Violation</th>
              <th>Date</th>
              <th className="text-right">Back wages</th>
              <th className="text-right">Penalty</th>
            </tr>
          </thead>
          <tbody>
            {violations.map((v) => (
              <tr key={v.id}>
                <td>
                  {v.employer_id ? (
                    <Link href={`/employer/${v.employer_id}`} className="link">
                      {v.employer?.name ?? v.employer_name_raw}
                    </Link>
                  ) : (
                    <span className="text-ink-800">{v.employer_name_raw}</span>
                  )}
                </td>
                <td>
                  <span className="font-mono text-[11px] uppercase tracking-wider text-ink-600">
                    {v.source}
                  </span>
                </td>
                <td className="text-ink-700">{v.violation_type || '—'}</td>
                <td className="num">
                  {v.violation_date ? new Date(v.violation_date).toLocaleDateString() : '—'}
                </td>
                <td className="num text-right">
                  {v.back_wages_amount ? formatCurrency(Number(v.back_wages_amount)) : '—'}
                </td>
                <td className="num text-right">
                  {v.penalty_amount ? formatCurrency(Number(v.penalty_amount)) : '—'}
                </td>
              </tr>
            ))}
            {violations.length === 0 && (
              <tr>
                <td colSpan={6} className="py-10 text-center text-sm text-ink-500">
                  No enforcement records ingested yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SidebarStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between border-b border-ink-100 pb-1.5">
      <dt className="text-ink-600">{label}</dt>
      <dd className="font-mono text-sm tabular text-ink-900">{value}</dd>
    </div>
  );
}
