'use client';

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

export interface EmployerChartData {
  byYear: { year: number; count: number }[];
  bySoc: { soc: string; count: number }[];
  uscisByYear: { year: number; approvals: number; denials: number }[];
}

const TICK = { fill: '#5e5b52', fontSize: 11, fontFamily: 'IBM Plex Mono, monospace' };
const GRID = { stroke: '#d8d5cc' };
const TOOLTIP_STYLE = {
  background: '#f4f1ea',
  border: '1px solid #111111',
  borderRadius: 0,
  fontSize: 12,
  color: '#111111',
};

export function EmployerCharts({ byYear, bySoc, uscisByYear }: EmployerChartData) {
  return (
    <div className="grid grid-cols-1 gap-10 md:grid-cols-3">
      <Panel
        title="Filings per fiscal year"
        sub="LCA volume trend"
        empty={byYear.length === 0 ? 'No filings with a fiscal year yet.' : null}
      >
        <ResponsiveContainer>
          <LineChart data={byYear} margin={{ top: 4, right: 8, bottom: 0, left: -10 }}>
            <CartesianGrid {...GRID} strokeDasharray="2 3" />
            <XAxis dataKey="year" tick={TICK} stroke="#bab6ac" />
            <YAxis allowDecimals={false} tick={TICK} stroke="#bab6ac" />
            <Tooltip contentStyle={TOOLTIP_STYLE} />
            <Line
              type="monotone"
              dataKey="count"
              stroke="#111111"
              strokeWidth={1.5}
              dot={{ r: 2.5, fill: '#111111' }}
              activeDot={{ r: 4 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </Panel>

      <Panel
        title="Top SOC codes"
        sub="By filing volume"
        empty={bySoc.length === 0 ? 'No SOC data.' : null}
      >
        <ResponsiveContainer>
          <BarChart data={bySoc} margin={{ top: 4, right: 8, bottom: 0, left: -10 }}>
            <CartesianGrid {...GRID} strokeDasharray="2 3" />
            <XAxis dataKey="soc" tick={TICK} stroke="#bab6ac" />
            <YAxis allowDecimals={false} tick={TICK} stroke="#bab6ac" />
            <Tooltip contentStyle={TOOLTIP_STYLE} />
            <Bar dataKey="count" fill="#252421" />
          </BarChart>
        </ResponsiveContainer>
      </Panel>

      <Panel
        title="USCIS approvals vs denials"
        sub="Initial decisions, by year"
        empty={uscisByYear.length === 0 ? 'No USCIS data for this employer.' : null}
      >
        <ResponsiveContainer>
          <BarChart data={uscisByYear} margin={{ top: 4, right: 8, bottom: 0, left: -10 }}>
            <CartesianGrid {...GRID} strokeDasharray="2 3" />
            <XAxis dataKey="year" tick={TICK} stroke="#bab6ac" />
            <YAxis allowDecimals={false} tick={TICK} stroke="#bab6ac" />
            <Tooltip contentStyle={TOOLTIP_STYLE} />
            <Legend wrapperStyle={{ fontSize: 11, color: '#5e5b52' }} />
            <Bar dataKey="approvals" stackId="a" fill="#3b3a35" />
            <Bar dataKey="denials" stackId="a" fill="#9a1f1f" />
          </BarChart>
        </ResponsiveContainer>
      </Panel>
    </div>
  );
}

function Panel({
  title,
  sub,
  empty,
  children,
}: {
  title: string;
  sub: string;
  empty: string | null;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h3 className="font-serif text-[17px] leading-[1.2]">{title}</h3>
      <div className="mt-0.5 text-xs text-ink-500">{sub}</div>
      <div className="mt-3">
        {empty ? (
          <p className="text-sm italic text-ink-500">{empty}</p>
        ) : (
          <div style={{ width: '100%', height: 200 }}>{children}</div>
        )}
      </div>
    </div>
  );
}
