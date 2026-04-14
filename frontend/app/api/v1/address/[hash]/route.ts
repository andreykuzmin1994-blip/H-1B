import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@/lib/db';
import { checkRateLimit } from '@/lib/ratelimit';

export async function GET(req: NextRequest, { params }: { params: { hash: string } }) {
  const ip = req.headers.get('x-forwarded-for') ?? 'anon';
  const limit = await checkRateLimit(`address:${ip}`);
  if (!limit.success) {
    return NextResponse.json({ error: 'rate_limit_exceeded' }, { status: 429 });
  }
  const [line1, city, state] = decodeURIComponent(params.hash).split('|');
  const employers = await prisma.employer.findMany({
    where: {
      address_line1: line1 || undefined,
      city: city || undefined,
      state: state || undefined,
    },
    orderBy: { anomaly_score: 'desc' },
    take: 200,
  });
  return NextResponse.json({ address: { line1, city, state }, employers });
}
