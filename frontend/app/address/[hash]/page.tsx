import Link from 'next/link';
import { prisma } from '@/lib/db';
import {
  severityClass,
  severityDotClass,
  severityLabel,
} from '@/lib/formatters';

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
    <div className="space-y-8">
      <div className="page-header">
        <div className="eyebrow">
          <span className="h-px w-6 bg-ember-500" /> Shared address
        </div>
        <h1>Entities sharing one address.</h1>
        <p>
          Multiple employers registered at the same street address can indicate shell companies,
          PEO stacks, or mail drops used to multiply H-1B cap registrations.
        </p>
        <p className="font-mono text-sm text-ink-700">
          {line1}
          {city && `, ${city}`}
          {state && `, ${state}`}
        </p>
      </div>

      <div className="overflow-hidden rounded-xl border border-ink-200 bg-white shadow-card">
        <table className="data-table">
          <thead>
            <tr>
              <th>Employer</th>
              <th>NAICS</th>
              <th>Address type</th>
              <th className="text-right">LCAs</th>
              <th>Severity</th>
            </tr>
          </thead>
          <tbody>
            {employers.map((e) => {
              const score = Number(e.anomaly_score);
              return (
                <tr key={e.id}>
                  <td>
                    <Link
                      className="font-medium text-ink-900 hover:text-ember-600"
                      href={`/employer/${e.id}`}
                    >
                      {e.name}
                    </Link>
                  </td>
                  <td className="num text-ink-600">{e.naics_code ?? '—'}</td>
                  <td className="text-ink-600">{e.address_type ?? 'UNKNOWN'}</td>
                  <td className="num text-right">{e.total_lca_count?.toLocaleString() ?? '0'}</td>
                  <td>
                    <span className={`severity-badge ${severityClass(score)}`}>
                      <span className={`severity-dot ${severityDotClass(score)}`} />
                      {severityLabel(score)} · {score.toFixed(0)}
                    </span>
                  </td>
                </tr>
              );
            })}
            {employers.length === 0 && (
              <tr>
                <td colSpan={5} className="py-10 text-center text-sm text-ink-500">
                  No other entities found at this address.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-ink-500">
        Consider cross-referencing against{' '}
        <a
          className="link"
          href={`https://fraudreporter.visadata.org/?q=${encodeURIComponent(line1 || '')}`}
        >
          visadata.org physical verification
        </a>
        .
      </p>
    </div>
  );
}
