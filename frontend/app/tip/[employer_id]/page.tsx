import { notFound } from 'next/navigation';
import Link from 'next/link';
import { prisma } from '@/lib/db';
import { buildTipPackage } from '@/lib/tip';
import { CopyButton } from '@/components/CopyButton';

export const dynamic = 'force-dynamic';

export default async function TipPage({ params }: { params: { employer_id: string } }) {
  const id = Number(params.employer_id);
  if (!Number.isFinite(id)) notFound();
  const employer = await prisma.employer.findUnique({ where: { id } });
  if (!employer) notFound();
  const tip = await buildTipPackage(id);

  return (
    <div className="space-y-8">
      <div className="page-header">
        <div className="eyebrow">
          <span className="h-px w-6 bg-ember-500" /> Enforcement kit
        </div>
        <h1>
          Tip packet for <span className="text-ember-600">{employer.name}</span>.
        </h1>
        <p>
          Pre-formatted complaint text ready to paste into the official DOL and USCIS forms.
          Evidence citations are bundled below &mdash; review before submitting.
        </p>
        <div className="mt-2 text-sm text-ink-600">
          Submit via{' '}
          <a
            className="link"
            href="https://www.dol.gov/agencies/whd/forms/wh4"
            target="_blank"
            rel="noreferrer"
          >
            dol.gov (WH-4)
          </a>{' '}
          or{' '}
          <a
            className="link"
            href="https://www.uscis.gov/report-fraud"
            target="_blank"
            rel="noreferrer"
          >
            uscis.gov (report fraud)
          </a>
          .
        </div>
        <Link
          href={`/employer/${employer.id}`}
          className="mt-2 inline-flex text-sm text-ink-500 hover:text-ember-600"
        >
          ← Back to dossier
        </Link>
      </div>

      <div className="rounded-xl border border-amber-300 bg-amber-50/70 p-5">
        <div className="flex items-start gap-3">
          <span aria-hidden className="mt-0.5 text-xl leading-none text-amber-700">⚑</span>
          <div>
            <div className="font-semibold text-ink-900">Before you submit this</div>
            <p className="mt-1 text-sm leading-relaxed text-ink-700">
              The text below is generated from public records. It is not legal advice and not a
              verified finding. Read each paragraph, verify the underlying filings on the{' '}
              <Link href={`/employer/${employer.id}`} className="link">
                employer dossier
              </Link>
              , and only submit if you can stand behind the facts yourself.
            </p>
          </div>
        </div>
      </div>

      <TipSection title="DOL WH-4 complaint" text={tip.dolText} />
      <TipSection title="USCIS tip" text={tip.uscisText} />

      <section>
        <div className="flex items-center justify-between">
          <h2 className="font-serif text-lg font-semibold text-ink-900">Evidence summary</h2>
          <CopyButton text={tip.evidence} />
        </div>
        <pre className="mt-2 whitespace-pre-wrap rounded-xl border border-ink-200 bg-white p-4 font-mono text-xs leading-relaxed text-ink-800 shadow-card">
          {tip.evidence}
        </pre>
      </section>
    </div>
  );
}

function TipSection({ title, text }: { title: string; text: string }) {
  return (
    <section>
      <div className="flex items-center justify-between">
        <h2 className="font-serif text-lg font-semibold text-ink-900">{title}</h2>
        <CopyButton text={text} />
      </div>
      <pre className="mt-2 whitespace-pre-wrap rounded-xl border border-ink-200 bg-white p-5 text-sm leading-relaxed text-ink-800 shadow-card">
        {text}
      </pre>
    </section>
  );
}
