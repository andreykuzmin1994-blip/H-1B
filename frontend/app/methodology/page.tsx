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
  weight: 'Critical' | 'High' | 'Medium' | 'Low';
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
      'Does not account for apprentice or entry-level roles, or legitimate geographic pay variation below the national median.',
  },
  {
    code: 'ADDRESS_REUSE',
    label: 'Shared or reused address',
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
      'Initial H-1B denial rate has climbed sharply year over year. Often a leading indicator of USCIS skepticism about the employer’s filings.',
    limits:
      'A single bad fiscal year can skew small-volume employers. Read alongside total volume.',
  },
  {
    code: 'LAYOFF_WITH_CONCURRENT_LCA',
    label: 'Layoffs with concurrent H-1B filings',
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
      'Employer appears on the DOL Willful Violator list, or has a resolved WHD wage-theft finding on record.',
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

const SOURCES = [
  {
    title: 'DOL OFLC disclosures',
    desc: 'LCA filings every H-1B employer is required to file. Wage, worksite, job title, certification status.',
    href: 'https://www.dol.gov/agencies/eta/foreign-labor/performance',
  },
  {
    title: 'USCIS H-1B employer data',
    desc: 'Annual counts of approvals, denials, new versus continuing petitions per employer.',
    href: 'https://www.uscis.gov/tools/reports-and-studies/h-1b-employer-data-hub',
  },
  {
    title: 'DOL WHD enforcement',
    desc: 'Resolved wage-theft investigations, back-wage awards, and the Willful Violator list.',
    href: 'https://enforcedata.dol.gov/views/search.php',
  },
  {
    title: 'BLS OEWS wage benchmarks',
    desc: 'Occupational Employment and Wage Statistics. The wage-anomaly baseline.',
    href: 'https://www.bls.gov/oes/',
  },
  {
    title: 'Federal and state WARN Act notices',
    desc: 'Mass-layoff notifications employers are legally required to file.',
    href: 'https://www.dol.gov/agencies/eta/layoffs',
  },
  {
    title: 'Secretary of State registrations',
    desc: 'Officer and registered-agent data used to resolve entity relationships.',
    href: 'https://www.sec.state.ma.us/cor/coridx.htm',
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
    <article className="space-y-16">
      <header>
        <div className="dateline">Methodology</div>
        <h1 className="mt-3 font-serif">
          How this engine works &mdash; and how it can be wrong.
        </h1>
        <p className="dropcap mt-6 max-w-[65ch] text-[17px] leading-[1.55] text-ink-800">
          Data plus design is power. This page exists because every transparency tool owes its
          readers an explanation of what the score means, where it comes from, and how to use
          it without hurting someone wrongly. What follows is not an apology; it is an audit
          trail you can use against us if we get something wrong.
        </p>
      </header>

      {/* ---------- GUARDRAILS ---------- */}
      <section className="border-l-[3px] border-accent pl-6">
        <h2 className="font-serif">A score is a starting point, not a verdict.</h2>
        <ul className="mt-4 max-w-[65ch] space-y-3 text-[15px] leading-[1.55] text-ink-800">
          <li>
            <strong>Nothing here is a legal finding.</strong> The anomaly score is a computed
            signal from public data. It is not proof of wrongdoing.
          </li>
          <li>
            <strong>Verify against primary sources</strong> before naming an employer, filing a
            complaint, or publishing a story. We link the underlying records.
          </li>
          <li>
            <strong>Do not use this tool to target individuals.</strong> It is about employers
            and the systems they operate — never about workers, recruiters, or people by name.
          </li>
          <li>
            <strong>Report errors.</strong> If a row is wrong, tell us below. We triage weekly
            and credit first reporters in the changelog.
          </li>
        </ul>
      </section>

      {/* ---------- FRESHNESS ---------- */}
      <section>
        <h2 className="font-serif">When each dataset was last refreshed.</h2>
        <hr className="hr-hair mt-3 mb-6" />
        <dl className="grid grid-cols-2 gap-x-10 gap-y-4 text-sm md:grid-cols-4">
          <FreshnessRow label="LCA filings" value={daysAgo(f.lastFiling)} source="DOL OFLC" />
          <FreshnessRow
            label="Enforcement outcomes"
            value={daysAgo(f.lastViolation)}
            source="DOL WHD"
          />
          <FreshnessRow
            label="Layoff notices"
            value={daysAgo(f.lastLayoff)}
            source="WARN Act"
          />
          <FreshnessRow
            label="Anomaly scoring"
            value={daysAgo(f.lastScored)}
            source="Engine"
          />
        </dl>
      </section>

      {/* ---------- SOURCES ---------- */}
      <section>
        <h2 className="font-serif">Every number traces back to a public filing.</h2>
        <p className="mt-3 max-w-[65ch] text-[15px] leading-[1.55] text-ink-700">
          No proprietary data. No black-box scraping. If you need to verify a cell, follow the
          link.
        </p>
        <hr className="hr-hair mt-4 mb-6" />
        <ul className="divide-y divide-ink-100">
          {SOURCES.map((s) => (
            <li key={s.href} className="grid grid-cols-1 gap-2 py-4 md:grid-cols-12">
              <div className="md:col-span-4">
                <a
                  className="link font-serif text-[17px]"
                  href={s.href}
                  target="_blank"
                  rel="noreferrer"
                >
                  {s.title}
                </a>
              </div>
              <p className="md:col-span-8 text-[15px] leading-[1.55] text-ink-700">{s.desc}</p>
            </li>
          ))}
        </ul>
      </section>

      {/* ---------- SCORING ---------- */}
      <section>
        <h2 className="font-serif">How the 0&ndash;100 score is computed.</h2>
        <p className="mt-3 max-w-[65ch] text-[15px] leading-[1.55] text-ink-700">
          The score is a weighted sum of flag contributions, capped at 100. Every contribution
          is visible in the employer dossier &mdash; nothing is hidden.
        </p>
        <hr className="hr-hair mt-4 mb-6" />
        <ol className="max-w-[65ch] space-y-5 text-[15px] leading-[1.55] text-ink-800">
          <li>
            <strong>1. Ingest.</strong> We normalize employer names, addresses, and EINs across
            all sources so the same employer is only counted once.
          </li>
          <li>
            <strong>2. Evaluate.</strong> Each signal below runs independently. A flag fires
            only when it meets its statistical threshold.
          </li>
          <li>
            <strong>3. Weight.</strong> Flags carry a severity (Critical, High, Medium, Low)
            which determines how many points they add.
          </li>
          <li>
            <strong>4. Cap and publish.</strong> The sum is clipped at 100. An employer at 100
            is not &ldquo;guilty&rdquo; &mdash; they just have many co-occurring signals worth
            investigating.
          </li>
        </ol>
      </section>

      {/* ---------- GLOSSARY ---------- */}
      <section>
        <h2 className="font-serif">Every flag, in plain English.</h2>
        <p className="mt-3 max-w-[65ch] text-[15px] leading-[1.55] text-ink-700">
          What each flag means, why it fires, and what it does <em>not</em> prove on its own.
        </p>
        <hr className="hr-hair mt-4 mb-6" />
        <div className="divide-y divide-ink-200">
          {FLAGS.map((flag) => (
            <article key={flag.code} className="grid grid-cols-1 gap-4 py-6 md:grid-cols-12">
              <div className="md:col-span-4">
                <h3 className="font-serif text-[19px] leading-[1.2]">{flag.label}</h3>
                <div className="mt-1 font-mono text-[11px] uppercase tracking-wider text-ink-500">
                  {flag.code}
                </div>
                <div className="mt-1 text-xs uppercase tracking-wider text-ink-700">
                  Weight &mdash; {flag.weight}
                </div>
              </div>
              <div className="md:col-span-8 space-y-3 text-[15px] leading-[1.6] text-ink-800">
                <p>{flag.meaning}</p>
                <p className="italic text-ink-600">
                  <span className="not-italic font-semibold text-ink-800">Does not prove:</span>{' '}
                  {flag.limits}
                </p>
              </div>
            </article>
          ))}
        </div>
      </section>

      {/* ---------- LIMITATIONS ---------- */}
      <section>
        <h2 className="font-serif">What this engine cannot tell you.</h2>
        <hr className="hr-hair mt-3 mb-6" />
        <ul className="max-w-[70ch] space-y-3 text-[15px] leading-[1.6] text-ink-800">
          <li>
            <strong>Intent.</strong> Anomalies can have innocent explanations — seasonal
            hiring, acquisitions, new offices, data-entry errors in filings.
          </li>
          <li>
            <strong>Individual workers.</strong> We only aggregate employer-level data. We do
            not identify beneficiaries, recruiters, or named employees.
          </li>
          <li>
            <strong>Outside the US.</strong> This engine is scoped to US federal and state
            public records. Overseas entities appear only when linked to a US employer.
          </li>
          <li>
            <strong>Real-time activity.</strong> DOL and USCIS datasets update on a delay,
            sometimes quarterly. See the freshness indicators above.
          </li>
          <li>
            <strong>Small-volume noise.</strong> Employers with very few filings can score high
            on a single anomaly. Weight findings by total volume.
          </li>
        </ul>
      </section>

      {/* ---------- REPORT ---------- */}
      <section className="border-t-2 border-ink-900 pt-8">
        <h2 className="font-serif">Spot a mistake? Tell us.</h2>
        <p className="mt-3 max-w-[65ch] text-[15px] leading-[1.55] text-ink-800">
          This engine gets better when workers, reporters, and researchers say what we got
          wrong. Open an issue on the public repository with a citation to the primary source.
        </p>
        <div className="mt-5 flex flex-wrap gap-6">
          <a
            className="btn btn-primary"
            href="https://github.com/andreykuzmin1994-blip/h-1b/issues/new?labels=data-report"
            target="_blank"
            rel="noreferrer"
          >
            Report a data error
          </a>
          <Link href="/search" className="btn-text">
            Back to the investigation
          </Link>
        </div>
      </section>
    </article>
  );
}

function FreshnessRow({
  label,
  value,
  source,
}: {
  label: string;
  value: string;
  source: string;
}) {
  return (
    <div>
      <dt className="caps text-ink-500">{label}</dt>
      <dd className="mt-1 font-serif text-[19px] text-ink-900">{value}</dd>
      <div className="mt-0.5 text-xs text-ink-500">{source}</div>
    </div>
  );
}
