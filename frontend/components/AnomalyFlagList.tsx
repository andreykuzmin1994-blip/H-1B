interface FlagRow {
  id: number;
  flag_type: string;
  flag_severity: string | null;
  flag_score: number;
  description: string | null;
  evidence: unknown;
}

const SEVERITY_CLASS: Record<string, string> = {
  CRITICAL: 'sev-critical',
  HIGH: 'sev-high',
  MEDIUM: 'sev-medium',
  LOW: 'sev-low',
};

const SEVERITY_DOT: Record<string, string> = {
  CRITICAL: 'bg-red-600',
  HIGH: 'bg-orange-500',
  MEDIUM: 'bg-amber-500',
  LOW: 'bg-lime-500',
};

export function AnomalyFlagList({ flags }: { flags: FlagRow[] }) {
  if (!flags || flags.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-ink-200 bg-white/60 p-6 text-center text-sm text-ink-500">
        No anomaly flags detected for this employer.
      </div>
    );
  }
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
      {flags.map((f) => {
        const sev = f.flag_severity ?? 'LOW';
        return (
          <div key={f.id} className="card relative overflow-hidden">
            <div
              aria-hidden
              className={`absolute inset-y-0 left-0 w-1 ${SEVERITY_DOT[sev] ?? 'bg-lime-500'}`}
            />
            <div className="flex items-center gap-2">
              <span className={`severity-badge ${SEVERITY_CLASS[sev] ?? 'sev-low'}`}>
                <span className={`severity-dot ${SEVERITY_DOT[sev] ?? 'bg-lime-500'}`} />
                {sev}
              </span>
              <span className="font-semibold text-ink-900">{f.flag_type}</span>
              <span className="ml-auto font-mono text-xs text-ink-500">
                +{Number(f.flag_score).toFixed(0)} pts
              </span>
            </div>
            {f.description && (
              <p className="mt-2 text-sm leading-relaxed text-ink-700">{f.description}</p>
            )}
            {f.evidence ? (
              <details className="mt-3 group">
                <summary className="cursor-pointer text-xs font-medium text-ink-500 hover:text-ember-600">
                  Show evidence
                </summary>
                <pre className="mt-2 overflow-x-auto rounded bg-ink-50 p-3 font-mono text-[11px] leading-relaxed text-ink-700">
                  {JSON.stringify(f.evidence, null, 2)}
                </pre>
              </details>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
