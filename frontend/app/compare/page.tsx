import Link from 'next/link';
import { prisma } from '@/lib/db';
import {
  formatCurrency,
  severityClass,
  severityLabel,
  severityMarkClass,
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
      violations: {
        select: { id: true, back_wages_amount: true, penalty_amount: true },
      },
      layoff_events: { select: { id: true, workers_affected: true } },
    },
  });
  const byId = new Map(employers.map((e) => [e.id, e]));
  return ids.map((i) => byId.get(i)).filter(Boolean) as typeof employers;
}

export default async function ComparePage({
  searchParams,
}: {
  searchParams: Params;
}) {
  const ids = parseIds(searchParams.ids);
  const columns = await loadColumns(ids);

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
    <div className="space-y-10">
      <header>
        <div className="dateline">Side by side</div>
        <h1 className="mt-3 font-serif">Compare employers.</h1>
        <p className="mt-3 max-w-[65ch] text-[15px] leading-[1.55] text-ink-700">
          Stack up to {MAX_COLS} employers next to each other &mdash; scores, flags, wage-theft
          history, concurrent layoffs. Share the URL to send a colleague straight to the
          comparison.
        </p>
      </header>

      {/* ---------- ADD FORM ---------- */}
      <form
        method="get"
        className="grid grid-cols-1 items-end gap-x-6 gap-y-3 border-t-2 border-ink-900 pt-4 md:grid-cols-12"
      >
        {ids.length > 0 && <input type="hidden" name="ids" value={ids.join(',')} />}
        <div className="md:col-span-9">
          <label className="field-label">Add an employer</label>
          <input
            name="add"
            defaultValue={searchTerm}
            placeholder="Search by name…"
            className="field"
            autoComplete="off"
          />
        </div>
        <div className="md:col-span-3 flex gap-4">
          <button className="btn btn-primary flex-1" type="submit">
            Search
          </button>
          {ids.length > 0 && (
            <Link href="/compare" className="btn-text self-center text-sm">
              Clear
            </Link>
          )}
        </div>
      </form>

      {suggestions.length > 0 && (
        <ul className="divide-y divide-ink-100 border-t border-ink-200">
          {suggestions.map((s) => {
            const alreadyIn = ids.includes(s.id);
            return (
              <li key={s.id} className="flex items-baseline justify-between gap-6 py-3">
                <div>
                  <div className="text-ink-900">{s.name}</div>
                  <div className="dateline mt-0.5">
                    {s.city}
                    {s.state ? `, ${s.state}` : ''} · score{' '}
                    {Number(s.anomaly_score).toFixed(0)}
                  </div>
                </div>
                {alreadyIn ? (
                  <span className="text-xs italic text-ink-500">already compared</span>
                ) : (
                  <Link href={urlWith(s.id)} className="btn-text text-sm">
                    Add to comparison
                  </Link>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {/* ---------- EMPTY STATE ---------- */}
      {columns.length === 0 && !searchTerm && (
        <p className="max-w-[65ch] text-[15px] italic text-ink-600">
          Search above to pull the first employer into the comparison, or{' '}
          <Link href="/search" className="link">
            browse flagged employers
          </Link>{' '}
          and add them from the dossier.
        </p>
      )}

      {/* ---------- COLUMNS ---------- */}
      {columns.length > 0 && (
        <div className="overflow-x-auto">
          <div
            className="grid gap-0"
            style={{
              gridTemplateColumns: `repeat(${Math.max(columns.length, 2)}, minmax(260px, 1fr))`,
            }}
          >
            {columns.map((e, idx) => {
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
                <div
                  key={e.id}
                  className={`flex flex-col gap-6 p-5 ${
                    idx === 0
                      ? 'border-t-2 border-ink-900'
                      : 'border-l border-t-2 border-ink-200 border-t-ink-900'
                  }`}
                >
                  {/* Header */}
                  <div>
                    <div className="flex items-baseline justify-between gap-2">
                      <Link
                        href={`/employer/${e.id}`}
                        className="link font-serif text-[20px] leading-[1.15]"
                      >
                        {e.name}
                      </Link>
                      <Link
                        href={urlWithout(e.id)}
                        className="text-[11px] uppercase tracking-wider text-ink-400 hover:text-accent"
                        title="Remove from comparison"
                      >
                        remove
                      </Link>
                    </div>
                    <div className="dateline mt-1">
                      {e.city}
                      {e.state ? `, ${e.state}` : ''} · NAICS {e.naics_code ?? '—'}
                    </div>
                  </div>

                  {/* Score */}
                  <div>
                    <div className="caps text-ink-500">Anomaly score</div>
                    <div className="mt-1 flex items-baseline gap-3">
                      <span className="font-serif text-4xl font-semibold tabular text-ink-900">
                        {score.toFixed(0)}
                      </span>
                      <span className="text-sm text-ink-500">/ 100</span>
                    </div>
                    <div className="mt-1">
                      <span className={`sev ${severityClass(score)}`}>
                        <span className={`sev-mark ${severityMarkClass(score)}`} />
                        {severityLabel(score)}
                      </span>
                    </div>
                  </div>

                  {/* Stats */}
                  <dl className="space-y-2 text-sm">
                    <StatLine
                      label="LCA filings"
                      value={e.total_lca_count?.toLocaleString() ?? '0'}
                    />
                    <StatLine label="Flags raised" value={e.flags.length.toString()} />
                    <StatLine
                      label="Violations"
                      value={e.violations.length.toString()}
                    />
                    <StatLine
                      label="Layoff events"
                      value={e.layoff_events.length.toString()}
                    />
                    <StatLine
                      label="Workers laid off"
                      value={laidOff ? laidOff.toLocaleString() : '—'}
                    />
                    <StatLine
                      label="Back wages"
                      value={backWages ? formatCurrency(backWages) : '—'}
                    />
                    <StatLine
                      label="Penalties"
                      value={penalties ? formatCurrency(penalties) : '—'}
                    />
                  </dl>

                  {/* Top flags */}
                  <div>
                    <div className="caps text-ink-500">Top flags</div>
                    {e.flags.length === 0 ? (
                      <p className="mt-2 text-sm text-ink-500">None.</p>
                    ) : (
                      <ul className="mt-2 space-y-1.5 text-[13px]">
                        {e.flags.slice(0, 4).map((f) => (
                          <li
                            key={f.id}
                            className="flex items-baseline justify-between gap-2 border-b border-ink-100 pb-1"
                          >
                            <span className="font-mono text-[11px] text-ink-700">
                              {f.flag_type}
                            </span>
                            <span className="tabular text-ink-500">
                              +{Number(f.flag_score).toFixed(0)}
                            </span>
                          </li>
                        ))}
                        {e.flags.length > 4 && (
                          <li className="text-[11px] italic text-ink-500">
                            and {e.flags.length - 4} more
                          </li>
                        )}
                      </ul>
                    )}
                  </div>

                  {/* Footer */}
                  <div className="mt-auto flex flex-wrap items-baseline gap-x-5 gap-y-2 text-sm">
                    <Link href={`/employer/${e.id}`} className="btn-text">
                      Open dossier
                    </Link>
                    <Link href={`/tip/${e.id}`} className="btn-text">
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
        <p className="text-xs italic text-ink-500">
          Permalink:{' '}
          <code className="font-mono not-italic text-ink-700">
            /compare?ids={ids.join(',')}
          </code>{' '}
          &mdash; share it with a colleague, or paste it into a story.
        </p>
      )}
    </div>
  );
}

function StatLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-ink-100 pb-1">
      <dt className="text-ink-600">{label}</dt>
      <dd className="font-mono text-[13px] tabular text-ink-900">{value}</dd>
    </div>
  );
}
