import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@/lib/db';
import { checkRateLimit } from '@/lib/ratelimit';

export async function GET(req: NextRequest, { params }: { params: { ein: string } }) {
  const ip = req.headers.get('x-forwarded-for') ?? 'anon';
  const limit = await checkRateLimit(`employer:${ip}`);
  if (!limit.success) {
    return NextResponse.json({ error: 'rate_limit_exceeded' }, { status: 429 });
  }

  // Caller may pass an EIN or a numeric employer id as a convenience.
  const ein = params.ein;
  const isNumeric = /^\d+$/.test(ein);
  const employer = await prisma.employer.findFirst({
    where: isNumeric ? { OR: [{ ein }, { id: Number(ein) }] } : { ein },
    include: {
      flags: true,
      violations: true,
      filings: { take: 50, orderBy: { received_date: 'desc' } },
    },
  });
  if (!employer) {
    return NextResponse.json({ error: 'not_found' }, { status: 404 });
  }
  return NextResponse.json({
    employer,
    meta: { generated_at: new Date().toISOString() },
  });
}
