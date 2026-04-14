import { notFound } from 'next/navigation';
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
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Tip packet for {employer.name}</h1>
        <p className="text-sm text-gray-600">
          Pre-filled text for the DOL Form WH-4 and USCIS tip form. Copy each block into the form
          at{' '}
          <a
            className="underline"
            href="https://www.dol.gov/agencies/whd/forms/wh4"
            target="_blank"
            rel="noreferrer"
          >
            dol.gov (WH-4)
          </a>{' '}
          /{' '}
          <a
            className="underline"
            href="https://www.uscis.gov/report-fraud"
            target="_blank"
            rel="noreferrer"
          >
            uscis.gov (report fraud)
          </a>
          .
        </p>
      </div>

      <section>
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">DOL WH-4 complaint</h2>
          <CopyButton text={tip.dolText} />
        </div>
        <pre className="mt-2 whitespace-pre-wrap rounded border border-gray-200 bg-white p-4 text-sm">
          {tip.dolText}
        </pre>
      </section>

      <section>
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">USCIS tip</h2>
          <CopyButton text={tip.uscisText} />
        </div>
        <pre className="mt-2 whitespace-pre-wrap rounded border border-gray-200 bg-white p-4 text-sm">
          {tip.uscisText}
        </pre>
      </section>

      <section>
        <h2 className="text-lg font-semibold">Evidence summary</h2>
        <pre className="mt-2 whitespace-pre-wrap rounded border border-gray-200 bg-white p-4 text-xs">
          {tip.evidence}
        </pre>
      </section>
    </div>
  );
}
