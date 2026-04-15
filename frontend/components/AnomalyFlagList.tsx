import { severityToken } from '@/lib/formatters';

interface FlagRow {
  id: number;
  flag_type: string;
  flag_severity: string | null;
  flag_score: number;
  description: string | null;
  evidence: unknown;
}

const LABEL: Record<ReturnType<typeof severityToken>, string> = {
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
};

export function AnomalyFlagList({ flags }: { flags: FlagRow[] }) {
  if (!flags || flags.length === 0) {
    return (
      <p className="text-sm italic text-ink-500">
        No anomaly flags detected for this employer.
      </p>
    );
  }
  return (
    <ul className="divide-y divide-ink-100">
      {flags.map((f) => {
        const tone = severityToken(f.flag_severity);
        return (
          <li
            key={f.id}
            className={`grid grid-cols-1 gap-2 py-4 md:grid-cols-12 border-l-[3px] pl-4 ${
              tone === 'critical'
                ? 'border-[#7a1616]'
                : tone === 'high'
                ? 'border-[#b06427]'
                : tone === 'medium'
                ? 'border-[#9a8a26]'
                : 'border-[#6a8a52]'
            }`}
          >
            <div className="md:col-span-4">
              <div className="text-[17px] font-semibold text-ink-900">{f.flag_type}</div>
              <div className="mt-0.5 text-xs uppercase tracking-wider text-ink-600">
                {LABEL[tone]} &mdash; weight +{Number(f.flag_score).toFixed(0)}
              </div>
            </div>
            <div className="md:col-span-8">
              {f.description && (
                <p className="text-[15px] leading-[1.55] text-ink-800">{f.description}</p>
              )}
              {f.evidence ? (
                <details className="mt-3">
                  <summary className="cursor-pointer text-xs uppercase tracking-wider text-ink-500 hover:text-accent">
                    Show evidence
                  </summary>
                  <pre className="mt-2 whitespace-pre-wrap border-l-[2px] border-ink-200 pl-3 font-mono text-[11px] leading-[1.5] text-ink-700">
                    {JSON.stringify(f.evidence, null, 2)}
                  </pre>
                </details>
              ) : null}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
