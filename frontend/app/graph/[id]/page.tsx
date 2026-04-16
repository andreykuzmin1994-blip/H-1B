import { notFound } from 'next/navigation';
import { Prisma } from '@prisma/client';
import { prisma } from '@/lib/db';
import { EntityGraph } from '@/components/EntityGraph';

export const dynamic = 'force-dynamic';

export default async function GraphPage({ params }: { params: { id: string } }) {
  const id = Number(params.id);
  if (!Number.isFinite(id)) notFound();
  const rows = await prisma.$queryRaw<Array<{ id: number | bigint; depth: number | bigint }>>(Prisma.sql`
    WITH RECURSIVE reachable(id, depth) AS (
        SELECT ${id}::int, 0
      UNION
        SELECT CASE WHEN er.employer_id_a = r.id THEN er.employer_id_b ELSE er.employer_id_a END,
               r.depth + 1
          FROM entity_relationships er
          JOIN reachable r ON er.employer_id_a = r.id OR er.employer_id_b = r.id
         WHERE r.depth < 2
    )
    SELECT DISTINCT id, depth FROM reachable
  `);
  const ids = rows.map((r) => Number(r.id));
  const employers = ids.length ? await prisma.employer.findMany({ where: { id: { in: ids } } }) : [];
  const edges = ids.length
    ? await prisma.entityRelationship.findMany({
        where: { employer_id_a: { in: ids }, employer_id_b: { in: ids } },
      })
    : [];
  const violators = new Set(
    (
      await prisma.violation.findMany({
        where: { employer_id: { in: ids } },
        select: { employer_id: true },
      })
    )
      .map((v) => v.employer_id)
      .filter((v): v is number => !!v),
  );
  const depthMap = new Map<number, number>(
    rows.map((r) => [Number(r.id), Number(r.depth)]),
  );
  const graph = {
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
    })),
  };

  return (
    <div className="space-y-8">
      <div className="page-header">
        <div className="eyebrow">
          <span className="h-px w-6 bg-ember-500" /> Network
        </div>
        <h1>Entity relationship explorer.</h1>
        <p>
          Two-hop graph of employers linked by shared officers, addresses, or trade-name aliases.
          Red nodes have a documented enforcement outcome.
        </p>
      </div>
      <div className="card">
        <EntityGraph graph={graph} centerId={id} />
      </div>
    </div>
  );
}
