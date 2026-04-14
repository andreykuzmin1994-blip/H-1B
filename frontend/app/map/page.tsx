import { prisma } from '@/lib/db';
import { AnomalyHeatmap } from '@/components/AnomalyHeatmap';

export const revalidate = 300;

export default async function MapPage() {
  const rows = await prisma.employer.findMany({
    where: {
      anomaly_score: { gte: 25 },
      address_geocoded_lat: { not: null },
      address_geocoded_lng: { not: null },
    },
    select: {
      id: true,
      name: true,
      state: true,
      anomaly_score: true,
      address_geocoded_lat: true,
      address_geocoded_lng: true,
    },
    take: 1000,
  });
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Anomaly heatmap</h1>
      <p className="text-sm text-gray-600">
        Geographic distribution of employers scored at 25 or higher. Click a marker for details.
      </p>
      <AnomalyHeatmap
        points={rows.map((r) => ({
          id: r.id,
          name: r.name,
          state: r.state,
          score: Number(r.anomaly_score),
          lat: Number(r.address_geocoded_lat),
          lng: Number(r.address_geocoded_lng),
        }))}
      />
    </div>
  );
}
