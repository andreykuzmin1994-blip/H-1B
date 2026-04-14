import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@/lib/db';
import { checkRateLimit } from '@/lib/ratelimit';

export async function GET(req: NextRequest) {
  const ip = req.headers.get('x-forwarded-for') ?? 'anon';
  const limit = await checkRateLimit(`anomalies:${ip}`);
  if (!limit.success) {
    return NextResponse.json({ error: 'rate_limit_exceeded' }, { status: 429 });
  }
  const { searchParams } = new URL(req.url);
  const minScore = Number(searchParams.get('min_score') ?? '50');
  const state = searchParams.get('state') ?? undefined;
  const flagType = searchParams.get('flag_type') ?? undefined;
  const limitN = Math.min(Number(searchParams.get('limit') ?? '100'), 500);

  const where: any = { anomaly_score: { gte: minScore } };
  if (state) where.state = state.toUpperCase();
  if (flagType) {
    where.flags = { some: { flag_type: flagType } };
  }
  const employers = await prisma.employer.findMany({
    where,
    include: { flags: true },
    orderBy: { anomaly_score: 'desc' },
    take: limitN,
  });
  return NextResponse.json({
    count: employers.length,
    employers,
  });
}
