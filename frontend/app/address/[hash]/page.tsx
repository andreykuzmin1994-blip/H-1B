import Link from 'next/link';
import { prisma } from '@/lib/db';
import {
  severityClass,
  severityLabel,
  severityMarkClass,
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
    <div className="space-y-10">
      <header>
        <div className="dateline">Shared address</div>
        <h1 className="mt-3 font-serif">Entities sharing a single address.</h1>
        <p className="mt-3 max-w-[65ch] text-[15px] leading-[1.55] text-ink-700">
          Multiple employers registered at one street address can indicate shell companies, PEO
          stacks, or mail drops used to multiply H-1B cap registrations. Context matters — these
          arrangements are also common in co-working spaces and corporate agents.
        </p>
        <p className="mt-4 font-mono text-sm text-ink-900">
          {line1}
          {city && `, ${city}`}
          {state && `, ${state}`}
        </p>
      </header>

      <div className="overflow-x-auto">
        <table className="ledger">
          <thead>
            <tr>
              <th>Employer</th>
              <th>NAICS</th>
              <th>Address type</th>
              <th className="text-right">LCAs</th>
              <th>Severity</th>
              <th className="text-right">Score</th>
            </tr>
          </thead>
          <tbody>
            {employers.map((e) => {
              const score = Number(e.anomaly_score);
              return (
                <tr key={e.id}>
                  <td>
                    <Link href={`/employer/${e.id}`} className="link">
                      {e.name}
                    </Link>
                  </td>
                  <td className="num">{e.naics_code ?? '—'}</td>
                  <td className="text-ink-700">{e.address_type ?? 'Unknown'}</td>
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
                </tr>
              );
            })}
            {employers.length === 0 && (
              <tr>
                <td colSpan={6} className="py-10 text-center text-sm text-ink-500">
                  No other entities on file at this address.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <p className="text-xs italic text-ink-500">
        Cross-reference against{' '}
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
