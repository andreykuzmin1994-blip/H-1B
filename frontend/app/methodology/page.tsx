import Link from 'next/link';
import { prisma } from '@/lib/db';

export const revalidate = 300;

async function getFreshness() {
  const [lastFiling, lastViolation, lastLayoff, lastFlag] = await Promise.all([
    prisma.lcaFiling.findFirst({
      orderBy: { received_date: 'desc' },
      select: { received_date: true },
    }),
    prisma.violation.findFirst({
      orderBy: { violation_date: 'desc' },
      select: { violation_date: true },
    }),
    prisma.layoffEvent.findFirst({
      orderBy: [{ effective_date: 'desc' }, { notice_date: 'desc' }],
      select: { effective_date: true, notice_date: true },
    }),
    prisma.anomalyFlag.findFirst({
      orderBy: { created_at: 'desc' },
      select: { created_at: true },
    }),
  ]);
  return {
    lastFiling: lastFiling?.received_date ?? null,
    lastViolation: lastViolation?.violation_date ?? null,
    lastLayoff: lastLayoff?.effective_date ?? lastLayoff?.notice_date ?? null,
    lastScored: lastFlag?.created_at ?? null,
  };
}

const FLAGS: {
  code: string;
  label: string;
  weight: string;
  meaning: string;
  limits: string;
}[] = [
  {
    code: 'WAGE_BELOW_MEDIAN',
    label: 'Wage below national median',
    weight: 'High',
    meaning:
      'The employer filed LCAs at a wage materially below the BLS OEWS national median for the same SOC occupation — a common pattern in wage-suppression complaints.',
    limits:
      'Does not account for apprentice/entry-level roles or legitimate geographic pay variation below the national median.',
  },
  {
    code: 'ADDRESS_REUSE',
    label: 'Shared / reused address',
    weight: 'Medium',
    meaning:
      'Multiple registered employers share a street address. Can indicate shell companies, PEO stacks, or mail-drop registrations used to multiply H-1B cap lottery entries.',
    limits:
      'Shared addresses are also common in co-working spaces, accountant registrations, and large buildings. Confirm before drawing conclusions.',
  },
  {
    code: 'DENIAL_SPIKE',
    label: 'USCIS denial spike',
    weight: 'Medium',
    meaning:
      'Initial H-1B denial rate has climbed sharply year-over-year. Often a leading indicator of USCIS skepticism about the employer’s filings.',
    limits:
      'A single bad fiscal year can skew small-volume employers. Read alongside total volume.',
  },
  {
    code: 'LAYOFF_WITH_CONCURRENT_LCA',
    label: 'Layoffs + concurrent H-1B filings',
    weight: 'High',
    meaning:
      'A WARN-notice mass layoff occurred within ±90 days of the employer filing new H-1B LCAs. For H-1B-dependent employers this is the INA §212(n)(1)(E) non-displacement window.',
    limits:
      'Not every employer is H-1B-dependent. Different divisions of a large employer can lay off and hire simultaneously without displacement.',
  },
  {
    code: 'KNOWN_VIOLATOR',
    label: 'DOL Willful Violator list',
    weight: 'Critical',
    meaning:
      'Employer appears on the DOL Willful Violator list or has a resolved WHD wage-theft finding on record.',
    limits:
      'Historic violations may have been remediated. Check the violation date before acting.',
  },
  {
    code: 'LCA_VOLUME_OUTLIER',
    label: 'Unusual LCA volume',
    weight: 'Low',
    meaning:
      'Filing volume is a statistical outlier relative to peers in the same NAICS industry and state.',
    limits:
      'High volume alone is not abuse. Consulting firms and tech primes can legitimately file at high volume.',
  },
];

function daysAgo(d: Date | null): string {
  if (!d) return 'never';
  const delta = Math.floor((Date.now() - new Date(d).getTime()) / (1000 * 60 * 60 * 24));
  if (delta <= 0) return 'today';
  if (delta === 1) return 'yesterday';
  if (delta < 30) return `${delta} days ago`;
  if (delta < 365) return `${Math.floor(delta / 30)} months ago`;
  return `${Math.floor(delta / 365)} years ago`;
}

export default async function MethodologyPage() {
  const f = await getFreshness();

  return (
    <div className="space-y-14">
      <div className="page-header">
        <div className="eyebrow">
          <span className="h-px w-6 bg-ember-500" /> Methodology
        </div>
        <h1>How this engine works &mdash; and how it can be wrong.</h1>
        <p>
          Data plus design is power. This page exists because every transparency tool owes its
          readers an explanation of <em>what the score means</em>, <em>where it comes from</em>,
          and <em>how to use it without hurting someone wrongly</em>.
        </p>
      </div>

      {/* ---------- GUARDRAILS ---------- */}
      <section className="rounded-2xl border border-ember-500/30 bg-ember-50/40 p-6 md:p-8">
        <div className="flex flex-wrap items-start gap-6">
          <div className="flex-1 min-w-[260px]">
            <div className="eyebrow">
              <span className="h-px w-6 bg-ember-500" /> Please read first
            </div>
            <h2 className="mt-2 font-serif text-2xl font-semibold tracking-tight text-ink-900">
              A score is a starting point, not a verdict.
            </h2>
            <ul className="mt-4 space-y-2 text-sm leading-relaxed text-ink-800">
              <li>
                <strong>Nothing here is a legal finding.</strong> The anomaly score is a computed
                signal from public data. It is not proof of wrongdoing.
              </li>
              <li>
                <strong>Always verify against primary sources</strong> before naming an employer,
                filing a complaint, or publishing a story. We link the underlying records.
              </li>
              <li>
                <strong>Do not use this tool to target individuals.</strong> It is about employers
                and the systems they operate &mdash; not workers, recruiters, or people by name.
              </li>
              <li>
                <strong>Report errors.</strong> If you see a record you believe is wrong, tell us
                below and we&rsquo;ll investigate before the next update.
              </li>
            </ul>
          </div>
        </div>
      </section>

      {/* ---------- DATA FRESHNESS ---------- */}
      <section>
        <SectionHeading label="Freshness" title="When was each dataset last updated?" />
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <FreshnessCard label="LCA filings" value={daysAgo(f.lastFiling)} sub="DOL OFLC" />
          <FreshnessCard
            label="Enforcement outcomes"
            value={daysAgo(f.lastViolation)}
            sub="DOL WHD"
          />
          <FreshnessCard label="Layoff notices" value={daysAgo(f.lastLayoff)} sub="WARN Act" />
          <FreshnessCard label="Anomaly scoring" value={daysAgo(f.lastScored)} sub="Engine" />
        </div>
      </section>

      {/* ---------- SOURCES ---------- */}
      <section>
        <SectionHeading
          label="Sources"
          title="Every number traces back to a public filing."
          sub="No proprietary data. No black-box scraping. If you need to verify a cell, follow the link."
        />
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <SourceCard
            title="DOL OFLC disclosures"
            desc="LCA filings (Labor Condition Applications) every H-1B employer must file. Wage, worksite, job title, certification status."
            href="https://www.dol.gov/agencies/eta/foreign-labor/performance"
          />
          <SourceCard
            title="USCIS H-1B employer data"
            desc="Annual counts of approvals, denials, new vs. continuing petitions per employer."
            href="https://www.uscis.gov/tools/reports-and-studies/h-1b-employer-data-hub"
          />
          <SourceCard
            title="DOL WHD enforcement"
            desc="Resolved wage-theft investigations, back-wage awards, and the Willful Violator list."
            href="https://enforcedata.dol.gov/views/search.php"
          />
          <SourceCard
            title="BLS OEWS wage benchmarks"
            desc="Occupational Employment & Wage Statistics. Our wage anomaly baseline."
            href="https://www.bls.gov/oes/"
          />
          <SourceCard
            title="Federal + state WARN Act notices"
            desc="Mass-layoff notifications employers are legally required to file."
            href="https://www.dol.gov/agencies/eta/layoffs"
          />
          <SourceCard
            title="State Secretary of State registrations"
            desc="Officer and registered-agent data used to resolve entity relationships."
            href="https://www.sec.state.ma.us/cor/coridx.htm"
          />
        </div>
      </section>

      {/* ---------- SCORING ---------- */}
      <section>
        <SectionHeading
          label="Scoring"
          title="How we compute the 0–100 anomaly score."
          sub="The score is a weighted sum of flag contributions, capped at 100. Every contribution is visible in the employer dossier — nothing is hidden."
        />
        <div className="card">
          <ol className="space-y-4 text-sm leading-relaxed text-ink-800">
            <li>
              <span className="font-mono text-xs text-ember-600">01 ·</span>{' '}
              <strong>Ingest.</strong> We normalize employer names, addresses, and EINs across all
              sources so the same employer is only counted once.
            </li>
            <li>
              <span className="font-mono text-xs text-ember-600">02 ·</span>{' '}
              <strong>Evaluate flags.</strong> Each signal below runs independently. A flag fires
              only when it meets its statistical threshold.
            </li>
            <li>
              <span className="font-mono text-xs text-ember-600">03 ·</span>{' '}
              <strong>Weight by severity.</strong> Flags carry a severity (CRITICAL / HIGH /
              MEDIUM / LOW). Severity determines how many points the flag adds.
            </li>
            <li>
              <span className="font-mono text-xs text-ember-600">04 ·</span>{' '}
              <strong>Cap &amp; publish.</strong> The sum is clipped at 100. An employer at 100 is
              not &ldquo;guilty&rdquo; &mdash; they just have many co-occurring signals worth
              investigating.
            </li>
          </ol>
        </div>
      </section>

      {/* ---------- FLAG GLOSSARY ---------- */}
      <section>
        <SectionHeading
          label="Glossary"
          title="Every flag type, in plain English."
          sub="What it means, why it fires, and what it does NOT prove on its own."
        />
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {FLAGS.map((f) => (
            <article key={f.code} className="card">
              <div className="flex items-center justify-between gap-3">
                <div className="font-serif text-lg font-semibold text-ink-900">{f.label}</div>
                <span
                  className={`severity-badge ${
                    f.weight === 'Critical'
                      ? 'sev-critical'
                      : f.weight === 'High'
                      ? 'sev-high'
                      : f.weight === 'Medium'
                      ? 'sev-medium'
                      : 'sev-low'
                  }`}
                >
                  {f.weight}
                </span>
              </div>
              <code className="mt-1 inline-block rounded bg-ink-100 px-1.5 py-0.5 font-mono text-[11px] text-ink-700">
                {f.code}
              </code>
              <p className="mt-3 text-sm leading-relaxed text-ink-700">{f.meaning}</p>
              <div className="mt-3 rounded-md border border-amber-200 bg-amber-50/60 p-3 text-xs leading-relaxed text-amber-900">
                <span className="font-semibold">Does not prove:</span> {f.limits}
              </div>
            </article>
          ))}
        </div>
      </section>

      {/* ---------- LIMITATIONS ---------- */}
      <section>
        <SectionHeading label="Limits" title="What this engine cannot tell you." />
        <ul className="card space-y-3 text-sm leading-relaxed text-ink-800">
          <li>
            <strong>Intent.</strong> Anomalies can have innocent explanations &mdash; seasonal
            hiring, acquisitions, new offices, data-entry errors in filings.
          </li>
          <li>
            <strong>Individual workers.</strong> We only aggregate employer-level data. We do not
            identify beneficiaries, recruiters, or named employees.
          </li>
          <li>
            <strong>Outside the US.</strong> This engine is scoped to US federal and state public
            records. Overseas entities appear only when linked to a US employer.
          </li>
          <li>
            <strong>Real-time activity.</strong> DOL and USCIS datasets update on a delay &mdash;
            sometimes quarterly. See the freshness indicators above.
          </li>
          <li>
            <strong>Small-volume noise.</strong> Employers with very few filings can score high on
            a single anomaly. Weight findings by total volume.
          </li>
        </ul>
      </section>

      {/* ---------- REPORT / CONTRIBUTE ---------- */}
      <section className="rounded-2xl border border-ink-800 bg-ink-950 p-8 text-ink-100 md:p-10">
        <div className="eyebrow">
          <span className="h-px w-6 bg-ember-500" /> Your turn
        </div>
        <h2 className="mt-2 font-serif text-2xl font-semibold tracking-tight text-white md:text-3xl">
          Spot a mistake, or an employer we missed?
        </h2>
        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-ink-300">
          This engine gets better when workers, reporters, and researchers tell us what we got
          wrong. Open an issue on the public repository with a citation to the primary source
          &mdash; we triage weekly and credit first reporters in the changelog.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <a
            className="btn-accent"
            href="https://github.com/andreykuzmin1994-blip/h-1b/issues/new?labels=data-report"
            target="_blank"
            rel="noreferrer"
          >
            Report a data error →
          </a>
          <Link
            href="/search"
            className="btn inline-flex items-center gap-2 rounded-md border border-white/20 px-3.5 py-2 text-sm font-medium text-white hover:bg-white/10"
          >
            Back to the investigation
          </Link>
        </div>
      </section>
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

function FreshnessCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub: string;
}) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="mt-2 font-serif text-xl font-semibold text-ink-900">{value}</div>
      <div className="stat-sub">{sub}</div>
    </div>
  );
}

function SourceCard({
  title,
  desc,
  href,
}: {
  title: string;
  desc: string;
  href: string;
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="card group block transition hover:border-ember-500/50 hover:shadow-elevated"
    >
      <div className="flex items-start justify-between gap-3">
        <h3 className="font-serif text-base font-semibold text-ink-900 group-hover:text-ember-600">
          {title}
        </h3>
        <span className="text-ink-400 group-hover:text-ember-500">↗</span>
      </div>
      <p className="mt-2 text-sm leading-relaxed text-ink-600">{desc}</p>
    </a>
  );
}
