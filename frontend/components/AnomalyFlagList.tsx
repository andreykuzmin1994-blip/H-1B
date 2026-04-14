interface FlagRow {
  id: number;
  flag_type: string;
  flag_severity: string | null;
  flag_score: number;
  description: string | null;
  evidence: unknown;
}

const SEVERITY_COLOR: Record<string, string> = {
  CRITICAL: 'bg-critical',
  HIGH: 'bg-high',
  MEDIUM: 'bg-medium',
  LOW: 'bg-low',
};

export function AnomalyFlagList({ flags }: { flags: FlagRow[] }) {
  if (!flags || flags.length === 0) {
    return <p className="text-sm text-gray-500">No anomaly flags detected.</p>;
  }
  return (
    <div className="space-y-2">
      {flags.map((f) => (
        <div key={f.id} className="card">
          <div className="flex items-center gap-2">
            <span
              className={`severity-badge ${SEVERITY_COLOR[f.flag_severity ?? 'LOW'] ?? 'bg-low'}`}
            >
              {f.flag_severity}
            </span>
            <span className="font-semibold">{f.flag_type}</span>
            <span className="ml-auto text-xs text-gray-500">{Number(f.flag_score).toFixed(0)} pts</span>
          </div>
          {f.description && <p className="mt-1 text-sm text-gray-700">{f.description}</p>}
          {f.evidence && (
            <pre className="mt-2 overflow-x-auto rounded bg-gray-50 p-2 text-xs">
              {JSON.stringify(f.evidence, null, 2)}
            </pre>
          )}
        </div>
      ))}
    </div>
  );
}
