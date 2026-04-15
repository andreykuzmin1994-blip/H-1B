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
    <div className="space-y-10">
      <header>
        <div className="dateline">Geography of risk</div>
        <h1 className="mt-3 font-serif">Anomaly heatmap.</h1>
        <p className="mt-3 max-w-[65ch] text-[15px] leading-[1.55] text-ink-700">
          Every dot is an employer with an anomaly score of at least 25. Color and radius scale
          with severity. Click a marker to open its dossier.
        </p>
        <div className="mt-4 flex flex-wrap items-baseline gap-x-6 gap-y-2 text-sm text-ink-700">
          <Legend mark="mark-critical" label="Critical (75+)" />
          <Legend mark="mark-high" label="High (50–74)" />
          <Legend mark="mark-medium" label="Medium (25–49)" />
          <span className="font-mono text-[11px] uppercase tracking-wider text-ink-500">
            {rows.length.toLocaleString()} points
          </span>
        </div>
      </header>

      <div className="border-t-2 border-ink-900 pt-4">
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

function Legend({ mark, label }: { mark: string; label: string }) {
  return (
    <span className="inline-flex items-baseline gap-2">
      <span className={`sev-mark ${mark}`} />
      {label}
    </span>
  );
}
