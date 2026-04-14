import Link from 'next/link';
import { notFound } from 'next/navigation';
import { prisma } from '@/lib/db';
import { formatCurrency, severityClass, severityLabel } from '@/lib/formatters';
import { WageChart } from '@/components/WageChart';
import { AnomalyFlagList } from '@/components/AnomalyFlagList';
import { EntityGraph } from '@/components/EntityGraph';
import { EmployerCharts } from '@/components/EmployerCharts';

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
  // 2-hop recursive CTE
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

  // Wage chart: compare each unique SOC's wage to the national median.
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

  // Chart data: filings per fiscal year, top SOCs, USCIS approval history.
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
    <div className="space-y-8">
      <section className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">{employer.name}</h1>
          <p className="mt-1 text-sm text-gray-600">
            {employer.address_line1 && `${employer.address_line1}, `}
            {employer.city}, {employer.state} {employer.zip}
          </p>
          <p className="text-sm text-gray-600">
            NAICS {employer.naics_code} · {employer.total_lca_count} LCA filings
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <span
            className={`severity-badge px-3 py-1 text-sm ${severityClass(score)}`}
          >
            {severityLabel(score)} · {score.toFixed(0)} / 100
          </span>
          <Link
            href={`/tip/${employer.id}`}
            className="rounded bg-blue-600 px-3 py-1 text-sm text-white"
          >
            Generate Tip Text
          </Link>
        </div>
      </section>

      <section>
        <h2 className="mb-2 text-lg font-semibold">Anomaly flags</h2>
        <AnomalyFlagList flags={employer.flags.map((f) => ({ ...f, flag_score: Number(f.flag_score) }))} />
      </section>

      <section className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="card">
          <h3 className="mb-2 font-semibold">Wage analysis</h3>
          {wageData.length === 0 ? (
            <p className="text-sm text-gray-500">
              No wage benchmark data available for this employer&rsquo;s SOC codes.
            </p>
          ) : (
            <WageChart data={wageData} />
          )}
        </div>
        <div className="card">
          <h3 className="mb-2 font-semibold">Address</h3>
          <p className="text-sm">
            Classification:{' '}
            <span className="font-semibold">{employer.address_type ?? 'UNKNOWN'}</span>
          </p>
          {employer.address_geocoded_lat && (
            <p className="text-sm">
              Coordinates: {Number(employer.address_geocoded_lat).toFixed(4)},{' '}
              {Number(employer.address_geocoded_lng).toFixed(4)}
            </p>
          )}
          {employer.address_line1 && (
            <Link
              className="mt-2 inline-block text-sm text-blue-700 hover:underline"
              href={`/address/${encodeURIComponent(
                [employer.address_line1, employer.city, employer.state].filter(Boolean).join('|'),
              )}`}
            >
              Other entities at this address →
            </Link>
          )}
        </div>
      </section>

      <section>
        <h2 className="mb-2 text-lg font-semibold">Filing activity</h2>
        <EmployerCharts byYear={byYear} bySoc={bySoc} uscisByYear={uscisByYear} />
      </section>

      <section>
        <h2 className="mb-2 text-lg font-semibold">Entity relationships</h2>
        <div className="card">
          <EntityGraph graph={graph} centerId={id} />
        </div>
      </section>

      <section>
        <h2 className="mb-2 text-lg font-semibold">Filing history (latest 100)</h2>
        <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
          <table className="min-w-full divide-y divide-gray-200 text-xs">
            <thead className="bg-gray-50 text-left">
              <tr>
                <th className="px-3 py-2 font-medium">Case #</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 font-medium">SOC</th>
                <th className="px-3 py-2 font-medium">Job title</th>
                <th className="px-3 py-2 font-medium">Wage (annual)</th>
                <th className="px-3 py-2 font-medium">Worksite</th>
                <th className="px-3 py-2 font-medium">Received</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {employer.filings.map((f) => (
                <tr key={f.id}>
                  <td className="px-3 py-2 font-mono">{f.case_number}</td>
                  <td className="px-3 py-2">{f.case_status}</td>
                  <td className="px-3 py-2">{f.soc_code}</td>
                  <td className="px-3 py-2">{f.job_title}</td>
                  <td className="px-3 py-2">
                    {formatCurrency(f.wage_annualized ? Number(f.wage_annualized) : null)}
                  </td>
                  <td className="px-3 py-2">
                    {f.worksite_city}, {f.worksite_state}
                  </td>
                  <td className="px-3 py-2">
                    {f.received_date ? new Date(f.received_date).toLocaleDateString() : ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {employer.layoff_events.length > 0 && (
        <section>
          <h2 className="mb-2 text-lg font-semibold">
            Layoffs and concurrent H-1B filings
          </h2>
          <div className="card space-y-3">
            <p className="text-sm text-gray-600">
              WARN Act and supplemental layoff notices. &ldquo;Concurrent H-1B&rdquo; counts LCAs
              filed within &plusmn;{LAYOFF_WINDOW_DAYS} days of each layoff &mdash; the INA
              &sect;&nbsp;212(n)(1)(E) non-displacement window that applies to H-1B-dependent
              employers.
            </p>
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
                <div
                  key={l.id}
                  className={`border-l-4 pl-3 ${
                    concurrent.length > 0 ? 'border-critical' : 'border-gray-300'
                  }`}
                >
                  <div className="font-semibold">
                    {l.workers_affected ? l.workers_affected.toLocaleString() : '?'} workers ·{' '}
                    {[l.location_city, l.location_state].filter(Boolean).join(', ') || '-'}
                  </div>
                  <div className="text-sm text-gray-600">
                    {l.source} ·{' '}
                    {l.effective_date
                      ? `effective ${new Date(l.effective_date).toLocaleDateString()}`
                      : l.notice_date
                      ? `noticed ${new Date(l.notice_date).toLocaleDateString()}`
                      : 'date unknown'}
                  </div>
                  {l.reason && <div className="text-sm">Reason: {l.reason}</div>}
                  {concurrent.length > 0 && (
                    <div className="mt-1 text-sm font-semibold text-red-700">
                      {concurrent.length} H-1B LCA{concurrent.length === 1 ? '' : 's'} filed
                      within ±{LAYOFF_WINDOW_DAYS} days
                    </div>
                  )}
                  {l.source_url && (
                    <a
                      className="mt-1 inline-block text-xs text-blue-700 hover:underline"
                      href={l.source_url}
                      rel="noreferrer"
                      target="_blank"
                    >
                      Source notice →
                    </a>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {employer.violations.length > 0 && (
        <section>
          <h2 className="mb-2 text-lg font-semibold">Enforcement history</h2>
          <div className="card space-y-3">
            {employer.violations.map((v) => (
              <div key={v.id} className="border-l-4 border-critical pl-3">
                <div className="font-semibold">{v.violation_type || 'Violation'}</div>
                <div className="text-sm text-gray-600">
                  {v.source} ·{' '}
                  {v.violation_date ? new Date(v.violation_date).toLocaleDateString() : 'date unknown'}
                </div>
                {v.back_wages_amount && (
                  <div className="text-sm">
                    Back wages: {formatCurrency(Number(v.back_wages_amount))}
                  </div>
                )}
                {v.penalty_amount && (
                  <div className="text-sm">Penalty: {formatCurrency(Number(v.penalty_amount))}</div>
                )}
                {v.description && <p className="text-sm">{v.description}</p>}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
