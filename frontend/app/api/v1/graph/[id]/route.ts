import { NextRequest, NextResponse } from 'next/server';
import { Prisma } from '@prisma/client';
import { prisma } from '@/lib/db';
import { checkRateLimit } from '@/lib/ratelimit';

export async function GET(req: NextRequest, { params }: { params: { id: string } }) {
  const ip = req.headers.get('x-forwarded-for') ?? 'anon';
  const limit = await checkRateLimit(`graph:${ip}`);
  if (!limit.success) {
    return NextResponse.json({ error: 'rate_limit_exceeded' }, { status: 429 });
  }
  const id = Number(params.id);
  if (!Number.isFinite(id)) {
    return NextResponse.json({ error: 'bad_request' }, { status: 400 });
  }
  const depth = Math.min(Number(new URL(req.url).searchParams.get('depth') ?? '2'), 3);
  const rows = await prisma.$queryRaw<Array<{ id: number | bigint; depth: number | bigint }>>(Prisma.sql`
    WITH RECURSIVE reachable(id, depth) AS (
        SELECT ${id}::int, 0
      UNION
        SELECT CASE WHEN er.employer_id_a = r.id THEN er.employer_id_b ELSE er.employer_id_a END,
               r.depth + 1
          FROM entity_relationships er
          JOIN reachable r ON er.employer_id_a = r.id OR er.employer_id_b = r.id
         WHERE r.depth < ${depth}::int
    )
    SELECT DISTINCT id, depth FROM reachable
  `);
  const ids = rows.map((r) => Number(r.id));
  if (ids.length === 0) return NextResponse.json({ nodes: [], edges: [] });
  const [employers, edges, violatorRows] = await Promise.all([
    prisma.employer.findMany({ where: { id: { in: ids } } }),
    prisma.entityRelationship.findMany({
      where: { employer_id_a: { in: ids }, employer_id_b: { in: ids } },
    }),
    prisma.violation.findMany({
      where: { employer_id: { in: ids } },
      select: { employer_id: true },
    }),
  ]);
  const violators = new Set(
    violatorRows.map((v) => v.employer_id).filter((v): v is number => v !== null),
  );
  const depthMap = new Map<number, number>(
    rows.map((r) => [Number(r.id), Number(r.depth)]),
  );
  return NextResponse.json({
    nodes: employers.map((e) => ({
      id: e.id,
      name: e.name,
      state: e.state,
      anomaly_score: Number(e.anomaly_score),
      is_violator: violators.has(e.id),
      depth: depthMap.get(e.id) ?? 0,
    })),
    edges: edges.map((r) => ({
      source: r.employer_id_a,
      target: r.employer_id_b,
      type: r.relationship_type,
      confidence: Number(r.confidence),
      evidence: r.evidence,
    })),
  });
}
