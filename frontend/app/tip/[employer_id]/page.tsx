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
    <div className="space-y-10">
      <header>
        <div className="dateline">Enforcement kit</div>
        <h1 className="mt-3 font-serif">
          Tip packet &mdash; {employer.name}
        </h1>
        <p className="mt-3 max-w-[65ch] text-[15px] leading-[1.55] text-ink-700">
          Pre-formatted complaint text ready to paste into the official DOL and USCIS forms.
          Evidence citations are bundled below.
        </p>
        <p className="mt-2 max-w-[65ch] text-sm text-ink-700">
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
        </p>
        <Link
          href={`/employer/${employer.id}`}
          className="mt-4 inline-block text-sm text-ink-500 hover:text-accent"
        >
          Back to dossier
        </Link>
      </header>

      <aside className="border-l-[3px] border-accent pl-5">
        <div className="caps text-ink-500">Before you submit</div>
        <p className="mt-2 max-w-[65ch] text-[15px] leading-[1.55] text-ink-800">
          The text below is generated from public records. It is not legal advice and not a
          verified finding. Read each paragraph, cross-check the underlying filings on the{' '}
          <Link href={`/employer/${employer.id}`} className="link">
            dossier
          </Link>
          , and only submit if you can stand behind the facts yourself.
        </p>
      </aside>

      <TipSection title="DOL WH-4 complaint" text={tip.dolText} />
      <TipSection title="USCIS tip" text={tip.uscisText} />

      <section>
        <header className="flex items-baseline justify-between gap-4">
          <h2 className="font-serif">Evidence summary</h2>
          <CopyButton text={tip.evidence} />
        </header>
        <hr className="hr-hair mt-3 mb-4" />
        <pre className="whitespace-pre-wrap border-l-[3px] border-ink-200 pl-4 font-mono text-xs leading-relaxed text-ink-800">
          {tip.evidence}
        </pre>
      </section>
    </div>
  );
}

function TipSection({ title, text }: { title: string; text: string }) {
  return (
    <section>
      <header className="flex items-baseline justify-between gap-4">
        <h2 className="font-serif">{title}</h2>
        <CopyButton text={text} />
      </header>
      <hr className="hr-hair mt-3 mb-4" />
      <pre className="whitespace-pre-wrap border-l-[3px] border-ink-200 pl-4 text-[15px] leading-[1.6] text-ink-800">
        {text}
      </pre>
    </section>
  );
}
