import Link from 'next/link';
import { prisma } from '@/lib/db';
import {
  formatCurrency,
  severityClass,
  severityDotClass,
  severityLabel,
  severityTagline,
} from '@/lib/formatters';

export const dynamic = 'force-dynamic';

interface Params {
  ids?: string;
  add?: string;
}

const MAX_COLS = 4;

function parseIds(raw: string | undefined): number[] {
  if (!raw) return [];
  return raw
    .split(',')
    .map((s) => Number(s.trim()))
    .filter((n) => Number.isFinite(n) && n > 0)
    .slice(0, MAX_COLS);
}

async function searchForAdd(q: string) {
  return prisma.employer.findMany({
    where: {
      OR: [
        { name: { contains: q, mode: 'insensitive' } },
        { name_normalized: { contains: q.toUpperCase() } },
      ],
    },
    orderBy: { anomaly_score: 'desc' },
    take: 10,
    select: { id: true, name: true, state: true, city: true, anomaly_score: true },
  });
}

async function loadColumns(ids: number[]) {
  if (ids.length === 0) return [];
  const employers = await prisma.employer.findMany({
    where: { id: { in: ids } },
    include: {
      flags: { orderBy: { flag_score: 'desc' } },
      violations: { select: { id: true, back_wages_amount: true, penalty_amount: true } },
      layoff_events: { select: { id: true, workers_affected: true } },
    },
  });
  // Preserve caller-requested order
  const byId = new Map(employers.map((e) => [e.id, e]));
  return ids.map((i) => byId.get(i)).filter(Boolean) as typeof employers;
}

export default async function ComparePage({ searchParams }: { searchParams: Params }) {
  const ids = parseIds(searchParams.ids);
  const columns = await loadColumns(ids);

  // Handle optional add-search form
  const searchTerm = (searchParams.add ?? '').trim();
  const suggestions = searchTerm.length >= 2 ? await searchForAdd(searchTerm) : [];

  function urlWithout(id: number) {
    const next = ids.filter((i) => i !== id);
    return next.length ? `/compare?ids=${next.join(',')}` : '/compare';
  }
  function urlWith(id: number) {
    const next = Array.from(new Set([...ids, id])).slice(0, MAX_COLS);
    return `/compare?ids=${next.join(',')}`;
  }

  return (
    <div className="space-y-8">
      <div className="page-header">
        <div className="eyebrow">
          <span className="h-px w-6 bg-ember-500" /> Side-by-side
        </div>
        <h1>Compare employers.</h1>
        <p>
          Stack up to {MAX_COLS} employers next to each other &mdash; scores, flags, wage-theft
          history, concurrent layoffs. Share the URL to send a reporter straight to the
          comparison.
        </p>
      </div>

      {/* ---------- ADD FORM ---------- */}
      <form
        method="get"
        className="flex flex-wrap items-end gap-3 rounded-xl border border-ink-200 bg-white p-4 shadow-card"
      >
        {ids.length > 0 && <input type="hidden" name="ids" value={ids.join(',')} />}
        <div className="flex-1">
          <label className="stat-label">Add an employer</label>
          <input
            name="add"
            defaultValue={searchTerm}
            placeholder="Search by name…"
            className="input mt-1.5"
            autoComplete="off"
          />
        </div>
        <button className="btn-primary" type="submit">
          Search
        </button>
        {ids.length > 0 && (
          <Link href="/compare" className="btn-ghost">
            Clear all
          </Link>
        )}
      </form>

      {/* Suggestions */}
      {suggestions.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-ink-200 bg-white shadow-card">
          <div className="border-b border-ink-100 px-4 py-2 text-[11px] font-semibold uppercase tracking-wider text-ink-500">
            Click to add
          </div>
          <ul className="divide-y divide-ink-100">
            {suggestions.map((s) => {
              const alreadyIn = ids.includes(s.id);
              return (
                <li key={s.id} className="flex items-center justify-between px-4 py-2.5">
                  <div>
                    <div className="font-medium text-ink-900">{s.name}</div>
                    <div className="text-xs text-ink-500">
                      {s.city}
                      {s.state ? `, ${s.state}` : ''} · score {Number(s.anomaly_score).toFixed(0)}
                    </div>
                  </div>
                  {alreadyIn ? (
                    <span className="text-xs font-medium text-ink-400">Already compared</span>
                  ) : (
                    <Link href={urlWith(s.id)} className="btn-outline py-1 text-xs">
                      + Add
                    </Link>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* ---------- EMPTY STATE ---------- */}
      {columns.length === 0 && !searchTerm && (
        <div className="rounded-xl border border-dashed border-ink-200 bg-white/60 p-10 text-center">
          <div className="eyebrow justify-center">
            <span className="h-px w-6 bg-ember-500" /> Get started
          </div>
          <p className="mx-auto mt-3 max-w-lg text-sm text-ink-600">
            Search above to pull your first employer into the comparison, or{' '}
            <Link href="/search" className="link">
              browse flagged employers
            </Link>{' '}
            and click <span className="font-medium">Compare</span> on their dossier.
          </p>
        </div>
      )}

      {/* ---------- COLUMNS ---------- */}
      {columns.length > 0 && (
        <div className="overflow-x-auto">
          <div
            className="grid gap-4"
            style={{
              gridTemplateColumns: `repeat(${Math.max(columns.length, 2)}, minmax(260px, 1fr))`,
            }}
          >
            {columns.map((e) => {
              const score = Number(e.anomaly_score);
              const backWages = e.violations.reduce(
                (s, v) => s + Number(v.back_wages_amount ?? 0),
                0,
              );
              const penalties = e.violations.reduce(
                (s, v) => s + Number(v.penalty_amount ?? 0),
                0,
              );
              const laidOff = e.layoff_events.reduce(
                (s, l) => s + (l.workers_affected ?? 0),
                0,
              );
              return (
                <div key={e.id} className="card flex flex-col gap-4">
                  {/* Header */}
                  <div>
                    <div className="flex items-start justify-between gap-2">
                      <Link
                        href={`/employer/${e.id}`}
                        className="font-serif text-lg font-semibold text-ink-900 hover:text-ember-600"
                      >
                        {e.name}
                      </Link>
                      <Link
                        href={urlWithout(e.id)}
                        className="shrink-0 text-xs text-ink-400 hover:text-red-600"
                        title="Remove from comparison"
                      >
                        ✕
                      </Link>
                    </div>
                    <div className="mt-1 text-xs text-ink-500">
                      {e.city}
                      {e.state ? `, ${e.state}` : ''} · NAICS {e.naics_code ?? '—'}
                    </div>
                  </div>

                  {/* Score */}
                  <div className="rounded-lg border border-ink-200 bg-ink-50/60 p-3">
                    <div className="stat-label">Anomaly score</div>
                    <div className="mt-1 flex items-end justify-between">
                      <span className="font-serif text-3xl font-semibold text-ink-900">
                        {score.toFixed(0)}
                        <span className="text-base text-ink-400">/100</span>
                      </span>
                      <span className={`severity-badge ${severityClass(score)}`}>
                        <span className={`severity-dot ${severityDotClass(score)}`} />
                        {severityLabel(score)}
                      </span>
                    </div>
                    <p className="mt-2 text-[11px] leading-snug text-ink-500">
                      {severityTagline(score)}
                    </p>
                  </div>

                  {/* Stats grid */}
                  <dl className="grid grid-cols-2 gap-2 text-sm">
                    <MiniStat label="LCA filings" value={e.total_lca_count?.toLocaleString() ?? '0'} />
                    <MiniStat label="Flags" value={e.flags.length.toString()} />
                    <MiniStat label="Violations" value={e.violations.length.toString()} />
                    <MiniStat label="Layoff events" value={e.layoff_events.length.toString()} />
                    <MiniStat label="Workers laid off" value={laidOff ? laidOff.toLocaleString() : '—'} />
                    <MiniStat
                      label="Back wages"
                      value={backWages ? formatCurrency(backWages) : '—'}
                    />
                  </dl>

                  {/* Flags preview */}
                  <div>
                    <div className="stat-label mb-2">Top flags</div>
                    {e.flags.length === 0 ? (
                      <p className="text-xs text-ink-500">No flags detected.</p>
                    ) : (
                      <ul className="space-y-1.5">
                        {e.flags.slice(0, 4).map((f) => (
                          <li key={f.id} className="flex items-center gap-2 text-xs">
                            <span
                              className={`severity-dot ${
                                f.flag_severity === 'CRITICAL'
                                  ? 'bg-red-600'
                                  : f.flag_severity === 'HIGH'
                                  ? 'bg-orange-500'
                                  : f.flag_severity === 'MEDIUM'
                                  ? 'bg-amber-500'
                                  : 'bg-lime-500'
                              }`}
                            />
                            <span className="font-mono text-ink-700">{f.flag_type}</span>
                            <span className="ml-auto text-ink-500">
                              +{Number(f.flag_score).toFixed(0)}
                            </span>
                          </li>
                        ))}
                        {e.flags.length > 4 && (
                          <li className="text-[11px] text-ink-400">
                            + {e.flags.length - 4} more
                          </li>
                        )}
                      </ul>
                    )}
                  </div>

                  {/* Footer */}
                  <div className="mt-auto flex gap-2 pt-2">
                    <Link href={`/employer/${e.id}`} className="btn-primary flex-1 py-1.5 text-xs">
                      Open dossier
                    </Link>
                    <Link href={`/tip/${e.id}`} className="btn-outline flex-1 py-1.5 text-xs">
                      Generate tip
                    </Link>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {columns.length > 0 && (
        <div className="rounded-xl border border-ink-200 bg-white p-4 text-xs text-ink-500">
          Permalink to this comparison:{' '}
          <code className="font-mono text-ink-700">
            /compare?ids={ids.join(',')}
          </code>{' '}
          &mdash; share it with a colleague, or paste into a story.
        </div>
      )}
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-ink-100 bg-white p-2">
      <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-500">
        {label}
      </div>
      <div className="mt-0.5 font-mono text-sm text-ink-900">{value}</div>
    </div>
  );
}
