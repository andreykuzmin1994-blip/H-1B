import Link from 'next/link';
import { notFound } from 'next/navigation';
import { prisma } from '@/lib/db';
import {
  formatCurrency,
  severityClass,
  severityDotClass,
  severityLabel,
  severityTagline,
} from '@/lib/formatters';
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
    <div className="space-y-10">
      {/* ---------- HERO ---------- */}
      <section className="relative overflow-hidden rounded-2xl border border-ink-800 bg-ink-950 p-6 text-ink-100 shadow-elevated md:p-10">
        <div className="hero-grid pointer-events-none absolute inset-0 opacity-60" />
        <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-ember-500/20 blur-3xl" />
        <div className="relative flex flex-wrap items-start justify-between gap-6">
          <div className="min-w-0 flex-1">
            <div className="eyebrow">
              <span className="h-px w-6 bg-ember-500" /> Employer dossier
            </div>
            <h1 className="mt-3 font-serif text-3xl font-semibold tracking-tight text-white md:text-4xl">
              {employer.name}
            </h1>
            <p className="mt-2 text-sm text-ink-300">
              {employer.address_line1 && `${employer.address_line1}, `}
              {employer.city}
              {employer.state && `, ${employer.state}`} {employer.zip ?? ''}
            </p>
            <div className="mt-5 flex flex-wrap gap-x-6 gap-y-2 text-xs uppercase tracking-[0.16em] text-ink-400">
              <span>
                NAICS <span className="font-mono text-ink-200">{employer.naics_code ?? '—'}</span>
              </span>
              <span>
                EIN <span className="font-mono text-ink-200">{employer.ein ?? '—'}</span>
              </span>
              <span>
                LCAs{' '}
                <span className="font-mono text-ink-200">
                  {employer.total_lca_count?.toLocaleString() ?? '0'}
                </span>
              </span>
            </div>
          </div>

          <div className="flex flex-col items-end gap-3">
            <div className="rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-right">
              <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-ink-400">
                Anomaly score
              </div>
              <div className="mt-1 font-serif text-4xl font-semibold tracking-tight text-white">
                {score.toFixed(0)}
                <span className="text-lg text-ink-400">/100</span>
              </div>
              <div className="mt-1">
                <span className={`severity-badge ${severityClass(score)}`}>
                  <span className={`severity-dot ${severityDotClass(score)}`} />
                  {severityLabel(score)}
                </span>
              </div>
              <p className="mt-2 max-w-[14rem] text-[11px] leading-snug text-ink-400">
                {severityTagline(score)}
              </p>
            </div>
            <Link href={`/tip/${employer.id}`} className="btn-accent">
              Generate enforcement tip →
            </Link>
          </div>
        </div>
      </section>

      {/* ---------- FLAGS ---------- */}
      <section>
        <SectionHeading
          label="Signals"
          title="Anomaly flags"
          sub="Each flag is a public-data signal — not a legal finding. See the methodology for what each flag does and does not prove."
        />
        <AnomalyFlagList
          flags={employer.flags.map((f) => ({ ...f, flag_score: Number(f.flag_score) }))}
        />
        <div className="mt-3 text-xs text-ink-500">
          <Link href="/methodology" className="link">
            What do these flags mean? →
          </Link>
        </div>
      </section>

      {/* ---------- WAGE + ADDRESS ---------- */}
      <section className="grid grid-cols-1 gap-5 md:grid-cols-2">
        <div className="card">
          <h3 className="font-serif text-lg font-semibold text-ink-900">Wage analysis</h3>
          <p className="mt-1 text-xs text-ink-500">
            Average filed wage vs. BLS OEWS national median, by SOC code.
          </p>
          <div className="mt-4">
            {wageData.length === 0 ? (
              <p className="text-sm text-ink-500">
                No wage benchmark data available for this employer&rsquo;s SOC codes.
              </p>
            ) : (
              <WageChart data={wageData} />
            )}
          </div>
        </div>
        <div className="card">
          <h3 className="font-serif text-lg font-semibold text-ink-900">Address</h3>
          <p className="mt-1 text-xs text-ink-500">Physical footprint and classification.</p>
          <dl className="mt-4 space-y-2 text-sm">
            <div className="flex justify-between">
              <dt className="text-ink-500">Classification</dt>
              <dd className="font-semibold text-ink-900">
                {employer.address_type ?? 'UNKNOWN'}
              </dd>
            </div>
            {employer.address_geocoded_lat && (
              <div className="flex justify-between">
                <dt className="text-ink-500">Coordinates</dt>
                <dd className="num text-ink-800">
                  {Number(employer.address_geocoded_lat).toFixed(4)},{' '}
                  {Number(employer.address_geocoded_lng).toFixed(4)}
                </dd>
              </div>
            )}
          </dl>
          {employer.address_line1 && (
            <Link
              className="mt-4 inline-flex text-sm font-medium text-ink-800 underline underline-offset-4 decoration-ember-500 decoration-2 hover:text-ember-600"
              href={`/address/${encodeURIComponent(
                [employer.address_line1, employer.city, employer.state].filter(Boolean).join('|'),
              )}`}
            >
              Other entities at this address →
            </Link>
          )}
        </div>
      </section>

      {/* ---------- FILING ACTIVITY ---------- */}
      <section>
        <SectionHeading label="Activity" title="Filing history" />
        <EmployerCharts byYear={byYear} bySoc={bySoc} uscisByYear={uscisByYear} />
      </section>

      {/* ---------- GRAPH ---------- */}
      <section>
        <SectionHeading label="Network" title="Entity relationships" />
        <div className="card">
          <EntityGraph graph={graph} centerId={id} />
        </div>
      </section>

      {/* ---------- FILINGS TABLE ---------- */}
      <section>
        <SectionHeading
          label="Disclosures"
          title="Filing history"
          sub="Most recent 100 LCA filings from DOL OFLC."
        />
        <div className="overflow-hidden rounded-xl border border-ink-200 bg-white shadow-card">
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Case #</th>
                  <th>Status</th>
                  <th>SOC</th>
                  <th>Job title</th>
                  <th className="text-right">Wage (annual)</th>
                  <th>Worksite</th>
                  <th>Received</th>
                </tr>
              </thead>
              <tbody>
                {employer.filings.map((f) => (
                  <tr key={f.id}>
                    <td className="num text-ink-600">{f.case_number}</td>
                    <td>
                      <StatusChip status={f.case_status} />
                    </td>
                    <td className="num">{f.soc_code}</td>
                    <td>{f.job_title}</td>
                    <td className="num text-right">
                      {formatCurrency(f.wage_annualized ? Number(f.wage_annualized) : null)}
                    </td>
                    <td className="text-ink-600">
                      {f.worksite_city}
                      {f.worksite_state ? `, ${f.worksite_state}` : ''}
                    </td>
                    <td className="num text-ink-600">
                      {f.received_date ? new Date(f.received_date).toLocaleDateString() : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {employer.layoff_events.length > 0 && (
        <section>
          <SectionHeading
            label="Displacement"
            title="Layoffs and concurrent H-1B filings"
            sub={`WARN Act and supplemental layoff notices. "Concurrent H-1B" counts LCAs filed within ±${LAYOFF_WINDOW_DAYS} days — the INA §212(n)(1)(E) non-displacement window.`}
          />
          <div className="card space-y-4">
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
              const hot = concurrent.length > 0;
              return (
                <div
                  key={l.id}
                  className={`relative rounded-md border-l-4 pl-4 py-1 ${
                    hot ? 'border-red-600 bg-red-50/40' : 'border-ink-200'
                  }`}
                >
                  <div className="font-serif text-base font-semibold text-ink-900">
                    {l.workers_affected ? l.workers_affected.toLocaleString() : '?'} workers ·{' '}
                    {[l.location_city, l.location_state].filter(Boolean).join(', ') || '—'}
                  </div>
                  <div className="mt-0.5 text-xs text-ink-500">
                    <span className="font-mono uppercase tracking-wider">{l.source}</span> ·{' '}
                    {l.effective_date
                      ? `effective ${new Date(l.effective_date).toLocaleDateString()}`
                      : l.notice_date
                      ? `noticed ${new Date(l.notice_date).toLocaleDateString()}`
                      : 'date unknown'}
                  </div>
                  {l.reason && (
                    <div className="mt-1 text-sm text-ink-700">Reason: {l.reason}</div>
                  )}
                  {hot && (
                    <div className="mt-1 inline-flex items-center gap-1.5 text-sm font-semibold text-red-700">
                      <span className="severity-dot bg-red-600 animate-pulseDot" />
                      {concurrent.length} H-1B LCA{concurrent.length === 1 ? '' : 's'} filed within
                      ±{LAYOFF_WINDOW_DAYS} days
                    </div>
                  )}
                  {l.source_url && (
                    <div className="mt-1">
                      <a
                        className="text-xs font-medium text-ink-800 underline underline-offset-4 decoration-ember-500 decoration-2 hover:text-ember-600"
                        href={l.source_url}
                        rel="noreferrer"
                        target="_blank"
                      >
                        Source notice ↗
                      </a>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {employer.violations.length > 0 && (
        <section>
          <SectionHeading label="Enforcement" title="Resolved violations" />
          <div className="card space-y-4">
            {employer.violations.map((v) => (
              <div
                key={v.id}
                className="relative rounded-md border-l-4 border-red-600 bg-red-50/30 pl-4 py-1"
              >
                <div className="font-serif text-base font-semibold text-ink-900">
                  {v.violation_type || 'Violation'}
                </div>
                <div className="mt-0.5 text-xs text-ink-500">
                  <span className="font-mono uppercase tracking-wider">{v.source}</span> ·{' '}
                  {v.violation_date
                    ? new Date(v.violation_date).toLocaleDateString()
                    : 'date unknown'}
                </div>
                {v.back_wages_amount && (
                  <div className="text-sm text-ink-700">
                    Back wages: {formatCurrency(Number(v.back_wages_amount))}
                  </div>
                )}
                {v.penalty_amount && (
                  <div className="text-sm text-ink-700">
                    Penalty: {formatCurrency(Number(v.penalty_amount))}
                  </div>
                )}
                {v.description && (
                  <p className="mt-1 text-sm text-ink-700">{v.description}</p>
                )}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function SectionHeading({
  label,
  title,
  sub,
}: {
  label: string;
  title: string;
  sub?: string;
}) {
  return (
    <div className="mb-5">
      <div className="eyebrow">
        <span className="h-px w-6 bg-ember-500" /> {label}
      </div>
      <h2 className="mt-2 font-serif text-2xl font-semibold tracking-tight text-ink-900">
        {title}
      </h2>
      {sub && <p className="mt-1 max-w-3xl text-sm text-ink-600">{sub}</p>}
    </div>
  );
}

function StatusChip({ status }: { status: string | null }) {
  if (!status) return <span className="text-ink-400">—</span>;
  const s = status.toUpperCase();
  const positive = s.includes('CERTIF');
  const negative = s.includes('DENIED') || s.includes('WITHDRAWN');
  const cls = positive
    ? 'bg-lime-50 text-lime-700 ring-lime-200'
    : negative
    ? 'bg-red-50 text-red-700 ring-red-200'
    : 'bg-ink-100 text-ink-700 ring-ink-200';
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ring-1 ring-inset ${cls}`}
    >
      {status}
    </span>
  );
}
