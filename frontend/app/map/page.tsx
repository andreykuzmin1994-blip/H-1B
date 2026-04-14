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
    <div className="space-y-8">
      <div className="page-header">
        <div className="eyebrow">
          <span className="h-px w-6 bg-ember-500" /> Geography of risk
        </div>
        <h1>Anomaly heatmap.</h1>
        <p>
          Every dot is an employer with an anomaly score of at least 25. Color and radius scale
          with severity. Click a marker to open its investigation.
        </p>
      </div>

      <div className="flex flex-wrap gap-3 text-xs text-ink-600">
        <LegendSwatch color="bg-red-600" label="Critical (75+)" />
        <LegendSwatch color="bg-orange-500" label="High (50–74)" />
        <LegendSwatch color="bg-amber-500" label="Medium (25–49)" />
        <span className="text-ink-400">·</span>
        <span>{rows.length.toLocaleString()} points</span>
      </div>

      <div className="overflow-hidden rounded-xl border border-ink-200 bg-white shadow-card">
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
    </div>
  );
}

function LegendSwatch({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`severity-dot ${color}`} />
      {label}
    </span>
  );
}
