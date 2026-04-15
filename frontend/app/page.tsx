import Link from 'next/link';
import { prisma } from '@/lib/db';
import {
  severityClass,
  severityDotClass,
  severityLabel,
} from '@/lib/formatters';

export const revalidate = 300;

async function getStats() {
  const [employers, filings, violations, flagged, layoffs, backWagesAgg] = await Promise.all([
    prisma.employer.count(),
    prisma.lcaFiling.count(),
    prisma.violation.count(),
    prisma.employer.count({ where: { anomaly_score: { gte: 50 } } }),
    prisma.layoffEvent.count(),
    prisma.violation.aggregate({ _sum: { back_wages_amount: true } }),
  ]);
  const backWages = Number(backWagesAgg._sum.back_wages_amount ?? 0);
  return { employers, filings, violations, flagged, layoffs, backWages };
}

async function getTopFlagged() {
  return prisma.employer.findMany({
    where: { anomaly_score: { gt: 0 } },
    orderBy: { anomaly_score: 'desc' },
    take: 12,
  });
}

function compactNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return n.toLocaleString();
}

function compactCurrency(n: number): string {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(0)}k`;
  return `$${n.toLocaleString()}`;
}

export default async function HomePage() {
  const [stats, top] = await Promise.all([getStats(), getTopFlagged()]);

  return (
    <div className="space-y-14">
      {/* ---------- HERO ---------- */}
      <section className="hero hero-grid px-6 py-14 md:px-12 md:py-20">
        <div className="pointer-events-none absolute -right-24 -top-24 h-80 w-80 rounded-full bg-ember-500/20 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-32 -left-20 h-80 w-80 rounded-full bg-blue-500/10 blur-3xl" />
        <div className="relative max-w-3xl">
          <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-ember-400">
            <span className="inline-block h-2 w-2 rounded-full bg-ember-500 animate-pulseDot" />
            Live · {compactNumber(stats.filings)} filings indexed
          </div>
          <h1 className="mt-5 font-serif text-4xl font-semibold leading-[1.05] tracking-tight text-white md:text-6xl">
            Who is gaming the{' '}
            <span className="relative inline-block">
              <span className="relative z-10">H-1B system</span>
              <span className="absolute inset-x-0 bottom-1 h-3 bg-ember-500/40" aria-hidden />
            </span>
            {' '}&mdash; and who&apos;s paying for it?
          </h1>
          <p className="mt-5 max-w-2xl text-base leading-relaxed text-ink-200 md:text-lg">
            We join DOL&nbsp;LCA disclosures, USCIS employer data, DOL&nbsp;WHD enforcement records,
            BLS wage benchmarks, and WARN Act layoff notices into a single system that{' '}
            <span className="text-white">flags anomalies</span>, maps shell-entity networks, and
            writes the enforcement tip for you.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link href="/search" className="btn-accent">
              Start an investigation →
            </Link>
            <Link
              href="/violators"
              className="btn inline-flex items-center gap-2 rounded-md border border-white/20 px-3.5 py-2 text-sm font-medium text-white hover:bg-white/10"
            >
              Browse known violators
            </Link>
            <Link
              href="/map"
              className="btn inline-flex items-center gap-2 rounded-md px-3.5 py-2 text-sm font-medium text-ink-200 hover:text-white"
            >
              See it on the map
            </Link>
          </div>

          <div className="mt-12 grid max-w-3xl grid-cols-2 gap-x-8 gap-y-6 md:grid-cols-4">
            <HeroStat label="Employers tracked" value={compactNumber(stats.employers)} />
            <HeroStat label="LCA filings" value={compactNumber(stats.filings)} />
            <HeroStat
              label="Flagged (score ≥ 50)"
              value={compactNumber(stats.flagged)}
              accent
            />
            <HeroStat
              label="Back wages found"
              value={stats.backWages ? compactCurrency(stats.backWages) : '—'}
            />
          </div>
        </div>
      </section>

      {/* ---------- HOW IT WORKS ---------- */}
      <section>
        <div className="eyebrow">
          <span className="h-px w-6 bg-ember-500" /> How it works
        </div>
        <h2 className="mt-2 font-serif text-2xl font-semibold tracking-tight text-ink-900 md:text-3xl">
          Four steps from raw disclosure to filed complaint.
        </h2>
        <div className="mt-8 grid grid-cols-1 gap-4 md:grid-cols-4">
          <StepCard
            n={1}
            title="Ingest"
            body="We pull LCA disclosures, USCIS H-1B data, WHD enforcement records, BLS wages, and WARN layoff notices."
          />
          <StepCard
            n={2}
            title="Score"
            body="Employers are scored on wage gaps, LCA volume, denial rates, address reuse, and other abuse signals."
          />
          <StepCard
            n={3}
            title="Map"
            body="Entity relationships are resolved across shared addresses, officers, and trade-name aliases."
          />
          <StepCard
            n={4}
            title="Act"
            body="One click generates a formatted DOL WH-4 / USCIS tip you can paste directly into the official form."
          />
        </div>
      </section>

      {/* ---------- TOP FLAGGED ---------- */}
      <section>
        <div className="flex items-end justify-between">
          <div>
            <div className="eyebrow">
              <span className="h-px w-6 bg-ember-500" /> Top anomalies
            </div>
            <h2 className="mt-2 font-serif text-2xl font-semibold tracking-tight text-ink-900 md:text-3xl">
              Employers the engine is most worried about.
            </h2>
            <p className="mt-2 max-w-2xl text-sm text-ink-600">
              Ranked by composite anomaly score. Click any row to see filings, wage gaps, entity
              links, and enforcement history.
            </p>
          </div>
          <div className="hidden items-center gap-4 md:flex">
            <Link
              href={`/compare?ids=${top
                .slice(0, 3)
                .map((e) => e.id)
                .join(',')}`}
              className="text-sm font-medium text-ink-700 underline underline-offset-4 decoration-ember-500 decoration-2 hover:text-ember-600"
            >
              Compare top 3 →
            </Link>
            <Link
              href="/search"
              className="text-sm font-medium text-ink-700 underline underline-offset-4 decoration-ember-500 decoration-2 hover:text-ember-600"
            >
              View all →
            </Link>
          </div>
        </div>
        <div className="mt-6 overflow-hidden rounded-xl border border-ink-200 bg-white shadow-card">
          <table className="data-table">
            <thead>
              <tr>
                <th className="w-10 text-right">#</th>
                <th>Employer</th>
                <th>State</th>
                <th>NAICS</th>
                <th className="text-right">LCAs</th>
                <th>Severity</th>
              </tr>
            </thead>
            <tbody>
              {top.map((e, i) => {
                const score = Number(e.anomaly_score);
                return (
                  <tr key={e.id} className="animate-fadeUp">
                    <td className="num text-right text-ink-400">{String(i + 1).padStart(2, '0')}</td>
                    <td>
                      <Link href={`/employer/${e.id}`} className="font-medium text-ink-900 hover:text-ember-600">
                        {e.name}
                      </Link>
                      {e.city && (
                        <div className="text-xs text-ink-500">
                          {e.city}, {e.state}
                        </div>
                      )}
                    </td>
                    <td className="text-ink-600">{e.state ?? '—'}</td>
                    <td className="num text-ink-600">{e.naics_code ?? '—'}</td>
                    <td className="num text-right text-ink-800">
                      {e.total_lca_count?.toLocaleString() ?? '0'}
                    </td>
                    <td>
                      <span className={`severity-badge ${severityClass(score)}`}>
                        <span className={`severity-dot ${severityDotClass(score)}`} />
                        {severityLabel(score)} · {score.toFixed(0)}
                      </span>
                    </td>
                  </tr>
                );
              })}
              {top.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-10 text-center text-sm text-ink-500">
                    No scored employers yet. Run{' '}
                    <code className="rounded bg-ink-100 px-1.5 py-0.5 text-xs">
                      python scripts/score.py run
                    </code>{' '}
                    to populate the engine.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <Link
          href="/search"
          className="mt-4 inline-flex text-sm font-medium text-ink-700 underline underline-offset-4 decoration-ember-500 decoration-2 hover:text-ember-600 md:hidden"
        >
          View all →
        </Link>
      </section>

      {/* ---------- WHY IT MATTERS ---------- */}
      <section className="grid grid-cols-1 gap-6 md:grid-cols-3">
        <PullQuote
          label="For workers"
          body="Find out whether your employer has been underpaying, laying off Americans while hiring H-1B, or operating through undisclosed shell entities."
        />
        <PullQuote
          label="For reporters"
          body="Jump straight from a score to the underlying filings, wage comparisons, and entity network &mdash; with deep links you can cite."
        />
        <PullQuote
          label="For enforcers"
          body="Every investigation exports a pre-formatted DOL WH-4 / USCIS tip with the case evidence bundled in."
        />
      </section>

      {/* ---------- GUARDRAILS ---------- */}
      <section className="rounded-2xl border border-ember-500/30 bg-gradient-to-br from-ember-50/70 to-transparent p-6 md:p-8">
        <div className="flex flex-wrap items-start gap-6 md:flex-nowrap">
          <div className="flex-1">
            <div className="eyebrow">
              <span className="h-px w-6 bg-ember-500" /> Use responsibly
            </div>
            <h2 className="mt-2 font-serif text-2xl font-semibold tracking-tight text-ink-900">
              A score is a <em>lead</em>, not a verdict.
            </h2>
            <p className="mt-3 max-w-2xl text-sm leading-relaxed text-ink-700">
              Every number on this site comes from public filings, but an anomaly can have an
              innocent explanation. Always verify against primary sources before naming an
              employer, filing a complaint, or publishing a story. This tool is about
              <em> employers and systems</em> &mdash; never about individual workers by name.
            </p>
            <div className="mt-5 flex flex-wrap gap-3">
              <Link href="/methodology" className="btn-outline">
                Read the methodology →
              </Link>
              <a
                href="https://github.com/andreykuzmin1994-blip/h-1b/issues/new?labels=data-report"
                target="_blank"
                rel="noreferrer"
                className="btn-ghost"
              >
                Report a data error
              </a>
            </div>
          </div>
          <aside className="w-full max-w-xs shrink-0 rounded-xl border border-ink-200 bg-white p-5 shadow-card">
            <div className="stat-label">What a score is</div>
            <ul className="mt-3 space-y-2 text-[13px] leading-relaxed text-ink-700">
              <li>
                <span className="mr-2 text-lime-600">✓</span>
                Weighted sum of public-data signals
              </li>
              <li>
                <span className="mr-2 text-lime-600">✓</span>
                Traceable to the filing that triggered it
              </li>
              <li>
                <span className="mr-2 text-red-600">✗</span>
                Not a legal finding
              </li>
              <li>
                <span className="mr-2 text-red-600">✗</span>
                Not a judgment about any individual
              </li>
            </ul>
          </aside>
        </div>
      </section>
    </div>
  );
}

function HeroStat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div>
      <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-ink-400">
        {label}
      </div>
      <div
        className={`mt-1 font-serif text-3xl font-semibold tracking-tight md:text-4xl ${
          accent ? 'text-ember-400' : 'text-white'
        }`}
      >
        {value}
      </div>
    </div>
  );
}

function StepCard({ n, title, body }: { n: number; title: string; body: string }) {
  return (
    <div className="card relative">
      <div className="font-mono text-xs text-ember-600">0{n}</div>
      <div className="mt-2 font-serif text-lg font-semibold text-ink-900">{title}</div>
      <p className="mt-1.5 text-sm leading-relaxed text-ink-600">{body}</p>
    </div>
  );
}

function PullQuote({ label, body }: { label: string; body: string }) {
  return (
    <figure className="relative rounded-xl border-l-4 border-ember-500 bg-white p-5 shadow-card">
      <div className="stat-label">{label}</div>
      <blockquote className="mt-2 font-serif text-lg leading-snug text-ink-900">
        &ldquo;{body}&rdquo;
      </blockquote>
    </figure>
  );
}
