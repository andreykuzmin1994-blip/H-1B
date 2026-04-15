import Link from 'next/link';
import { prisma } from '@/lib/db';
import {
  severityClass,
  severityMarkClass,
  severityLabel,
} from '@/lib/formatters';

export const revalidate = 300;

async function getStats() {
  const [employers, filings, violations, flagged, backWagesAgg] = await Promise.all([
    prisma.employer.count(),
    prisma.lcaFiling.count(),
    prisma.violation.count(),
    prisma.employer.count({ where: { anomaly_score: { gte: 50 } } }),
    prisma.violation.aggregate({ _sum: { back_wages_amount: true } }),
  ]);
  return {
    employers,
    filings,
    violations,
    flagged,
    backWages: Number(backWagesAgg._sum.back_wages_amount ?? 0),
  };
}

async function getTopFlagged() {
  return prisma.employer.findMany({
    where: { anomaly_score: { gt: 0 } },
    orderBy: { anomaly_score: 'desc' },
    take: 15,
  });
}

function compactNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return n.toLocaleString();
}

function compactCurrency(n: number): string {
  if (!n) return '—';
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(0)}k`;
  return `$${n.toLocaleString()}`;
}

export default async function HomePage() {
  const [stats, top] = await Promise.all([getStats(), getTopFlagged()]);

  return (
    <div className="space-y-16">
      {/* ---------- LEDE ---------- */}
      <article className="grid grid-cols-1 gap-10 md:grid-cols-12">
        <div className="md:col-span-8">
          <div className="caps text-ink-500">The investigation</div>
          <h1 className="mt-2 font-serif text-ink-900">
            Who is gaming the H-1B system, and who is paying for it.
          </h1>
          <p className="dropcap mt-6 text-[17px] leading-[1.55] text-ink-800">
            This project joins Department of Labor wage disclosures, USCIS petition outcomes,
            Wage &amp; Hour Division enforcement records, BLS wage benchmarks, and federal and
            state layoff notices into a single investigative index. It finds employers whose
            filings, pay, denials, and firings tell a story the official datasets alone do not.
            Every number on this site links to the document that produced it.
          </p>
          <p className="mt-5 max-w-[65ch] text-[15px] leading-[1.6] text-ink-700">
            The engine is built for three people: a worker deciding whether to file a complaint,
            a reporter deciding whether to call a source back, and an investigator deciding where
            to spend a scarce subpoena. It will not tell you who is guilty. It will tell you who
            is worth a second look, and why.
          </p>
          <div className="mt-8 flex flex-wrap items-baseline gap-x-8 gap-y-3">
            <Link href="/search" className="btn btn-primary">
              Start with a search
            </Link>
            <Link href="/violators" className="btn-text">
              Read the enforcement record
            </Link>
            <Link href="/methodology" className="btn-text">
              How the score is computed
            </Link>
          </div>
        </div>

        <aside className="md:col-span-4">
          <div className="border-t-2 border-ink-900 pt-3">
            <div className="caps text-ink-500">As of today</div>
            <dl className="mt-4 space-y-3 text-sm">
              <LedeStat label="Employers indexed" value={compactNumber(stats.employers)} />
              <LedeStat label="LCA filings" value={compactNumber(stats.filings)} />
              <LedeStat
                label="Flagged (score ≥ 50)"
                value={compactNumber(stats.flagged)}
                emphasis
              />
              <LedeStat
                label="Resolved enforcement outcomes"
                value={compactNumber(stats.violations)}
              />
              <LedeStat label="Back wages on record" value={compactCurrency(stats.backWages)} />
            </dl>
          </div>
        </aside>
      </article>

      <hr className="hr-thick" />

      {/* ---------- TOP FLAGGED ---------- */}
      <section>
        <header className="flex flex-wrap items-baseline justify-between gap-4">
          <h2 className="font-serif">
            The fifteen employers the engine is most worried about.
          </h2>
          <div className="flex items-baseline gap-6 text-sm">
            <Link
              href={`/compare?ids=${top.slice(0, 3).map((e) => e.id).join(',')}`}
              className="btn-text"
            >
              Compare the top three
            </Link>
            <Link href="/search" className="btn-text">
              See the full index
            </Link>
          </div>
        </header>
        <p className="mt-3 max-w-[70ch] text-sm italic text-ink-600">
          Ranked by composite anomaly score. A score is a lead, not a verdict — follow the row
          through to the underlying filings.
        </p>

        <div className="mt-6 overflow-x-auto">
          <table className="ledger">
            <thead>
              <tr>
                <th className="w-10">No.</th>
                <th>Employer</th>
                <th>State</th>
                <th>NAICS</th>
                <th className="text-right">LCAs</th>
                <th>Severity</th>
                <th className="w-20 text-right">Score</th>
              </tr>
            </thead>
            <tbody>
              {top.map((e, i) => {
                const score = Number(e.anomaly_score);
                return (
                  <tr key={e.id}>
                    <td className="num text-ink-400">{String(i + 1).padStart(2, '0')}</td>
                    <td>
                      <Link href={`/employer/${e.id}`} className="link">
                        {e.name}
                      </Link>
                      {e.city && (
                        <div className="text-xs text-ink-500">
                          {e.city}, {e.state}
                        </div>
                      )}
                    </td>
                    <td className="text-ink-700">{e.state ?? '—'}</td>
                    <td className="num">{e.naics_code ?? '—'}</td>
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
              {top.length === 0 && (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-sm text-ink-500">
                    No scored employers yet. Run{' '}
                    <code className="font-mono text-xs">python scripts/score.py run</code>.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <hr className="hr-hair" />

      {/* ---------- GUARDRAILS (one line, in-line) ---------- */}
      <aside className="md:grid md:grid-cols-12 md:gap-10">
        <div className="md:col-span-3">
          <div className="caps text-ink-500">A note to readers</div>
        </div>
        <div className="md:col-span-9">
          <p className="max-w-[65ch] text-[15px] leading-[1.6] text-ink-800">
            Every figure comes from a public filing, but an anomaly can have an innocent
            explanation. This tool is about employers and systems — never about individual
            workers by name. Before naming a company in print or filing a complaint, read the
            methodology and verify against primary sources.{' '}
            <Link href="/methodology" className="link">
              How the engine works
            </Link>
            .
          </p>
        </div>
      </aside>
    </div>
  );
}

function LedeStat({
  label,
  value,
  emphasis,
}: {
  label: string;
  value: string;
  emphasis?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-ink-100 pb-2 last:border-b-0">
      <dt className="text-xs text-ink-600">{label}</dt>
      <dd
        className={`font-mono text-sm tabular ${
          emphasis ? 'text-accent' : 'text-ink-900'
        }`}
      >
        {value}
      </dd>
    </div>
  );
}
