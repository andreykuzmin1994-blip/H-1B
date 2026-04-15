import Link from 'next/link';
import { notFound } from 'next/navigation';
import { prisma } from '@/lib/db';
import {
  formatCurrency,
  severityClass,
  severityLabel,
  severityMarkClass,
  severityTagline,
} from '@/lib/formatters';
import { WageChart } from '@/components/WageChart';
import { AnomalyFlagList } from '@/components/AnomalyFlagList';
import { EntityGraph } from '@/components/EntityGraph';
import { EmployerCharts } from '@/components/EmployerCharts';
import { ShareButton } from '@/components/ShareButton';

export const revalidate = 60;

async function loadEmployer(id: number) {
  return prisma.employer.findUnique({
    where: { id },
    include: {
      flags: { orderBy: { flag_score: 'desc' } },
      filings: { orderBy: { received_date: 'desc' }, take: 100 },
      violations: { orderBy: { violation_date: 'desc' } },
      sos_entities: true,
      layoff_events: { orderBy: [{ effective_date: 'desc' }, { notice_date: 'desc' }] },
    },
  });
}

const LAYOFF_WINDOW_DAYS = 90;
const DAY_MS = 24 * 60 * 60 * 1000;

async function loadGraph(id: number) {
  const rows = await prisma.$queryRawUnsafe<any[]>(
    `
    WITH RECURSIVE reachable(id, depth) AS (
        SELECT $1::int, 0
      UNION
        SELECT CASE WHEN er.employer_id_a = r.id THEN er.employer_id_b ELSE er.employer_id_a END,
               r.depth + 1
          FROM entity_relationships er
          JOIN reachable r ON er.employer_id_a = r.id OR er.employer_id_b = r.id
         WHERE r.depth < 2
    )
    SELECT DISTINCT id, depth FROM reachable
    `,
    id,
  );
  const ids = rows.map((r: any) => Number(r.id));
  if (ids.length === 0) return { nodes: [], edges: [] };
  const employers = await prisma.employer.findMany({ where: { id: { in: ids } } });
  const edges = await prisma.entityRelationship.findMany({
    where: { employer_id_a: { in: ids }, employer_id_b: { in: ids } },
  });
  const violators = new Set(
    (
      await prisma.violation.findMany({
        where: { employer_id: { in: ids } },
        select: { employer_id: true },
      })
    )
      .map((v) => v.employer_id)
      .filter((v): v is number => !!v),
  );
  const depthMap = new Map<number, number>();
  for (const row of rows) {
    depthMap.set(Number(row.id), Number(row.depth));
  }
  return {
    nodes: employers.map((e) => ({
      id: e.id,
      name: e.name,
      state: e.state,
      anomaly_score: Number(e.anomaly_score),
      is_violator: violators.has(e.id),
      depth: depthMap.get(e.id) ?? 0,
    })),
    edges: edges.map((r) => ({
      source: r.employer_id_a,
      target: r.employer_id_b,
      type: r.relationship_type,
      confidence: Number(r.confidence),
    })),
  };
}

async function loadSocMedian(socCode: string) {
  const row = await prisma.socWageBenchmark.findFirst({
    where: { soc_code: socCode, area_type: 'NATIONAL' },
    orderBy: { oews_year: 'desc' },
  });
  return row?.median_annual_wage ? Number(row.median_annual_wage) : null;
}

export default async function EmployerPage({ params }: { params: { id: string } }) {
  const id = Number(params.id);
  if (!Number.isFinite(id)) notFound();
  const employer = await loadEmployer(id);
  if (!employer) notFound();

  const graph = await loadGraph(id);
  const score = Number(employer.anomaly_score);

  const uniqSocs = Array.from(
    new Set(employer.filings.map((f) => f.soc_code).filter((s): s is string => !!s)),
  );
  const wageData: { soc: string; employer: number; median: number | null }[] = [];
  for (const soc of uniqSocs.slice(0, 6)) {
    const filings = employer.filings.filter((f) => f.soc_code === soc && f.wage_annualized);
    if (filings.length === 0) continue;
    const avg =
      filings.reduce((s, f) => s + Number(f.wage_annualized ?? 0), 0) / filings.length;
    const median = await loadSocMedian(soc);
    wageData.push({ soc, employer: avg, median });
  }

  const yearBuckets = new Map<number, number>();
  for (const f of employer.filings) {
    if (f.fiscal_year == null) continue;
    yearBuckets.set(f.fiscal_year, (yearBuckets.get(f.fiscal_year) ?? 0) + 1);
  }
  const byYear = [...yearBuckets.entries()]
    .sort(([a], [b]) => a - b)
    .map(([year, count]) => ({ year, count }));

  const socBuckets = new Map<string, number>();
  for (const f of employer.filings) {
    if (!f.soc_code) continue;
    socBuckets.set(f.soc_code, (socBuckets.get(f.soc_code) ?? 0) + 1);
  }
  const bySoc = [...socBuckets.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(([soc, count]) => ({ soc, count }));

  const uscisRows = await prisma.uscisEmployerStats.findMany({
    where: { employer_id: id },
    orderBy: { fiscal_year: 'asc' },
  });
  const uscisByYear = uscisRows.map((r) => ({
    year: r.fiscal_year,
    approvals: r.initial_approvals,
    denials: r.initial_denials,
  }));

  return (
    <article className="space-y-14">
      {/* ---------- CASE HEADER ---------- */}
      <header>
        <div className="dateline">Case file · Employer dossier</div>
        <h1 className="mt-3 font-serif text-ink-900">{employer.name}</h1>
        <p className="mt-2 text-sm text-ink-600">
          {[employer.address_line1, employer.city].filter(Boolean).join(', ')}
          {employer.state && `, ${employer.state}`} {employer.zip ?? ''}
        </p>

        <div className="mt-8 grid grid-cols-1 gap-6 border-t-2 border-ink-900 pt-4 md:grid-cols-12">
          <dl className="md:col-span-8 grid grid-cols-2 gap-y-2 gap-x-8 text-sm md:grid-cols-4">
            <FactRow label="NAICS" value={employer.naics_code ?? '—'} />
            <FactRow label="EIN" value={employer.ein ?? '—'} mono />
            <FactRow
              label="LCA filings"
              value={employer.total_lca_count?.toLocaleString() ?? '0'}
            />
            <FactRow
              label="First seen"
              value={
                employer.first_filing_date
                  ? new Date(employer.first_filing_date).getFullYear().toString()
                  : '—'
              }
            />
          </dl>

          <div className="md:col-span-4">
            <div className="caps text-ink-500">Anomaly score</div>
            <div className="mt-1 flex items-baseline gap-3">
              <span className="font-serif text-5xl font-semibold leading-none text-ink-900 tabular">
                {score.toFixed(0)}
              </span>
              <span className="text-sm text-ink-500">/ 100</span>
            </div>
            <div className="mt-2">
              <span className={`sev ${severityClass(score)}`}>
                <span className={`sev-mark ${severityMarkClass(score)}`} />
                {severityLabel(score)}
              </span>
              <span className="ml-3 text-sm italic text-ink-600">
                {severityTagline(score)}
              </span>
            </div>
            <div className="mt-4 flex flex-wrap items-baseline gap-x-6 gap-y-2 text-sm">
              <Link href={`/tip/${employer.id}`} className="btn-text">
                Generate enforcement tip
              </Link>
              <Link
                href={`/compare?ids=${employer.id}`}
                className="btn-text"
              >
                Add to comparison
              </Link>
              <ShareButton path={`/employer/${employer.id}`} />
            </div>
          </div>
        </div>
      </header>

      {/* ---------- FLAGS ---------- */}
      <section>
        <header className="flex items-baseline justify-between gap-6">
          <h2 className="font-serif">Signals the engine raised</h2>
          <Link href="/methodology" className="btn-text text-sm">
            What the flags mean
          </Link>
        </header>
        <hr className="hr-hair mt-3 mb-6" />
        <AnomalyFlagList
          flags={employer.flags.map((f) => ({
            ...f,
            flag_score: Number(f.flag_score),
          }))}
        />
      </section>

      {/* ---------- WAGE + ADDRESS ---------- */}
      <section className="grid grid-cols-1 gap-10 md:grid-cols-12">
        <div className="md:col-span-7">
          <h2 className="font-serif">Wage comparison</h2>
          <p className="mt-1 text-sm italic text-ink-600">
            Average filed wage versus BLS OEWS national median, by SOC code.
          </p>
          <hr className="hr-hair mt-3 mb-4" />
          {wageData.length === 0 ? (
            <p className="text-sm text-ink-500">
              No wage benchmark data available for this employer&rsquo;s SOC codes.
            </p>
          ) : (
            <WageChart data={wageData} />
          )}
        </div>
        <div className="md:col-span-5">
          <h2 className="font-serif">Address</h2>
          <p className="mt-1 text-sm italic text-ink-600">
            Physical footprint and classification.
          </p>
          <hr className="hr-hair mt-3 mb-4" />
          <dl className="space-y-2 text-sm">
            <FactInline
              label="Classification"
              value={employer.address_type ?? 'Unknown'}
            />
            {employer.address_geocoded_lat && (
              <FactInline
                label="Coordinates"
                value={`${Number(employer.address_geocoded_lat).toFixed(4)}, ${Number(
                  employer.address_geocoded_lng,
                ).toFixed(4)}`}
                mono
              />
            )}
          </dl>
          {employer.address_line1 && (
            <Link
              className="mt-4 inline-block text-sm link"
              href={`/address/${encodeURIComponent(
                [employer.address_line1, employer.city, employer.state]
                  .filter(Boolean)
                  .join('|'),
              )}`}
            >
              Other entities at this address
            </Link>
          )}
        </div>
      </section>

      {/* ---------- FILING ACTIVITY ---------- */}
      <section>
        <h2 className="font-serif">Filing activity</h2>
        <hr className="hr-hair mt-3 mb-6" />
        <EmployerCharts byYear={byYear} bySoc={bySoc} uscisByYear={uscisByYear} />
      </section>

      {/* ---------- GRAPH ---------- */}
      <section>
        <h2 className="font-serif">Entity network</h2>
        <p className="mt-1 text-sm italic text-ink-600">
          Two-hop graph of employers linked by shared officers, addresses, or trade-name aliases.
        </p>
        <hr className="hr-hair mt-3 mb-6" />
        <EntityGraph graph={graph} centerId={id} />
      </section>

      {/* ---------- FILINGS TABLE ---------- */}
      <section>
        <h2 className="font-serif">Most recent filings</h2>
        <p className="mt-1 text-sm italic text-ink-600">
          The hundred most recent LCA filings from DOL OFLC.
        </p>
        <hr className="hr-hair mt-3 mb-6" />
        <div className="overflow-x-auto">
          <table className="ledger">
            <thead>
              <tr>
                <th>Case</th>
                <th>Status</th>
                <th>SOC</th>
                <th>Job title</th>
                <th className="text-right">Annual wage</th>
                <th>Worksite</th>
                <th>Received</th>
              </tr>
            </thead>
            <tbody>
              {employer.filings.map((f) => (
                <tr key={f.id}>
                  <td className="num">{f.case_number}</td>
                  <td>
                    <StatusText status={f.case_status} />
                  </td>
                  <td className="num">{f.soc_code}</td>
                  <td>{f.job_title}</td>
                  <td className="num text-right">
                    {formatCurrency(f.wage_annualized ? Number(f.wage_annualized) : null)}
                  </td>
                  <td className="text-ink-700">
                    {f.worksite_city}
                    {f.worksite_state ? `, ${f.worksite_state}` : ''}
                  </td>
                  <td className="num">
                    {f.received_date ? new Date(f.received_date).toLocaleDateString() : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {employer.layoff_events.length > 0 && (
        <section>
          <h2 className="font-serif">Layoffs and concurrent H-1B filings</h2>
          <p className="mt-1 max-w-[70ch] text-sm italic text-ink-600">
            WARN Act and supplemental layoff notices. &ldquo;Concurrent H-1B&rdquo; counts LCAs
            filed within ±{LAYOFF_WINDOW_DAYS} days &mdash; the INA §212(n)(1)(E) non-displacement
            window for H-1B-dependent employers.
          </p>
          <hr className="hr-hair mt-3 mb-6" />
          <ul className="divide-y divide-ink-100">
            {employer.layoff_events.map((l) => {
              const pivot = l.effective_date ?? l.notice_date;
              const pivotMs = pivot ? new Date(pivot).getTime() : null;
              const concurrent = pivotMs
                ? employer.filings.filter(
                    (f) =>
                      f.received_date &&
                      Math.abs(new Date(f.received_date).getTime() - pivotMs) <=
                        LAYOFF_WINDOW_DAYS * DAY_MS,
                  )
                : [];
              return (
                <li
                  key={l.id}
                  className={`flex flex-wrap items-baseline gap-x-6 gap-y-1 py-3 ${
                    concurrent.length > 0
                      ? 'border-l-[3px] border-accent pl-4'
                      : ''
                  }`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="font-semibold text-ink-900">
                      {l.workers_affected ? l.workers_affected.toLocaleString() : '?'} workers
                      laid off &mdash;{' '}
                      {[l.location_city, l.location_state].filter(Boolean).join(', ') || '—'}
                    </div>
                    <div className="dateline mt-0.5">
                      {l.source} ·{' '}
                      {l.effective_date
                        ? `effective ${new Date(l.effective_date).toLocaleDateString()}`
                        : l.notice_date
                        ? `noticed ${new Date(l.notice_date).toLocaleDateString()}`
                        : 'date unknown'}
                    </div>
                    {l.reason && (
                      <div className="mt-1 text-sm text-ink-700">Reason: {l.reason}</div>
                    )}
                  </div>
                  {concurrent.length > 0 && (
                    <div className="text-sm font-semibold text-accent">
                      {concurrent.length} concurrent H-1B LCA
                      {concurrent.length === 1 ? '' : 's'}
                    </div>
                  )}
                  {l.source_url && (
                    <a
                      className="text-sm link"
                      href={l.source_url}
                      rel="noreferrer"
                      target="_blank"
                    >
                      Source notice
                    </a>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {employer.violations.length > 0 && (
        <section>
          <h2 className="font-serif">Resolved violations</h2>
          <hr className="hr-hair mt-3 mb-6" />
          <ul className="divide-y divide-ink-100">
            {employer.violations.map((v) => (
              <li
                key={v.id}
                className="border-l-[3px] border-accent pl-4 py-3"
              >
                <div className="font-semibold text-ink-900">
                  {v.violation_type || 'Violation'}
                </div>
                <div className="dateline mt-0.5">
                  {v.source} ·{' '}
                  {v.violation_date
                    ? new Date(v.violation_date).toLocaleDateString()
                    : 'date unknown'}
                </div>
                {(v.back_wages_amount || v.penalty_amount) && (
                  <div className="mt-1 text-sm text-ink-700">
                    {v.back_wages_amount &&
                      `Back wages ${formatCurrency(Number(v.back_wages_amount))}`}
                    {v.back_wages_amount && v.penalty_amount && ' · '}
                    {v.penalty_amount &&
                      `Penalty ${formatCurrency(Number(v.penalty_amount))}`}
                  </div>
                )}
                {v.description && (
                  <p className="mt-1 text-sm text-ink-700">{v.description}</p>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </article>
  );
}

function FactRow({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <dt className="caps text-ink-500">{label}</dt>
      <dd className={`mt-0.5 ${mono ? 'font-mono text-sm' : 'text-sm'} text-ink-900`}>
        {value}
      </dd>
    </div>
  );
}

function FactInline({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-ink-100 pb-1">
      <dt className="text-ink-500">{label}</dt>
      <dd className={mono ? 'font-mono text-xs' : undefined}>{value}</dd>
    </div>
  );
}

function StatusText({ status }: { status: string | null }) {
  if (!status) return <span className="text-ink-400">—</span>;
  const s = status.toUpperCase();
  const tone = s.includes('CERTIF')
    ? 'text-ink-800'
    : s.includes('DENIED') || s.includes('WITHDRAWN')
    ? 'text-accent'
    : 'text-ink-700';
  return (
    <span className={`text-xs font-semibold uppercase tracking-wider ${tone}`}>{status}</span>
  );
}
