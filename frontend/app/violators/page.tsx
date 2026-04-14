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
    <div className="space-y-8">
      <div className="page-header">
        <div className="eyebrow">
          <span className="h-px w-6 bg-ember-500" /> Enforcement archive
        </div>
        <h1>Employers the government has already caught.</h1>
        <p>
          Every row is a documented outcome from DOL Wage & Hour Division investigations, USCIS
          enforcement referrals, or the DOL Willful Violator list. These are not accusations &mdash;
          they are resolved findings.
        </p>
      </div>

      <section className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <div className="stat stat-accent">
          <div className="stat-label">Violations shown</div>
          <div className="stat-value">{violations.length.toLocaleString()}</div>
          <div className="stat-sub">Most recent 200 outcomes</div>
        </div>
        <div className="stat stat-accent">
          <div className="stat-label">Distinct employers</div>
          <div className="stat-value">{uniqueEmployers.toLocaleString()}</div>
          <div className="stat-sub">Some appear more than once</div>
        </div>
        <div className="stat stat-accent">
          <div className="stat-label">Back wages + penalties</div>
          <div className="stat-value">{formatCurrency(totalBackWages + totalPenalty)}</div>
          <div className="stat-sub">
            {formatCurrency(totalBackWages)} wages · {formatCurrency(totalPenalty)} penalties
          </div>
        </div>
      </section>

      <div className="overflow-hidden rounded-xl border border-ink-200 bg-white shadow-card">
        <table className="data-table">
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
                    <Link
                      className="font-medium text-ink-900 hover:text-ember-600"
                      href={`/employer/${v.employer_id}`}
                    >
                      {v.employer?.name ?? v.employer_name_raw}
                    </Link>
                  ) : (
                    <span className="text-ink-700">{v.employer_name_raw}</span>
                  )}
                </td>
                <td>
                  <span className="rounded-md bg-ink-100 px-2 py-0.5 font-mono text-[11px] uppercase tracking-wider text-ink-700">
                    {v.source}
                  </span>
                </td>
                <td className="text-ink-700">{v.violation_type || '—'}</td>
                <td className="num text-ink-600">
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
